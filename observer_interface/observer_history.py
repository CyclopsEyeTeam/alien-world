"""Sight-owned public observation history. This module never talks to Alien."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time
import uuid

EVENT_KINDS = frozenset(('frame', 'note', 'word_intent', 'word_receipt', 'word_error'))
PHASES = frozenset(('awaiting_acknowledgement', 'active', 'closed', 'expired', 'offer_expired', 'unavailable'))
BINDING_KEYS = ('world_id', 'runtime', 'segment_id', 'pid', 'window_id', 'size', 'crop', 'binding')
MAX_RECORD_BYTES = 32768


def _text(value, label, maximum=128):
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > maximum or '\x00' in value:
        raise ValueError(f'{label} must be nonempty text of at most {maximum} UTF-8 bytes')
    return value


def _json(value, maximum=MAX_RECORD_BYTES):
    try: raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error: raise ValueError('History requires finite JSON values') from error
    if len(raw.encode('utf-8')) > maximum: raise ValueError('History record exceeds storage limit')
    return raw


def _limit(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum: raise ValueError(f'History limit must be 1..{maximum}')
    return value


def process_start(pid=None):
    """Linux process-generation token; absent evidence never establishes liveness."""
    try: return Path(f'/proc/{pid or os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError): return None


class ObserverJournal:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.connection = None
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Observer history needs an owner-only directory')
        path = self.root / 'observers.sqlite3'
        try: fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as error: raise ValueError('Observer history database is unavailable or unsafe') from error
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
                raise ValueError('Observer history needs an owner-only regular database')
        finally: os.close(fd)
        self.connection = sqlite3.connect(str(path), timeout=1., check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA synchronous=FULL')
            self.connection.executescript('''
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS visits (
                    id TEXT PRIMARY KEY, observer_id TEXT NOT NULL REFERENCES profiles(id),
                    profile_name TEXT NOT NULL, phase TEXT NOT NULL, started_monotonic REAL,
                    duration REAL NOT NULL, updated_at REAL NOT NULL, process_pid INTEGER NOT NULL,
                    process_start TEXT, binding TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    visit_id TEXT NOT NULL REFERENCES visits(id), kind TEXT NOT NULL,
                    created_at REAL NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS visit_events ON events(visit_id, sequence);
                CREATE INDEX IF NOT EXISTS recent_visits ON visits(updated_at);
            ''')
            with self.connection:
                self.connection.execute('INSERT OR IGNORE INTO profiles VALUES (?, ?, ?, ?)',
                                        ('observer-agent', 'Observer agent', 'mcp', time.time()))
        except Exception:
            self.close()
            raise

    def close(self):
        with self.lock:
            if self.connection is not None:
                self.connection.close()
                self.connection = None

    def list_profiles(self):
        with self.lock:
            return [dict(row) for row in self.connection.execute('SELECT * FROM profiles ORDER BY created_at, id')]

    def add_profile(self, name, kind='mcp'):
        name, kind = _text(name, 'Profile name'), _text(kind, 'Profile kind', 64)
        profile = dict(id=uuid.uuid4().hex, name=name, kind=kind, created_at=time.time())
        with self.lock, self.connection:
            self.connection.execute('INSERT INTO profiles VALUES (:id, :name, :kind, :created_at)', profile)
        return profile

    def save_visit(self, visit_id, binding, phase, started=None, duration=93, observer_id='observer-agent'):
        _text(visit_id, 'Visit ID')
        _text(observer_id, 'Observer ID')
        if phase not in PHASES: raise ValueError('Unknown observation phase')
        if not isinstance(binding, dict): raise ValueError('Observation binding must be an object')
        safe_binding = _json({key: binding[key] for key in BINDING_KEYS if key in binding}, maximum=8192)
        if (type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 3600
                or started is not None and (type(started) not in (int, float) or not math.isfinite(started) or started < 0)):
            raise ValueError('Observation clock must be finite and bounded')
        with self.lock, self.connection:
            profile = self.connection.execute('SELECT name FROM profiles WHERE id=?', (observer_id,)).fetchone()
            if profile is None: raise ValueError('Unknown observer profile')
            previous = self.connection.execute('SELECT * FROM visits WHERE id=?', (visit_id,)).fetchone()
            if previous:
                if previous['binding'] != safe_binding or previous['observer_id'] != observer_id or previous['duration'] != duration:
                    raise ValueError('Visit ID already belongs to a different observation')
                if previous['started_monotonic'] is not None:
                    if started is not None and started != previous['started_monotonic']:
                        raise ValueError('Observation start cannot be changed')
                    started = previous['started_monotonic']
                self.connection.execute('UPDATE visits SET phase=?, started_monotonic=?, updated_at=? WHERE id=?',
                                        (phase, started, time.time(), visit_id))
            else:
                self.connection.execute('INSERT INTO visits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (visit_id, observer_id, profile['name'], phase, started, duration, time.time(),
                     os.getpid(), process_start(), safe_binding))
            return self._visit(self.connection.execute('SELECT * FROM visits WHERE id=?', (visit_id,)).fetchone())

    @staticmethod
    def _visit(row):
        result = dict(row)
        result['binding'] = json.loads(result['binding'])
        return result

    @staticmethod
    def _event(row):
        result = {key: row[key] for key in ('id', 'visit_id', 'kind', 'created_at', 'payload')}
        result['payload'] = json.loads(result['payload'])
        return result

    def record(self, visit_id, kind, payload, event_id=None):
        _text(visit_id, 'Visit ID')
        if kind not in EVENT_KINDS: raise ValueError('Unknown observation event kind')
        if not isinstance(payload, dict): raise ValueError('History payload must be an object')
        encoded = _json(payload)
        event_id = _text(event_id, 'Event ID') if event_id is not None else uuid.uuid4().hex
        with self.lock, self.connection:
            previous = self.connection.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            if previous:
                if (previous['visit_id'], previous['kind'], previous['payload']) != (visit_id, kind, encoded):
                    raise ValueError('Event ID already belongs to different history')
                return self._event(previous)
            if not self.connection.execute('SELECT 1 FROM visits WHERE id=?', (visit_id,)).fetchone():
                raise ValueError('Unknown observation visit')
            self.connection.execute('INSERT INTO events(id,visit_id,kind,created_at,payload) VALUES (?, ?, ?, ?, ?)',
                                    (event_id, visit_id, kind, time.time(), encoded))
            return self._event(self.connection.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone())

    def recent_visits(self, limit=50):
        with self.lock:
            return [self._visit(row) for row in self.connection.execute(
                'SELECT * FROM visits ORDER BY updated_at DESC, id LIMIT ?', (_limit(limit, 200),))]

    def events(self, visit_id, limit=200):
        _text(visit_id, 'Visit ID')
        with self.lock:
            rows = self.connection.execute('SELECT * FROM events WHERE visit_id=? ORDER BY sequence DESC LIMIT ?',
                                           (visit_id, _limit(limit, 1000))).fetchall()
            return [self._event(row) for row in reversed(rows)]
