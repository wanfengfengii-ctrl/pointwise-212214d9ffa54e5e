import json
from dataclasses import asdict, dataclass

from release.provenance import CueOrigin


@dataclass(frozen=True)
class PlaybackEntry:
    seq: int
    show_id: str
    seat: str
    token: str
    origin: CueOrigin
    kind: str
    text: str
    amendment_id: str | None


def append_playback(db, command):
    detail = {
        'seat': command.seat,
        'origin': asdict(command.origin),
        'text': command.text,
        'amendment_id': command.amendment_id,
    }
    cursor = db.execute(
        'INSERT INTO playback (show_id, cue_id, kind, token, detail) VALUES (?, ?, ?, ?, ?)',
        (command.show_id, command.origin.cue_id, command.kind, command.token, json.dumps(detail)),
    )
    return PlaybackEntry(
        cursor.lastrowid, command.show_id, command.seat, command.token, command.origin,
        command.kind, command.text, command.amendment_id,
    )


def _entry(row):
    detail = json.loads(row['detail'])
    detail['origin'] = CueOrigin(**detail['origin'])
    return PlaybackEntry(seq=row['seq'], show_id=row['show_id'], token=row['token'], kind=row['kind'], **detail)


def find_playback(db, token):
    row = db.execute('SELECT * FROM playback WHERE token = ?', (token,)).fetchone()
    return _entry(row) if row is not None else None


def find_original(db, show_id, cue_id):
    row = db.execute(
        "SELECT * FROM playback WHERE show_id = ? AND cue_id = ? AND kind = 'original'", (show_id, cue_id)
    ).fetchone()
    return _entry(row) if row is not None else None


def list_playback(db, show_id):
    return [_entry(row) for row in db.execute('SELECT * FROM playback WHERE show_id = ? ORDER BY seq', (show_id,))]
