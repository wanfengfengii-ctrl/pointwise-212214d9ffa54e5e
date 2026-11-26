import json
from dataclasses import asdict, dataclass

from script.cues import Cue, parse_cues


@dataclass(frozen=True)
class Edition:
    edition_id: str
    draft_id: str
    revision: int
    cues: tuple[Cue, ...]


def initialize_editions(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS editions (
            edition_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            cues TEXT NOT NULL,
            FOREIGN KEY (draft_id, revision) REFERENCES draft_revisions(draft_id, revision)
        )
    ''')


def freeze_edition(db, edition_id, revision):
    cues = parse_cues(revision.raw_cues)
    db.execute(
        'INSERT INTO editions VALUES (?, ?, ?, ?)',
        (edition_id, revision.draft_id, revision.revision, json.dumps([asdict(cue) for cue in cues])),
    )
    return Edition(edition_id, revision.draft_id, revision.revision, cues)


def get_edition(db, edition_id):
    row = db.execute(
        'SELECT draft_id, revision, cues FROM editions WHERE edition_id = ?', (edition_id,)
    ).fetchone()
    if row is None:
        raise LookupError(edition_id)
    return Edition(edition_id, row[0], row[1], tuple(Cue(**item) for item in json.loads(row[2])))
