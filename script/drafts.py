import json
from dataclasses import dataclass


@dataclass(frozen=True)
class DraftRevision:
    draft_id: str
    revision: int
    raw_cues: object


def initialize_drafts(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS draft_revisions (
            draft_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            raw_cues TEXT NOT NULL,
            PRIMARY KEY (draft_id, revision)
        )
    ''')


def save_revision(db, draft_id, raw_cues):
    row = db.execute(
        'SELECT COALESCE(MAX(revision), 0) FROM draft_revisions WHERE draft_id = ?',
        (draft_id,),
    ).fetchone()
    revision = row[0] + 1
    db.execute(
        'INSERT INTO draft_revisions VALUES (?, ?, ?)',
        (draft_id, revision, json.dumps(raw_cues)),
    )
    return DraftRevision(draft_id, revision, raw_cues)


def get_revision(db, draft_id, revision):
    row = db.execute(
        'SELECT raw_cues FROM draft_revisions WHERE draft_id = ? AND revision = ?',
        (draft_id, revision),
    ).fetchone()
    if row is None:
        return None
    return DraftRevision(draft_id, revision, json.loads(row[0]))
