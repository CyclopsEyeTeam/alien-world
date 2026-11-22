"""Bounded background writes to the existing, single byte archive.

One thread owns SQLite writes for every view of a canonical path in this
process. Other application processes use their own actor; SQLite WAL/FULL
serializes those writers while keeping committed reads independent of fsync.
WAL/SHM are temporary journal controls. The last available owner checkpoints
and restores DELETE mode at close, without ever manually deleting a journal.

``put`` accepts volatile, bounded work. Only a completed barrier acknowledges
durability. Compression and transactions belong to the writer thread; native
and GTK callbacks use after_flush, never the blocking startup/shutdown flush.
"""
import asyncio
import hashlib
import os
import secrets
import sqlite3
import threading
import time
import zlib
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FutureTimeout
from pathlib import Path

from content_cache import (CacheBusy, MAX_BYTES, MAX_METADATA, MAX_PENDING_BYTES,
                           _json, _kind, _unpack, _world, json_bytes,
                           read_reference, reference_identity)


_REGISTRY = {}
_REGISTRY_LOCK = threading.RLock()
_MAX_PENDING_RECORDS = 4096
_MAX_CONTINUATIONS = 4096
_CLOSE_SECONDS = 4.
_BATCH_RECORDS = 32
_FLUSH_SECONDS = 1.
# Under a real backlog one fsync covers several whole groups: commit latency on
# a busy rotational disk, not record size, bounds the writer's throughput.
_BACKLOG_RECORDS = 128
_MAX_TXN_RECORDS = 512
_MAX_TXN_BYTES = 4 * 1024 * 1024


def _ordered_id():
    """32 hex like uuid4().hex: nanosecond time, then 64 random bits.

    New ids and appended keys land at the end of the id and heads indexes, so
    each insert touches recently cached pages instead of a random page of a
    multi-gigabyte archive on a rotational disk.
    """
    return f'{time.time_ns():016x}{secrets.token_hex(8)}'


