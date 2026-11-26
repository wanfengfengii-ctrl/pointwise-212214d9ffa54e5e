from contextlib import contextmanager
from dataclasses import dataclass


class ApiError(Exception):
    def __init__(self, status, code, details=None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.details = details


@contextmanager
def control_write(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


@dataclass(frozen=True)
class Show:
    show_id: str
    edition_id: str
    closed: bool


def initialize_shows(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS shows (
            show_id TEXT PRIMARY KEY,
            edition_id TEXT NOT NULL UNIQUE REFERENCES editions(edition_id),
            closed INTEGER NOT NULL DEFAULT 0 CHECK (closed IN (0, 1))
        )
    ''')


def bind_show(db, show_id, edition_id):
    db.execute('INSERT INTO shows (show_id, edition_id) VALUES (?, ?)', (show_id, edition_id))
    return Show(show_id, edition_id, False)


def get_show(db, show_id):
    row = db.execute('SELECT edition_id, closed FROM shows WHERE show_id = ?', (show_id,)).fetchone()
    if row is None:
        raise ApiError(404, 'unknown_show')
    return Show(show_id, row[0], bool(row[1]))


def require_open_show(db, show_id):
    show = get_show(db, show_id)
    if show.closed:
        raise ApiError(409, 'show_closed')
    return show


def mark_show_closed(db, show_id):
    db.execute('UPDATE shows SET closed = 1 WHERE show_id = ?', (show_id,))
