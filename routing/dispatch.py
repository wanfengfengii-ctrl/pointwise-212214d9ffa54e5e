import json
from dataclasses import asdict, dataclass

from release.editions import get_edition
from release.provenance import CueOrigin, make_cue_origin


@dataclass(frozen=True)
class DispatchRecord:
    show_id: str
    seat: str
    token: str
    text: str
    origin: CueOrigin


def initialize_dispatch(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS dispatches (
            token TEXT PRIMARY KEY,
            show_id TEXT NOT NULL,
            seat TEXT NOT NULL,
            position INTEGER NOT NULL,
            text TEXT NOT NULL,
            origin TEXT NOT NULL,
            UNIQUE (show_id, seat, position),
            FOREIGN KEY (show_id, seat) REFERENCES enabled_seats(show_id, seat)
        )
    ''')


def record_dispatch(db, show, seat, position):
    edition = get_edition(db, show.edition_id)
    if position > len(edition.cues):
        return None
    cue = edition.cues[position - 1]
    origin = make_cue_origin(edition, cue)
    token = json.dumps(['original', show.show_id, seat, cue.cue_id], separators=(',', ':'))
    db.execute(
        'INSERT INTO dispatches VALUES (?, ?, ?, ?, ?, ?)',
        (token, show.show_id, seat, position, cue.text, json.dumps(asdict(origin))),
    )
    return DispatchRecord(show.show_id, seat, token, cue.text, origin)


def get_dispatch(db, token):
    row = db.execute('SELECT show_id, seat, text, origin FROM dispatches WHERE token = ?', (token,)).fetchone()
    if row is None:
        return None
    return DispatchRecord(row[0], row[1], token, row[2], CueOrigin(**json.loads(row[3])))
