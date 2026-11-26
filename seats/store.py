import sqlite3
from contextlib import closing, contextmanager
from threading import Lock


class SeatUnavailable(Exception):
    """The seat store cannot currently confirm an operation."""


class SeatStore:
    def __init__(self, path, seat):
        self.path = path
        self.seat = seat
        self._init_lock = Lock()
        self._initialized = False

    def initialize(self):
        with self._init_lock:
            if self._initialized:
                return
            with self.reopen() as db:
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS commands (
                        token TEXT PRIMARY KEY,
                        body TEXT NOT NULL,
                        consumed INTEGER NOT NULL DEFAULT 0 CHECK (consumed IN (0, 1))
                    );
                    CREATE TABLE IF NOT EXISTS playback (
                        seq INTEGER PRIMARY KEY,
                        show_id TEXT NOT NULL,
                        cue_id TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK (kind IN ('original', 'replacement', 'erratum')),
                        token TEXT NOT NULL UNIQUE REFERENCES commands(token),
                        detail TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS playback_show_sequence ON playback(show_id, seq);
                    CREATE UNIQUE INDEX IF NOT EXISTS one_original_play
                        ON playback(show_id, cue_id) WHERE kind = 'original';
                    CREATE TABLE IF NOT EXISTS play_receipts (
                        request_id TEXT PRIMARY KEY,
                        token TEXT NOT NULL UNIQUE REFERENCES playback(token)
                    );
                ''')
            self._initialized = True

    @contextmanager
    def reopen(self):
        try:
            with closing(sqlite3.connect(self.path, isolation_level=None, timeout=2.0)) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA foreign_keys = ON')
                yield db
        except sqlite3.OperationalError as error:
            base_code = getattr(error, 'sqlite_errorcode', 0) & 255
            if base_code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_IOERR):
                raise SeatUnavailable(self.seat) from error
            raise

    @contextmanager
    def transaction(self):
        with self.reopen() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
