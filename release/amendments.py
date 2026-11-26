import json
from dataclasses import asdict, dataclass

from release.provenance import CueOrigin, resolve_original_cue
from routing.enrollment import list_enabled_seats
from routing.shows import ApiError, control_write, require_open_show
from seats.execution import AmendmentInstruction, accept_seat_instruction
from seats.store import SeatUnavailable


@dataclass(frozen=True)
class Amendment:
    show_id: str
    amendment_id: str
    origin: CueOrigin
    corrected_text: str
    erratum_text: str
    seats: dict


def initialize_amendments(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS amendments (
            show_id TEXT NOT NULL REFERENCES shows(show_id),
            amendment_id TEXT NOT NULL,
            cue_id TEXT NOT NULL,
            origin TEXT NOT NULL,
            corrected_text TEXT NOT NULL,
            erratum_text TEXT NOT NULL,
            PRIMARY KEY (show_id, amendment_id),
            UNIQUE (show_id, cue_id)
        );
        CREATE TABLE IF NOT EXISTS amendment_notices (
            show_id TEXT NOT NULL,
            amendment_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('replacement', 'erratum')),
            PRIMARY KEY (show_id, amendment_id),
            FOREIGN KEY (show_id, amendment_id) REFERENCES amendments(show_id, amendment_id)
        );
        CREATE TABLE IF NOT EXISTS amendment_seats (
            show_id TEXT NOT NULL,
            amendment_id TEXT NOT NULL,
            seat TEXT NOT NULL,
            play_token TEXT,
            evidence TEXT,
            PRIMARY KEY (show_id, amendment_id, seat),
            FOREIGN KEY (show_id, amendment_id) REFERENCES amendments(show_id, amendment_id),
            FOREIGN KEY (show_id, seat) REFERENCES enabled_seats(show_id, seat)
        );
    ''')


def get_amendment(db, show_id, amendment_id):
    row = db.execute(
        'SELECT origin, corrected_text, erratum_text FROM amendments WHERE show_id = ? AND amendment_id = ?',
        (show_id, amendment_id),
    ).fetchone()
    if row is None:
        return None
    seat_rows = db.execute('''
        SELECT a.seat, a.play_token, a.evidence FROM amendment_seats AS a
        JOIN enabled_seats AS e ON e.show_id = a.show_id AND e.seat = a.seat
        WHERE a.show_id = ? AND a.amendment_id = ? ORDER BY e.position
    ''', (show_id, amendment_id))
    seats = {
        seat: {'play_token': token, 'evidence': json.loads(evidence) if evidence is not None else None}
        for seat, token, evidence in seat_rows
    }
    return Amendment(show_id, amendment_id, CueOrigin(**json.loads(row[0])), row[1], row[2], seats)


def list_show_amendments(db, show_id):
    rows = db.execute('SELECT amendment_id FROM amendments WHERE show_id = ? ORDER BY amendment_id', (show_id,))
    return [get_amendment(db, show_id, row[0]) for row in rows]


def _intake(db, show_id, amendment_id, cue_id, corrected_text, erratum_text):
    current = get_amendment(db, show_id, amendment_id)
    if current is not None:
        original = (current.origin.cue_id, current.corrected_text, current.erratum_text)
        if original != (cue_id, corrected_text, erratum_text):
            raise ApiError(409, 'request_mismatch')
        return current

    show = require_open_show(db, show_id)
    resolved = resolve_original_cue(db, show.edition_id, cue_id)
    if resolved is None:
        raise ApiError(404, 'unknown_original_cue')
    if db.execute('SELECT 1 FROM amendments WHERE show_id = ? AND cue_id = ?', (show_id, cue_id)).fetchone():
        raise ApiError(409, 'original_already_amended')
    _, origin = resolved
    db.execute(
        'INSERT INTO amendments VALUES (?, ?, ?, ?, ?, ?)',
        (show_id, amendment_id, cue_id, json.dumps(asdict(origin)), corrected_text, erratum_text),
    )
    db.executemany(
        'INSERT INTO amendment_seats (show_id, amendment_id, seat) VALUES (?, ?, ?)',
        [(show_id, amendment_id, seat) for seat in list_enabled_seats(db, show_id)],
    )
    return get_amendment(db, show_id, amendment_id)


def _notice(db, order):
    key = (order.show_id, order.amendment_id)
    previous = db.execute(
        'SELECT kind FROM amendment_notices WHERE show_id = ? AND amendment_id = ?', key,
    ).fetchone()
    if previous is None:
        issued = db.execute(
            'SELECT 1 FROM dispatches WHERE show_id = ? AND position = ? LIMIT 1',
            (order.show_id, order.origin.position),
        ).fetchone()
        kind = 'erratum' if issued is not None else 'replacement'
        db.execute('INSERT INTO amendment_notices VALUES (?, ?, ?)', (*key, kind))
    else:
        kind = previous[0]
    text = order.erratum_text if kind == 'erratum' else order.corrected_text
    return AmendmentInstruction(order.show_id, order.amendment_id, order.origin, text, kind)


def record_seat_evidence(db, order, seat, instruction, acceptance):
    if acceptance.token is None:
        return
    evidence = None
    if acceptance.receipt is not None:
        entry = acceptance.receipt.playback
        evidence = json.dumps({
            'status': instruction.kind + '_played', 'original_seq': None, 'amendment_seq': entry.seq,
        })

    key = (order.show_id, order.amendment_id, seat)
    prior = db.execute(
        'SELECT play_token, evidence FROM amendment_seats WHERE show_id = ? AND amendment_id = ? AND seat = ?', key,
    ).fetchone()
    if prior is None or prior[0] not in (None, acceptance.token):
        raise RuntimeError('amendment token changed')
    if evidence is not None and prior[1] not in (None, evidence):
        raise RuntimeError('settled evidence changed')
    db.execute('''
        UPDATE amendment_seats SET play_token = ?, evidence = COALESCE(evidence, ?)
        WHERE show_id = ? AND amendment_id = ? AND seat = ?
    ''', (acceptance.token, evidence, *key))


def amend(db, store_for, show_id, amendment_id, cue_id, corrected_text, erratum_text):
    with control_write(db):
        order = _intake(db, show_id, amendment_id, cue_id, corrected_text, erratum_text)
        instruction = _notice(db, order)

    for seat, saved in order.seats.items():
        if saved['evidence'] is not None:
            continue
        try:
            acceptance = accept_seat_instruction(store_for(seat), instruction)
        except SeatUnavailable:
            continue
        with control_write(db):
            record_seat_evidence(db, order, seat, instruction, acceptance)
    return get_amendment(db, show_id, amendment_id)
