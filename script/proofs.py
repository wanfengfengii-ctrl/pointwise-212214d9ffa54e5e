import json
from dataclasses import asdict, dataclass

from script.cues import CueFieldError, parse_cues
from script.drafts import get_revision, save_revision
from script.timing import CueInterval, build_intervals, find_conflicts


@dataclass(frozen=True)
class ProofResult:
    draft_id: str
    revision: int
    passed: bool
    intervals: list[CueInterval]
    conflicts: list[dict]
    field_errors: list[dict]


def initialize_proofs(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS proofs (
            draft_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
            result TEXT NOT NULL,
            PRIMARY KEY (draft_id, revision),
            FOREIGN KEY (draft_id, revision) REFERENCES draft_revisions(draft_id, revision)
        )
    ''')


def proof(db, draft_id, raw_cues):
    revision = save_revision(db, draft_id, raw_cues)
    try:
        cues = parse_cues(revision.raw_cues)
    except CueFieldError as error:
        result = ProofResult(draft_id, revision.revision, False, [], [], error.issues)
    else:
        intervals = build_intervals(cues)
        conflicts = find_conflicts(intervals)
        result = ProofResult(draft_id, revision.revision, not conflicts, intervals, conflicts, [])
    db.execute(
        'INSERT INTO proofs VALUES (?, ?, ?, ?)',
        (draft_id, result.revision, result.passed, json.dumps(asdict(result))),
    )
    return result


def get_passed_revision(db, draft_id, revision):
    row = db.execute(
        'SELECT passed FROM proofs WHERE draft_id = ? AND revision = ?',
        (draft_id, revision),
    ).fetchone()
    if row is None or not row[0]:
        return None
    return get_revision(db, draft_id, revision)
