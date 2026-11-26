from dataclasses import dataclass

from routing.dispatch import DispatchRecord, get_dispatch, record_dispatch
from routing.enrollment import require_enabled_seat
from routing.shows import ApiError, control_write, require_open_show


@dataclass(frozen=True)
class ClaimReceipt:
    request_id: str
    show_id: str
    seat: str
    command: DispatchRecord | None


def initialize_claims(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS claim_receipts (
            request_id TEXT PRIMARY KEY,
            show_id TEXT NOT NULL,
            seat TEXT NOT NULL,
            token TEXT REFERENCES dispatches(token),
            FOREIGN KEY (show_id, seat) REFERENCES enabled_seats(show_id, seat)
        )
    ''')


def get_claim_receipt(db, request_id):
    row = db.execute(
        'SELECT show_id, seat, token FROM claim_receipts WHERE request_id = ?', (request_id,)
    ).fetchone()
    if row is None:
        return None
    command = get_dispatch(db, row[2]) if row[2] is not None else None
    return ClaimReceipt(request_id, row[0], row[1], command)


def claim(db, show_id, seat, request_id):
    with control_write(db):
        prior = get_claim_receipt(db, request_id)
        if prior is not None:
            if (prior.show_id, prior.seat) != (show_id, seat):
                raise ApiError(409, 'request_mismatch')
            return prior

        show = require_open_show(db, show_id)
        position = require_enabled_seat(db, show_id, seat)
        command = record_dispatch(db, show, seat, position)
        token = command.token if command else None
        if command is not None:
            db.execute(
                'UPDATE enabled_seats SET next_position = ? WHERE show_id = ? AND seat = ?',
                (position + 1, show_id, seat),
            )
        db.execute('INSERT INTO claim_receipts VALUES (?, ?, ?, ?)', (request_id, show_id, seat, token))
        return ClaimReceipt(request_id, show_id, seat, command)