def _busy(error):
    code = getattr(error, 'sqlite_errorcode', None)
    if code is not None:
        return (code & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    return any(word in str(error).lower() for word in ('locked', 'busy'))


def _future():
    result = Future()
    # Cancelling an observer must not cancel a write or remove its fence.
    result.set_running_or_notify_cancel()
    return result


class _Record:
    __slots__ = ('sequence', 'ident', 'world', 'kind', 'key', 'raw', 'digest',
                 'metadata', 'cost', 'hidden', 'previous_ref', 'group', 'state')

    def __init__(self, sequence, world, kind, key, raw, metadata, digest, hidden, previous_ref, group=None,
                 state=False):
        self.sequence = sequence
        self.ident = _ordered_id()
        self.world, self.kind, self.key = world, kind, key
        self.raw, self.metadata, self.digest = raw, metadata, digest
        self.cost = len(raw) + len(metadata)
        self.hidden = hidden
        self.previous_ref = previous_ref
        self.group = group
        # A keyed state snapshot (set_json/stage_json). Only these supersede
        # older versions of themselves; art, Eye and appended records keep all.
        self.state = state

    @property
    def ref(self):
        return f'alien-cache:v1:{self.world}:{self.ident}:{self.digest}'

    @property
    def head(self):
        return self.world, self.kind, self.key


class _Actor:
    def __init__(self, path, max_pending_bytes):
        self.path = path
        self.max_pending_bytes = max_pending_bytes
        self.condition = threading.Condition(threading.RLock())
        self.read_lock = threading.RLock()
        self.pending = OrderedDict()
        self.heads, self.all_heads = {}, {}
        # Lean archive: per state head, the kept previous committed version,
        # and the superseded ids queued for deletion one commit later.
        self.kept_previous, self.doomed = {}, []
        self.pending_bytes = self.accepted = self.durable = self.commits = 0
        self.fences = []
        self.continuations = 0
        self.owners = 0
        self.error = None
        self.read_failures = self.read_busy_errors = self.last_read_code = 0
        self.force = self.stopping = False
        self.stop_deadline = None
        self.cleanup_diagnostic = None
        self.last_flush = time.monotonic()
        self.reader = None
        self.ready = _future()
        self.thread = threading.Thread(target=self._run, name='alien-archive-writer', daemon=True)

    def start(self):
        try:
            self.thread.start()
        except BaseException:
            # No thread or SQLite connection exists, so there is no cleanup
            # owner that could retire this registry reservation later.
            if _REGISTRY.get(str(self.path)) is self:
                del _REGISTRY[str(self.path)]
            raise
        try:
            self.ready.result(timeout=_CLOSE_SECONDS)
        except BaseException as error:
            with self.condition:
                self.stopping = True
                self.stop_deadline = time.monotonic() + _CLOSE_SECONDS
                self.condition.notify()
            # A blocked storage syscall may return after this caller. Keep
            # the actor registered until its real connection cleanup finishes.
            if isinstance(error, FutureTimeout):
                raise CacheBusy('content archive startup timed out') from error
            raise

    def check(self):
        if self.error is not None:
            raise self.error
        if self.stopping:
            raise CacheBusy('content archive is closing')

    def query(self, sql, values=(), many=False):
        with self.read_lock:
            if self.reader is None:
                raise ValueError('content archive is closed')
            try:
                cursor = self.reader.execute(sql, values)
                return cursor.fetchall() if many else cursor.fetchone()
            except sqlite3.Error as error:
                code = getattr(error, 'sqlite_errorcode', 0) & 255
                with self.condition:
                    self.read_failures += 1
                    self.read_busy_errors += int(_busy(error))
                    self.last_read_code = code
                raise OSError('committed content archive read failed') from error

    def enqueue(self, world, kind, key, raw, metadata, digest, hidden=False, previous_ref=None, state=False):
        with self.condition:
            self.check()
            cost = len(raw) + len(metadata)
            if (self.pending_bytes + cost > self.max_pending_bytes or
                    len(self.pending) >= _MAX_PENDING_RECORDS):
                raise CacheBusy('content archive pending capacity is full')
            record = _Record(self.accepted + 1, world, kind, key, raw, metadata, digest, hidden, previous_ref,
                             state=state)
            self.accepted = record.sequence
            self.pending[record.ident] = record
            self.pending_bytes += cost
            self.all_heads[record.head] = record.ident
            if not hidden:
                self.heads[record.head] = record.ident
            self.condition.notify()
            return record.ref

    def enqueue_batch(self, prepared):
        with self.condition:
            self.check()
            prepared = tuple(prepared[:_BATCH_RECORDS + 1])
            if not 1 <= len(prepared) <= _BATCH_RECORDS:
                raise ValueError('cache JSON batch must contain 1..32 entries')
            cost = sum(len(raw) + len(metadata) for _, _, _, raw, metadata, _ in prepared)
            if (self.pending_bytes + cost > self.max_pending_bytes or
                    len(self.pending) + len(prepared) > _MAX_PENDING_RECORDS):
                raise CacheBusy('content archive pending capacity is full')
            # Construct the whole group before accepting any prefix. Its tag
            # is volatile only; SQLite schema and the existing write stay intact.
            group = object()
            records = [_Record(self.accepted + index + 1, world, kind, key,
                               raw, metadata, digest, False, None, group)
                       for index, (world, kind, key, raw, metadata, digest) in enumerate(prepared)]
            refs = [row.ref for row in records]
            for row in records:
                self.pending[row.ident] = row
                self.all_heads[row.head] = row.ident
                self.heads[row.head] = row.ident
            self.accepted = records[-1].sequence
            self.pending_bytes += cost
            self.condition.notify()
            return refs

    def barrier(self):
        future = _future()
        with self.condition:
            if self.error is not None:
                error = self.error
            elif self.accepted <= self.durable:
                error = None
            else:
                for sequence, existing in self.fences:
                    if sequence == self.accepted:
                        return existing
                self.fences.append((self.accepted, future))
                self.force = True
                self.condition.notify()
                return future
        if error is None:
            future.set_result(None)
        else:
            future.set_exception(error)
        return future

    @staticmethod
    def _schema(db):
        version = db.execute('PRAGMA user_version').fetchone()[0]
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not ((version == 0 and not tables) or (version == 1 and tables == {'records', 'heads'})):
            raise ValueError('unsupported content cache schema; preserve file')
        return version

    def _open_database(self):
        db = sqlite3.connect(self.path, timeout=.25, isolation_level=None)
        try:
            self._schema(db)
            deadline = time.monotonic() + _CLOSE_SECONDS
            while True:
                try:
                    mode = db.execute('PRAGMA journal_mode=WAL').fetchone()[0]
                    if mode.lower() != 'wal':
                        raise OSError('content archive WAL mode unavailable')
                    break
                except sqlite3.OperationalError as error:
                    if not _busy(error) or time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA temp_store=MEMORY')
            db.execute('PRAGMA busy_timeout=250')
            if self._schema(db) == 0:
                while True:
                    try:
                        db.execute('BEGIN IMMEDIATE')
                        break
                    except sqlite3.OperationalError as error:
                        if not _busy(error) or time.monotonic() >= deadline:
                            raise
                        time.sleep(.01)
                # A different application process may have initialized while
                # this actor waited for SQLite's writer lock.
                if self._schema(db) == 0:
                    db.execute('CREATE TABLE records(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,world TEXT NOT NULL,kind TEXT NOT NULL,key TEXT NOT NULL,payload BLOB NOT NULL,digest TEXT NOT NULL,size INTEGER NOT NULL,metadata BLOB NOT NULL)')
                    db.execute('CREATE INDEX world_kind ON records(world,kind,seq)')
                    db.execute('CREATE TABLE heads(world TEXT NOT NULL,kind TEXT NOT NULL,key TEXT NOT NULL,id TEXT NOT NULL,PRIMARY KEY(world,kind,key))')
                    db.execute('PRAGMA user_version=1')
                db.commit()
            os.chmod(self.path, 0o600)
            return db
        except BaseException:
            db.close()
            raise

    def _failed(self, error):
        if not isinstance(error, OSError):
            wrapped = OSError('content archive commit failed')
            wrapped.__cause__ = error
            error = wrapped
        with self.condition:
            self.error = error
            fences = [future for _, future in self.fences]
            self.fences.clear()
            self.condition.notify_all()
        for future in fences:
            future.set_exception(error)

    def _write(self, db, records):
        # Raw queued/inflight bytes plus metadata stay charged until ACK.
        # Compressed bytes are worker-local, at most one transaction (32 records,
        # or under backlog 512 records / 4 MiB beyond its first 32 records);
        # zlib's small incompressible overhead is additional transient memory.
        rows = [(row.ident, row.world, row.kind, row.key, zlib.compress(row.raw, 3),
                 row.digest, len(row.raw), row.metadata) for row in records]
        states = OrderedDict()
        for row in records:
            if row.state:
                states.setdefault(row.head, []).append(row.ident)
        # Readers may still hold a private proposal's previous version.
        protected = {reference_identity(row.previous_ref)[1] for row in records
                     if row.hidden and row.previous_ref}
        while True:
            try:
                db.execute('BEGIN IMMEDIATE')
                # Versions superseded by the previous commit. Waiting one whole
                # commit lets a reader that resolved a head finish its read.
                db.executemany('DELETE FROM records WHERE id=?', [(ident,) for ident in self.doomed])
                versions = {}
                for head, idents in states.items():
                    outgoing = db.execute('SELECT id FROM heads WHERE world=? AND kind=? AND key=?', head).fetchone()
                    versions[head] = ([outgoing[0]] if outgoing else []) + idents
                db.executemany('INSERT INTO records(id,world,kind,key,payload,digest,size,metadata) VALUES(?,?,?,?,?,?,?,?)', rows)
                db.executemany('INSERT INTO heads(world,kind,key,id) VALUES(?,?,?,?) ON CONFLICT(world,kind,key) DO UPDATE SET id=excluded.id',
                               [(row.world, row.kind, row.key, row.ident) for row in records])
                db.commit()
                # Keep the current and the previous version of each state head.
                doomed, kept = [], {}
                for head, chain in versions.items():
                    if len(chain) < 2:
                        continue
                    older = chain[:-2]
                    earlier = self.kept_previous.get(head)
                    if earlier is not None and earlier not in chain:
                        older.insert(0, earlier)
                    doomed.extend(ident for ident in older if ident not in protected)
                    kept[head] = chain[-2]
                self.kept_previous.update(kept)
                self.doomed = doomed
                return
            except sqlite3.Error as error:
                db.rollback()
                if not _busy(error):
                    raise
                with self.condition:
                    if self.stopping and time.monotonic() >= self.stop_deadline:
                        raise CacheBusy('content archive close could not drain its writer') from error
                    self.condition.wait(.02)

    def _cleanup(self, db):
        with self.read_lock:
            if self.reader is not None:
                self.reader.close()
                self.reader = None
        if db is not None:
            try:
                result = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                if result[0]:
                    self.cleanup_diagnostic = 'archive journal retained while another reader or writer is active'
                else:
                    mode = db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]
                    if mode.lower() != 'delete':
                        self.cleanup_diagnostic = 'archive journal retained while another owner is active'
            except sqlite3.Error as error:
                # Cleanup contention is independent of already acknowledged
                # durability. SQLite, never this adapter, owns WAL removal.
                self.cleanup_diagnostic = ('archive journal retained while another owner is active'
                                           if _busy(error) else 'archive journal cleanup unavailable')
            finally:
                db.close()

    def _run(self):
        db = None
        try:
            db = self._open_database()
            with self.condition:
                if self.stopping:
                    raise CacheBusy('content archive startup was cancelled')
            with self.read_lock:
                self.reader = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                                              timeout=.05, check_same_thread=False)
                self.reader.execute('PRAGMA query_only=ON')
            self.ready.set_result(None)
            while True:
                with self.condition:
                    while True:
                        if self.stopping and (self.error is not None or not self.pending):
                            return
                        if self.error is None and self.pending:
                            remaining = _FLUSH_SECONDS - (time.monotonic() - self.last_flush)
                            if self.force or self.stopping or len(self.pending) >= _BATCH_RECORDS or remaining <= 0:
                                queued = list(self.pending.values())
                                cut = min(_BATCH_RECORDS, len(queued))
                                if len(queued) >= _BACKLOG_RECORDS:
                                    size = sum(len(row.raw) for row in queued[:cut])
                                    while cut < min(_MAX_TXN_RECORDS, len(queued)):
                                        size += len(queued[cut].raw)
                                        if size > _MAX_TXN_BYTES:
                                            break
                                        cut += 1
                                records = queued[:cut]
                                if (len(queued) > cut and records[-1].group is not None
                                        and records[-1].group is queued[cut].group):
                                    trailing = records[-1].group
                                    while records and records[-1].group is trailing:
                                        records.pop()
                                # Every accepted group fits one batch. Trimming
                                # a partial trailing group therefore leaves an
                                # earlier complete prefix and cannot stall FIFO.
                                break
                        else:
                            remaining = None
                        self.condition.wait(remaining)
                try:
                    self._write(db, records)
                except BaseException as error:
                    self._failed(error)
                    continue
                with self.condition:
                    for row in records:
                        del self.pending[row.ident]
                        self.pending_bytes -= row.cost
                        if self.heads.get(row.head) == row.ident:
                            del self.heads[row.head]
                        if self.all_heads.get(row.head) == row.ident:
                            del self.all_heads[row.head]
                    self.durable = records[-1].sequence
                    self.commits += 1
                    self.last_flush = time.monotonic()
                    complete = [future for sequence, future in self.fences if sequence <= self.durable]
                    self.fences = [(sequence, future) for sequence, future in self.fences if sequence > self.durable]
                    self.force = bool(self.fences)
                    self.condition.notify_all()
                for future in complete:
                    future.set_result(None)
        except BaseException as error:
            if not self.ready.done():
                self.ready.set_exception(error)
            else:
                self._failed(error)
        finally:
            self._cleanup(db)
            with _REGISTRY_LOCK:
                if _REGISTRY.get(str(self.path)) is self:
                    del _REGISTRY[str(self.path)]


