import json
from dataclasses import asdict, dataclass

from routing.shows import ApiError


@dataclass(frozen=True)
class ShowReport:
    report_id: str
    show_id: str
    seats: dict[str, list[dict]]


@dataclass(frozen=True)
class CloseReceipt:
    request_id: str
    show_id: str
    report_id: str
    status: str = 'closed'


def initialize_reports(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            show_id TEXT NOT NULL UNIQUE REFERENCES shows(show_id),
            playback TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS close_receipts (
            request_id TEXT PRIMARY KEY,
            report_id TEXT NOT NULL UNIQUE REFERENCES reports(report_id)
        );
    ''')


def store_report(db, show_id, request_id, playback):
    report_id = 'report:' + show_id
    contents = {seat: [asdict(entry) for entry in entries] for seat, entries in playback.items()}
    db.execute('INSERT INTO reports VALUES (?, ?, ?)', (report_id, show_id, json.dumps(contents)))
    db.execute('INSERT INTO close_receipts VALUES (?, ?)', (request_id, report_id))
    return CloseReceipt(request_id, show_id, report_id)


def get_close_receipt(db, request_id):
    row = db.execute('''
        SELECT r.show_id, r.report_id FROM close_receipts AS c
        JOIN reports AS r ON r.report_id = c.report_id WHERE c.request_id = ?
    ''', (request_id,)).fetchone()
    return CloseReceipt(request_id, row[0], row[1]) if row is not None else None


def report(db, report_id):
    row = db.execute('SELECT show_id, playback FROM reports WHERE report_id = ?', (report_id,)).fetchone()
    if row is None:
        raise ApiError(404, 'unknown_report')
    return ShowReport(report_id, row[0], json.loads(row[1]))
