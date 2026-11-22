"""Sight-owned installed observer channels and finite owner Connect grants.

Registration records a host binding, never proof that an agent is online. A
Connect request neither opens an image nor starts the observation clock.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from observer_history import _text

CHANNEL_FIELDS = ('id', 'observer_id', 'name', 'host_kind', 'thread_id')
REQUEST_FIELDS = ('id', 'channel_id', 'observer_id', 'state', 'created_at',
                  'expires_at', 'visit_id', 'error')
TERMINAL_STATES = frozenset(('completed', 'cancelled', 'failed', 'expired'))
QUEUE_SECONDS = 300.
WAKE_TIMEOUT = 5.
CODEX_BINARY = shutil.which('codex') or shutil.which('codex', path=str(Path.home() / '.local/bin')) or 'codex'


def _read_process_start(pid):
    if type(pid) is not int or pid <= 0: return None
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[19] if fields[0] not in ('Z', 'X') and fields[19].isdigit() else None
    except (OSError, IndexError): return None


class ChannelRegistry:
    def __init__(self, journal, *, clock=time.time, monotonic=time.monotonic,
                 process_reader=_read_process_start, runner=subprocess.run):
        self.journal, self.clock, self.runner = journal, clock, runner
        self.monotonic, self.process_reader = monotonic, process_reader
        with journal.lock:
            journal.connection.executescript('''
                CREATE TABLE IF NOT EXISTS observer_channels (
                    id TEXT PRIMARY KEY,
                    observer_id TEXT UNIQUE NOT NULL REFERENCES profiles(id),
                    name TEXT NOT NULL,
                    host_kind TEXT NOT NULL CHECK(host_kind IN ('codex_queue', 'mcp_wait')),
                    thread_id TEXT, created_at REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS observer_channel_binding
                    ON observer_channels(host_kind, thread_id) WHERE thread_id IS NOT NULL;
                CREATE UNIQUE INDEX IF NOT EXISTS observer_wait_channel_name
                    ON observer_channels(host_kind, name) WHERE thread_id IS NULL;
                CREATE TABLE IF NOT EXISTS connect_requests (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL REFERENCES observer_channels(id),
                    observer_id TEXT NOT NULL REFERENCES profiles(id),
                    state TEXT NOT NULL CHECK(state IN
                        ('pending', 'notified', 'claimed', 'completed', 'cancelled', 'failed', 'expired')),
                    created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    visit_id TEXT UNIQUE REFERENCES visits(id), error TEXT,
                    wake_attempted_at REAL, claimant_id TEXT, offer_deadline_monotonic REAL);
                CREATE UNIQUE INDEX IF NOT EXISTS active_channel_connect
                    ON connect_requests(channel_id) WHERE state IN ('pending', 'notified', 'claimed');
            ''')
            with journal.connection:
                journal.connection.execute('BEGIN IMMEDIATE')
                columns = {row['name'] for row in journal.connection.execute('PRAGMA table_info(connect_requests)')}
                for name, kind in (('claimant_id', 'TEXT'), ('offer_deadline_monotonic', 'REAL')):
                    if name not in columns:
                        journal.connection.execute(f'ALTER TABLE connect_requests ADD COLUMN {name} {kind}')

    @contextmanager
    def _transaction(self):
        # The shared journal lock protects its one connection. BEGIN IMMEDIATE
        # also serializes brokers in separate MCP/window processes.
        with self.journal.lock:
            connection = self.journal.connection
            if connection is None: raise ValueError('Observer history is closed')
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                yield connection

    def _now(self):
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Channel clock must be finite')
        return value

    @staticmethod
    def _channel(connection, channel_id):
        _text(channel_id, 'Channel ID')
        row = connection.execute('SELECT * FROM observer_channels WHERE id=?', (channel_id,)).fetchone()
        if row is None: raise ValueError('Unknown installed observer channel')
        return {key: row[key] for key in CHANNEL_FIELDS}

    @staticmethod
    def _request(connection, request_id):
        _text(request_id, 'Connect request ID')
        row = connection.execute('SELECT * FROM connect_requests WHERE id=?', (request_id,)).fetchone()
        if row is None: raise ValueError('Unknown owner Connect request')
        return {key: row[key] for key in REQUEST_FIELDS}

    @staticmethod
    def _finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    @staticmethod
    def _claimant(connection, request_id, claimant_id):
        if claimant_id is not None: _text(claimant_id, 'MCP connection claimant ID')
        stored = connection.execute('SELECT claimant_id FROM connect_requests WHERE id=?',
                                    (request_id,)).fetchone()[0]
        if stored != claimant_id:
            raise ValueError('Owner Connect request is claimed by another MCP connection')

    def _expire(self, connection):
        connection.execute("""UPDATE connect_requests SET state='expired', error='Owner Connect request expired'
            WHERE expires_at<=? AND visit_id IS NULL AND state IN ('pending', 'notified', 'claimed')""",
            (self._now(),))
        # Reconcile missed finish bookkeeping without touching the observation
        # history or its native lease. A recorded phase alone is not liveness.
        rows = connection.execute("""SELECT r.id, r.offer_deadline_monotonic, v.*
            FROM connect_requests r JOIN visits v ON v.id=r.visit_id WHERE r.state='claimed'""").fetchall()
        for row in rows:
            phase = row['phase']
            state = dict(closed='completed', expired='completed', offer_expired='expired', unavailable='failed').get(phase)
            if state is None:
                try: actual = self.process_reader(row['process_pid'])
                except (OSError, ValueError, TypeError): actual = None
                token = row['process_start']
                if not isinstance(token, str) or not token.isdigit() or actual != token:
                    state = 'failed'
                elif phase == 'active':
                    start, duration, now = row['started_monotonic'], row['duration'], self.monotonic()
                    if (not all(self._finite(value) for value in (start, duration, now))
                            or start < 0 or now < start or not 0 < duration <= 93):
                        state = 'failed'
                    elif now >= start + duration:
                        state = 'completed'
                elif phase == 'awaiting_acknowledgement':
                    deadline, now = row['offer_deadline_monotonic'], self.monotonic()
                    if deadline is None:
                        # Pre-migration requests have only the original visit
                        # offer timestamp; retain their bounded remaining offer.
                        if self._now() >= row['updated_at'] + QUEUE_SECONDS: state = 'expired'
                    elif not self._finite(deadline) or not self._finite(now) or now < 0:
                        state = 'failed'
                    elif now >= deadline:
                        state = 'expired'
                else:
                    state = 'failed'
            if state is not None:
                connection.execute('UPDATE connect_requests SET state=?, error=? WHERE id=?',
                                   (state, 'Observation visit is no longer live', row['id']))

    def register(self, name, host_kind, thread_id=None):
        name = _text(name, 'Observer name').strip()
        if host_kind not in ('codex_queue', 'mcp_wait'):
            raise ValueError('Supported observer hosts are codex_queue and mcp_wait')
        if host_kind == 'codex_queue':
            _text(thread_id, 'Existing Codex thread ID')
            try: binding = str(uuid.UUID(thread_id))
            except (ValueError, AttributeError) as error:
                raise ValueError('Codex channel requires an existing thread UUID') from error
            if binding != thread_id.lower():
                raise ValueError('Codex channel requires a canonical thread UUID')
            thread_id = binding
        elif thread_id is not None:
            thread_id = _text(thread_id, 'MCP host binding')
        with self._transaction() as connection:
            if thread_id is None:
                previous = connection.execute('''SELECT * FROM observer_channels
                    WHERE host_kind=? AND thread_id IS NULL AND name=?''', (host_kind, name)).fetchone()
            else:
                previous = connection.execute('''SELECT * FROM observer_channels
                    WHERE host_kind=? AND thread_id=?''', (host_kind, thread_id)).fetchone()
            if previous:
                connection.execute('UPDATE observer_channels SET name=? WHERE id=?', (name, previous['id']))
                connection.execute('UPDATE profiles SET name=? WHERE id=?', (name, previous['observer_id']))
                return self._channel(connection, previous['id'])
            channel_id, observer_id, now = uuid.uuid4().hex, uuid.uuid4().hex, self._now()
            connection.execute('INSERT INTO profiles VALUES (?, ?, ?, ?)', (observer_id, name, 'mcp', now))
            connection.execute('INSERT INTO observer_channels VALUES (?, ?, ?, ?, ?, ?)',
                               (channel_id, observer_id, name, host_kind, thread_id, now))
            return self._channel(connection, channel_id)

    def list_installed(self):
        with self.journal.lock:
            return [{key: row[key] for key in CHANNEL_FIELDS} for row in self.journal.connection.execute(
                'SELECT * FROM observer_channels ORDER BY created_at, id')]

    def request_connect(self, channel_id):
        with self._transaction() as connection:
            channel = self._channel(connection, channel_id)
            self._expire(connection)
            previous = connection.execute('''SELECT id FROM connect_requests
                WHERE channel_id=? AND state IN ('pending', 'notified', 'claimed')''', (channel_id,)).fetchone()
            if previous: return self._request(connection, previous['id'])
            request_id, now = uuid.uuid4().hex, self._now()
            connection.execute('''INSERT INTO connect_requests
                (id, channel_id, observer_id, state, created_at, expires_at) VALUES (?, ?, ?, 'pending', ?, ?)''',
                (request_id, channel_id, channel['observer_id'], now, now + QUEUE_SECONDS))
            return self._request(connection, request_id)

    def get(self, request_id):
        with self._transaction() as connection:
            self._expire(connection)
            return self._request(connection, request_id)

    def pending(self, channel_id):
        with self._transaction() as connection:
            self._channel(connection, channel_id)
            self._expire(connection)
            row = connection.execute('''SELECT id FROM connect_requests
                WHERE channel_id=? AND state IN ('pending', 'notified')''', (channel_id,)).fetchone()
            return self._request(connection, row['id']) if row else None

    def wake(self, request_id):
        with self._transaction() as connection:
            self._expire(connection)
            request = self._request(connection, request_id)
            channel = self._channel(connection, request['channel_id'])
            attempted = connection.execute('SELECT wake_attempted_at FROM connect_requests WHERE id=?',
                                           (request_id,)).fetchone()[0]
            if request['state'] != 'pending' or attempted is not None or channel['host_kind'] == 'mcp_wait':
                return request
            # Persist the attempt before releasing the lock: retries and a
            # second process cannot launch duplicate host notifications.
            connection.execute('UPDATE connect_requests SET wake_attempted_at=? WHERE id=?',
                               (self._now(), request_id))
        notice = (f'Owner Connect request {request_id} for installed observer channel {channel["id"]}. '
                  'Read alien_observer_pending and claim this matching request with alien_observer_claim '
                  'before opening an observation. The 93 second clock starts only after verified image acknowledgement.')
        argv = [CODEX_BINARY, 'queue', '--thread', channel['thread_id'], '--message', notice]
        error = None
        try:
            result = self.runner(argv, timeout=WAKE_TIMEOUT, shell=False, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if result.returncode != 0: error = 'Codex host notification failed'
        except subprocess.TimeoutExpired:
            error = 'Codex host notification timed out'
        except OSError:
            error = 'Codex host notification is unavailable'
        with self._transaction() as connection:
            self._expire(connection)
            current = self._request(connection, request_id)
            # An agent may already have claimed independently, or the owner may
            # have cancelled while the bounded host call was in progress.
            if current['state'] == 'pending':
                connection.execute('UPDATE connect_requests SET state=?, error=? WHERE id=?',
                                   ('failed' if error else 'notified', error, request_id))
            return self._request(connection, request_id)

    def claim(self, channel_id, request_id, claimant_id=None):
        if claimant_id is not None: _text(claimant_id, 'MCP connection claimant ID')
        # Commit expiry before reporting a rejected grant.
        self.get(request_id)
        with self._transaction() as connection:
            self._channel(connection, channel_id)
            self._expire(connection)
            request = self._request(connection, request_id)
            if request['channel_id'] != channel_id:
                raise ValueError('Owner Connect request belongs to another channel')
            if request['state'] not in ('pending', 'notified', 'claimed'):
                raise ValueError('Owner Connect request is no longer available')
            if request['state'] == 'claimed': self._claimant(connection, request_id, claimant_id)
            connection.execute("UPDATE connect_requests SET state='claimed', claimant_id=? WHERE id=?",
                               (claimant_id, request_id))
            return self._request(connection, request_id)

    def attach_visit(self, request_id, visit_id, claimant_id=None, offer_deadline=None):
        _text(visit_id, 'Visit ID')
        self.get(request_id)
        with self._transaction() as connection:
            self._expire(connection)
            request = self._request(connection, request_id)
            if request['state'] != 'claimed': raise ValueError('Claim the owner Connect request before opening')
            self._claimant(connection, request_id, claimant_id)
            if request['visit_id'] is not None and request['visit_id'] != visit_id:
                raise ValueError('Owner Connect request already belongs to another visit')
            visit = connection.execute('SELECT observer_id FROM visits WHERE id=?', (visit_id,)).fetchone()
            if visit is None or visit['observer_id'] != request['observer_id']:
                raise ValueError('Observation visit belongs to another observer or is unavailable')
            previous_deadline = connection.execute('SELECT offer_deadline_monotonic FROM connect_requests WHERE id=?',
                                                   (request_id,)).fetchone()[0]
            deadline = previous_deadline if request['visit_id'] is not None else offer_deadline
            now = self.monotonic()
            if deadline is None: deadline = now + QUEUE_SECONDS
            if (not self._finite(deadline) or not self._finite(now) or now < 0
                    or request['visit_id'] is None and not now < deadline <= now + QUEUE_SECONDS):
                raise ValueError('Image offer deadline is invalid or expired')
            if (request['visit_id'] is not None and offer_deadline is not None
                    and offer_deadline != previous_deadline):
                raise ValueError('Image offer deadline cannot be changed')
            connection.execute('UPDATE connect_requests SET visit_id=?, offer_deadline_monotonic=? WHERE id=?',
                               (visit_id, deadline, request_id))
            return self._request(connection, request_id)

    def finish(self, request_id, state, claimant_id=None):
        if state not in TERMINAL_STATES: raise ValueError('Connect finish state must be terminal')
        with self._transaction() as connection:
            self._expire(connection)
            request = self._request(connection, request_id)
            self._claimant(connection, request_id, claimant_id)
            if request['state'] in TERMINAL_STATES:
                if request['state'] != state: raise ValueError('Connect request is already terminal')
                return request
            connection.execute('UPDATE connect_requests SET state=? WHERE id=?', (state, request_id))
            return self._request(connection, request_id)

    def wait(self, channel_id, timeout=60):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= QUEUE_SECONDS:
            raise ValueError('Observer wait timeout must be finite and between 0 and 300 seconds')
        deadline = time.monotonic() + timeout
        while True:
            request = self.pending(channel_id)
            if request is not None: return request
            remaining = deadline - time.monotonic()
            if remaining <= 0: return None
            # Polling sees other MCP/window processes too; never sleep while
            # holding the journal connection lock.
            time.sleep(min(.05, remaining))
