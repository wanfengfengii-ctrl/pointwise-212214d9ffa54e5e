import json
from dataclasses import dataclass

from routing.shows import ApiError
from seats.execution import read_play_receipt
from seats.playback_history import PlaybackEntry, list_playback
from seats.store import SeatUnavailable


@dataclass(frozen=True)
class ReceiptEvidence:
    playback: list[PlaybackEntry]
    confirmed: set[str]


def initialize_review_receipts(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS review_pending (
            request_id TEXT PRIMARY KEY,
            show_id TEXT NOT NULL REFERENCES shows(show_id),
            pending TEXT NOT NULL
        )
    ''')


def collect_receipts(store_for, show_id, seats):
    evidence = {}
    for seat in seats:
        try:
            with store_for(seat).reopen() as db:
                db.execute('BEGIN')
                entries = list_playback(db, show_id)
                confirmed = set()
                for entry in entries:
                    receipt = read_play_receipt(db, entry.token)
                    if receipt is not None and receipt.playback == entry:
                        confirmed.add(entry.token)
                evidence[seat] = ReceiptEvidence(entries, confirmed)
        except SeatUnavailable:
            evidence[seat] = ReceiptEvidence([], set())
    return evidence


def require_pending_show(db, show_id, request_id):
    row = db.execute('SELECT show_id FROM review_pending WHERE request_id = ?', (request_id,)).fetchone()
    if row is not None and row[0] != show_id:
        raise ApiError(409, 'request_mismatch')


def save_pending_receipts(db, show_id, request_id, pending):
    db.execute('''
        INSERT INTO review_pending VALUES (?, ?, ?)
        ON CONFLICT(request_id) DO UPDATE SET pending = excluded.pending
    ''', (request_id, show_id, json.dumps(pending)))


def clear_pending_receipts(db, show_id):
    db.execute('DELETE FROM review_pending WHERE show_id = ?', (show_id,))