class AsyncContentCache:
    background_writer = True

    def __init__(self, path, world_id, dispatch=None, max_pending_bytes=MAX_PENDING_BYTES):
        self.world_id = _world(world_id)
        supplied = Path(path).absolute()
        if supplied.is_symlink():
            raise ValueError('content cache must not be a symlink')
        if type(max_pending_bytes) is not int or max_pending_bytes <= 0:
            raise ValueError('invalid archive pending allowance')
        self.path = supplied.resolve()
        self.dispatch = dispatch
        self.closed = False
        with _REGISTRY_LOCK:
            actor = _REGISTRY.get(str(self.path))
            if actor is None:
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if not self.path.exists():
                    try:
                        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    except FileExistsError:
                        pass  # Another application process created this archive.
                    else:
                        os.close(fd)
                if self.path.is_symlink() or not self.path.is_file():
                    raise ValueError('content cache must be a regular file')
                actor = _Actor(self.path, max_pending_bytes)
                _REGISTRY[str(self.path)] = actor
                actor.start()
            with actor.condition:
                actor.check()
                actor.owners += 1
            self._actor = actor

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, kind, value, trace):
        self.close()

    def _open(self):
        if self.closed:
            raise ValueError('content cache is closed')

    @property
    def cleanup_diagnostic(self):
        return self._actor.cleanup_diagnostic

    def statistics(self):
        actor = self._actor
        with actor.condition:
            return dict(pending_bytes=actor.pending_bytes, pending_records=len(actor.pending),
                        max_pending_bytes=actor.max_pending_bytes, max_pending_records=_MAX_PENDING_RECORDS,
                        accepted_sequence=actor.accepted, durable_sequence=actor.durable,
                        failed=actor.error is not None, error=str(actor.error) if actor.error else None,
                        read_failures=actor.read_failures, read_busy_errors=actor.read_busy_errors,
                        last_read_code=actor.last_read_code,
                        writer_alive=actor.thread.is_alive(), commits=actor.commits,
                        pending_continuations=actor.continuations, max_pending_continuations=_MAX_CONTINUATIONS)

    def namespace(self, world_id):
        self._open()
        return type(self)(self.path, world_id, dispatch=self.dispatch,
                          max_pending_bytes=self._actor.max_pending_bytes)

    def put(self, kind, key, value, metadata=None):
        self._open()
        _kind(kind)
        if not isinstance(key, str) or not 1 <= len(key.encode('utf-8')) <= 512:
            raise ValueError('invalid cache key')
        if not isinstance(value, bytes) or len(value) > MAX_BYTES:
            raise ValueError('cache content must be bounded bytes')
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError('cache metadata must be an object')
        encoded = json_bytes(metadata or {})
        if len(encoded) > MAX_METADATA:
            raise ValueError('cache metadata exceeds allowance')
        return self._actor.enqueue(self.world_id, kind, key, value, encoded,
                                   hashlib.sha256(value).hexdigest())

    def put_batch_json(self, entries):
        """Accept 1..32 visible JSON writes atomically into this actor's FIFO.

        Entries are (world_id, kind, key, value), so one transaction may join
        namespaces in this same archive. Returned RAM heads remain provisional;
        only a real barrier acknowledges the complete group's durability.
        No SQL or dedup reads run on this caller path.
        """
        self._open()
        if type(entries) is not list:
            raise ValueError('cache JSON batch must contain 1..32 entries')
        # A producer may still own the supplied list. Serialization must not
        # observe later appends and create a group larger than one SQL batch.
        entries = tuple(entries[:_BATCH_RECORDS + 1])
        if not 1 <= len(entries) <= _BATCH_RECORDS:
            raise ValueError('cache JSON batch must contain 1..32 entries')
        prepared = []
        cost = 0
        for entry in entries:
            if type(entry) not in (tuple, list) or len(entry) != 4:
                raise ValueError('invalid cache JSON batch entry')
            world, kind, key, value = entry
            _world(world)
            _kind(kind)
            if not isinstance(key, str) or not 1 <= len(key.encode('utf-8')) <= 512:
                raise ValueError('invalid cache key')
            raw = json_bytes(value)
            if len(raw) > MAX_BYTES:
                raise ValueError('cache content must be bounded bytes')
            cost += len(raw) + 2
            # Bound serialized scratch before inspecting another entry. The
            # actor rechecks actual pending capacity atomically at acceptance.
            if cost > self._actor.max_pending_bytes:
                raise CacheBusy('content archive pending capacity is full')
            prepared.append((world, kind, key, raw, b'{}', hashlib.sha256(raw).hexdigest()))
        with self._actor.condition:
            self._open()
            return self._actor.enqueue_batch(prepared)

    def get(self, ref):
        self._open()
        world, ident, digest = reference_identity(ref)
        if world != self.world_id:
            return None
        actor = self._actor
        with actor.condition:
            pending = actor.pending.get(ident)
            if pending is not None and pending.world == world:
                if pending.digest != digest:
                    raise ValueError('cache reference digest mismatch')
                return pending.raw
        # A slow committed read must not own the queue/ACK condition. Records
        # are immutable; a concurrent pending->committed move is safe here.
        row = actor.query('SELECT payload,digest,size FROM records WHERE world=? AND id=?', (world, ident))
        return _unpack(row, ref, MAX_BYTES)

    def _head(self, kind, key, pending=True, hidden=False):
        actor = self._actor
        with actor.condition:
            if pending:
                ident = (actor.all_heads if hidden else actor.heads).get((self.world_id, kind, key))
                if ident is not None:
                    return actor.pending[ident].ref
        row = actor.query('SELECT r.id,r.digest FROM heads h JOIN records r ON r.id=h.id AND r.world=h.world WHERE h.world=? AND h.kind=? AND h.key=?',
                          (self.world_id, kind, key))
        with actor.condition:
            # Prefer a newer local overlay accepted during the committed read.
            if pending:
                ident = (actor.all_heads if hidden else actor.heads).get((self.world_id, kind, key))
                if ident is not None:
                    return actor.pending[ident].ref
            ref = None if row is None else f'alien-cache:v1:{self.world_id}:{row[0]}:{row[1]}'
            if not hidden:
                # COMMIT returns before the actor can retire its overlay and
                # resolve fences. Keep proposals private during that interval.
                while ref is not None:
                    previous = actor.pending.get(reference_identity(ref)[1])
                    if previous is None or not previous.hidden:
                        break
                    ref = previous.previous_ref
            return ref

    def get_json(self, kind, key, default=None):
        self._open()
        _kind(kind)
        ref = self._head(kind, key)
        return default if ref is None else _json(self.get(ref))

    def read_committed_json(self, kind, key, default=None):
        self._open()
        _kind(kind)
        row = self._actor.query('SELECT r.id,r.payload,r.digest,r.size FROM heads h JOIN records r ON r.id=h.id AND r.world=h.world WHERE h.world=? AND h.kind=? AND h.key=?',
                                (self.world_id, kind, key))
        if row is None:
            return default
        ref = f'alien-cache:v1:{self.world_id}:{row[0]}:{row[2]}'
        return _json(_unpack(row[1:], ref, MAX_BYTES))

    def _set_json(self, kind, key, value, hidden):
        self._open()
        _kind(kind)
        if not isinstance(key, str) or not 1 <= len(key.encode('utf-8')) <= 512:
            raise ValueError('invalid cache key')
        raw = json_bytes(value)
        if len(raw) > MAX_BYTES:
            raise ValueError('cache content must be bounded bytes')
        digest = hashlib.sha256(raw).hexdigest()
        actor = self._actor
        while True:
            with actor.condition:
                actor.check()
                revision = actor.accepted
            # Mutation ordering follows the actual FIFO head, including a
            # private proposal. A visible old value must still enqueue a
            # rollback after a newer staged value with different bytes.
            ref = self._head(kind, key, hidden=True)
            with actor.condition:
                actor.check()
                ident = actor.all_heads.get((self.world_id, kind, key))
                if ident is not None:
                    ref = actor.pending[ident].ref
                elif actor.accepted != revision:
                    # Another producer may have committed while SQL was in
                    # flight. Re-read rather than dedup against a stale head.
                    continue
                if ref is not None and reference_identity(ref)[2] == digest:
                    latest = actor.pending.get(reference_identity(ref)[1])
                    if hidden or latest is None or not latest.hidden:
                        return ref
                    # A visible write cannot reuse a private unacked record.
                return actor.enqueue(self.world_id, kind, key, raw, b'{}', digest, hidden,
                                     previous_ref=ref if hidden else None, state=True)

    def set_json(self, kind, key, value):
        return self._set_json(kind, key, value, False)

    def stage_json(self, kind, key, value):
        """Queue a private proposed head; normal head reads see it after ACK."""
        return self._set_json(kind, key, value, True)

    def append(self, kind, value, metadata=None):
        return self.put(kind, _ordered_id(),
                        value if isinstance(value, bytes) else json_bytes(value), metadata)

    def records(self, kind, limit=100):
        self._open()
        _kind(kind)
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError('invalid cache record limit')
        actor = self._actor
        while True:
            with actor.condition:
                revision = actor.accepted, actor.durable
                pending = [(row.ident, row.key, row.digest, len(row.raw), row.metadata, None)
                           for row in reversed(actor.pending.values()) if row.world == self.world_id and row.kind == kind]
            committed = actor.query('SELECT id,key,digest,size,metadata,seq FROM records WHERE world=? AND kind=? ORDER BY seq DESC LIMIT ?',
                                    (self.world_id, kind, limit), many=True)
            with actor.condition:
                if revision == (actor.accepted, actor.durable):
                    break
            # A newer local record may now be in the SQL result. Do not put
            # an older pending snapshot ahead of it (especially with limit=1).
        # SQLite can commit just before the actor retires its overlay. Deduping
        # preserves one record at that boundary without waiting for disk.
        seen, result = set(), []
        for ident, key, digest, size, metadata, sequence in pending + committed:
            if ident in seen:
                continue
            seen.add(ident)
            result.append(dict(cache_ref=f'alien-cache:v1:{self.world_id}:{ident}:{digest}',
                               kind=kind, key=key, size=size, metadata=_json(metadata), sequence=sequence))
            if len(result) == limit:
                break
        return result

    def flush_if_due(self):
        self._open()
        actor = self._actor
        with actor.condition:
            actor.check()
            if actor.pending and (len(actor.pending) >= _BATCH_RECORDS or
                                  time.monotonic() - actor.last_flush >= _FLUSH_SECONDS):
                actor.force = True
                actor.condition.notify()
        return True

    def barrier(self):
        self._open()
        return self._actor.barrier()

    def after_flush(self, success, error=None):
        self._open()
        actor = self._actor
        with actor.condition:
            if actor.continuations >= _MAX_CONTINUATIONS:
                raise CacheBusy('content archive continuation capacity is full')
            actor.continuations += 1
        dispatch = self.dispatch
        if dispatch is None:
            try:
                dispatch = asyncio.get_running_loop().call_soon_threadsafe
            except RuntimeError:
                pass
        try:
            future = self.barrier()
        except BaseException:
            with actor.condition:
                actor.continuations -= 1
            raise

        def completed(fence):
            released = False
            invoked = False

            def release():
                nonlocal released
                with actor.condition:
                    if not released:
                        actor.continuations -= 1
                        released = True

            exception = fence.exception()
            if exception is None:
                callback = success
            elif error is not None:
                callback = lambda: error(exception)
            else:
                release()
                return

            def invoke():
                nonlocal invoked
                with actor.condition:
                    if invoked:
                        return
                    invoked = True
                try:
                    callback()
                finally:
                    release()

            if dispatch is None:
                invoke()
            else:
                try:
                    dispatch(invoke)
                except BaseException:
                    release()
                    raise

        future.add_done_callback(completed)
        return future

    def flush(self, wait=True):
        """Blocking durable fence, for startup/shutdown and offline callers."""
        future = self.barrier()
        if wait:
            try:
                future.result(timeout=_CLOSE_SECONDS)
            except FutureTimeout as error:
                raise CacheBusy('content archive flush timed out; pending work is not acknowledged') from error
        return future

    def close(self):
        actor = self._actor
        with actor.condition:
            if self.closed:
                return
            self.closed = True
        deadline = time.monotonic() + _CLOSE_SECONDS
        with _REGISTRY_LOCK:
            with actor.condition:
                actor.owners -= 1
                last = actor.owners == 0
                if last:
                    actor.stopping = True
                    actor.stop_deadline = deadline
                    actor.condition.notify_all()
                failure = actor.error
        if not last:
            # A namespace owns no separate writer or durability promise. Its
            # queued work remains with the shared actor; the final owner drains.
            if failure is not None:
                raise failure
            return
        fence = actor.barrier()
        failure = None
        try:
            fence.result(timeout=max(0., deadline - time.monotonic()))
        except FutureTimeout:
            failure = CacheBusy('content archive close timed out; pending work is not acknowledged')
        except BaseException as error:
            failure = error
        if threading.current_thread() is actor.thread:
            raise ValueError('archive writer callbacks require dispatch before closing')
        actor.thread.join(timeout=max(0., deadline - time.monotonic()))
        if actor.thread.is_alive() and failure is None:
            failure = CacheBusy('content archive writer is still draining')
        if failure is not None:
            raise failure
