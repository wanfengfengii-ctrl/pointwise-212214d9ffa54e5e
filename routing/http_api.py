import argparse
import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
from contextlib import closing
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from release.amendments import amend, initialize_amendments
from release.editions import initialize_editions
from release.publication import publish
from release.status import amend_status, project_amendment
from review.closeout import close
from review.receipts import initialize_review_receipts
from review.reports import initialize_reports, report
from routing.claims import claim, initialize_claims
from routing.dispatch import get_dispatch, initialize_dispatch
from routing.enrollment import initialize_enrollment, require_enabled_seat
from routing.shows import ApiError, control_write, initialize_shows
from script.cues import valid_text
from script.drafts import initialize_drafts
from script.proofs import initialize_proofs, proof
from seats.execution import accept_seat_instruction, play
from seats.store import SeatStore, SeatUnavailable


class Service:
    def __init__(self, root):
        self.root = Path(root)
        self._stores = {}
        self._stores_lock = threading.Lock()

    def connect(self):
        db = sqlite3.connect(self.root / 'control.sqlite3', isolation_level=None, timeout=5.0)
        db.execute('PRAGMA foreign_keys = ON')
        return db

    def store_for(self, seat):
        with self._stores_lock:
            store = self._stores.get(seat)
            if store is None:
                filename = hashlib.sha256(seat.encode('utf-8')).hexdigest() + '.sqlite3'
                store = SeatStore(self.root / 'seats' / filename, seat)
                self._stores[seat] = store
        store.initialize()
        return store


def initialize_service(root):
    service = Service(root)
    (service.root / 'seats').mkdir(parents=True, exist_ok=True)
    with closing(service.connect()) as db:
        for initialize in (
            initialize_drafts, initialize_proofs, initialize_editions, initialize_shows,
            initialize_enrollment, initialize_dispatch, initialize_claims, initialize_amendments,
            initialize_review_receipts, initialize_reports,
        ):
            initialize(db)
    return service


POST_FIELDS = {
    '/proof': ('draft_id', 'cues'),
    '/publish': ('draft_id', 'revision', 'show_id', 'seats'),
    '/claim': ('show_id', 'seat', 'request_id'),
    '/play': ('show_id', 'seat', 'token', 'request_id'),
    '/amend': ('show_id', 'amendment_id', 'cue_id', 'corrected_text', 'erratum_text'),
    '/close': ('show_id', 'request_id'),
}
GET_FIELDS = {'/amend_status': ('show_id', 'amendment_id'), '/report': ('report_id',)}


def _parameters(values, fields):
    if not isinstance(values, dict) or set(values) != set(fields):
        raise ApiError(400, 'invalid_fields', {'required': list(fields)})
    for field in fields:
        value = values[field]
        if field == 'cues':
            continue
        if field == 'seats':
            valid = isinstance(value, list) and bool(value) and all(valid_text(seat) for seat in value)
            valid = valid and len(value) == len(set(value))
        elif field == 'revision':
            valid = type(value) is int and 1 <= value <= 2**63 - 1
        else:
            valid = valid_text(value)
        if not valid:
            raise ApiError(400, 'invalid_field', {'field': field})
    return [values[field] for field in fields]


def _post(service, path, args):
    with closing(service.connect()) as db:
        if path == '/proof':
            with control_write(db):
                return 200, asdict(proof(db, *args))
        if path == '/publish':
            return 200, asdict(publish(db, *args))
        if path == '/claim':
            result = claim(db, *args)
            if result.command is not None:
                accept_seat_instruction(service.store_for(result.seat), result.command)
            return 200, asdict(result)
        if path == '/play':
            show_id, seat, token, request_id = args
            require_enabled_seat(db, show_id, seat)
            dispatch = get_dispatch(db, token)
            if dispatch is not None and (dispatch.show_id, dispatch.seat) != (show_id, seat):
                dispatch = None
            return 200, asdict(play(service.store_for(seat), show_id, token, request_id, dispatch))
        if path == '/amend':
            return 200, project_amendment(amend(db, service.store_for, *args))
        result = close(db, service.store_for, *args)
        return (409 if result['status'] == 'pending' else 200), result


def _get(service, path, args):
    with closing(service.connect()) as db:
        if path == '/amend_status':
            db.execute('BEGIN')
            return amend_status(db, *args)
        return asdict(report(db, *args))


def _reject_json_constant(value):
    raise ValueError(value)


def build_request_handler(service):
    class RequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _read_json(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0:
                    raise ValueError('missing length')
                if length > 1_048_576:
                    raise ApiError(413, 'body_too_large')
                return json.loads(self.rfile.read(length).decode('utf-8'), parse_constant=_reject_json_constant)
            except (ValueError, UnicodeError) as error:
                raise ApiError(400, 'invalid_json') from error

        def _reply(self, status, result):
            body = json.dumps(result).encode('ascii')
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def _handle(self, is_post):
            try:
                try:
                    target = urlsplit(self.path)
                except ValueError as error:
                    raise ApiError(400, 'invalid_target') from error
                fields = (POST_FIELDS if is_post else GET_FIELDS).get(target.path)
                if fields is None:
                    raise ApiError(404, 'unknown_endpoint')
                if is_post:
                    if target.query:
                        raise ApiError(400, 'unexpected_query')
                    status, result = _post(service, target.path, _parameters(self._read_json(), fields))
                else:
                    try:
                        query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, errors='strict')
                    except ValueError as error:
                        raise ApiError(400, 'invalid_query') from error
                    args = _parameters({key: values[0] for key, values in query.items() if len(values) == 1}, fields)
                    if len(query) != len(fields):
                        raise ApiError(400, 'invalid_fields')
                    status, result = 200, _get(service, target.path, args)
            except ApiError as error:
                status, result = error.status, {'error': error.code}
                if error.details is not None:
                    result['details'] = error.details
            except SeatUnavailable:
                status, result = 503, {'error': 'seat_unavailable'}
            except sqlite3.OperationalError as error:
                if getattr(error, 'sqlite_errorcode', 0) & 255 not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise
                status, result = 503, {'error': 'control_unavailable'}
            self._reply(status, result)

        def do_POST(self):
            self._handle(True)

        def do_GET(self):
            self._handle(False)

    return RequestHandler


def serve_loopback(root, port=0):
    return ThreadingHTTPServer(('127.0.0.1', port), build_request_handler(initialize_service(root)))


def _demo_request(port, path, payload=None, query=None):
    if query is not None:
        path += '?' + urlencode(query)
    with closing(http.client.HTTPConnection('127.0.0.1', port, timeout=10)) as connection:
        if payload is None:
            connection.request('GET', path)
        else:
            connection.request('POST', path, json.dumps(payload), {'Content-Type': 'application/json'})
        with connection.getresponse() as response:
            result = json.load(response)
            if response.status != 200:
                raise RuntimeError((path, response.status, result))
            return result


def _demo():
    sample_path = Path(__file__).resolve().parents[1] / 'samples' / 'day.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    show = sample['show_id']
    first_seat, second_seat = sample['seats']
    correction = {'show_id': show, **sample['amendment']}
    with tempfile.TemporaryDirectory(prefix='museum-demo-') as root, serve_loopback(root) as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05})
        worker.start()
        try:
            def request(path, payload=None, query=None):
                return _demo_request(server.server_port, path, payload, query)

            def claim_next(seat, request_id):
                return request('/claim', {'show_id': show, 'seat': seat, 'request_id': request_id})['command']

            def play_token(seat, token, request_id):
                return request('/play', {'show_id': show, 'seat': seat, 'token': token, 'request_id': request_id})

            checked = request('/proof', {'draft_id': sample['draft_id'], 'cues': sample['cues']})
            edition = request('/publish', {
                'draft_id': sample['draft_id'], 'revision': checked['revision'], 'show_id': show, 'seats': sample['seats'],
            })
            original = claim_next(first_seat, 'original-first')
            claim_next(second_seat, 'original-second')
            play_token(first_seat, original['token'], 'play-original')
            order = request('/amend', correction)
            for seat in sample['seats']:
                followup = claim_next(seat, 'followup-' + seat)
                play_token(seat, followup['token'], 'play-followup')
                play_token(seat, order['seats'][seat]['play_token'], 'play-correction')
            settled = request('/amend', correction)
            receipt = request('/close', {'show_id': show, 'request_id': 'close-morning'})
            fixed = request('/report', query={'report_id': receipt['report_id']})
            print(json.dumps({'proof': checked, 'edition': edition, 'amendment': settled, 'report': fixed}, ensure_ascii=False, indent=2))
        finally:
            server.shutdown()
            worker.join()


def main():
    parser = argparse.ArgumentParser(description='Museum narration service')
    subcommands = parser.add_subparsers(dest='command', required=True)
    run = subcommands.add_parser('serve')
    run.add_argument('--data-dir', type=Path, required=True)
    run.add_argument('--port', type=int, default=8765)
    subcommands.add_parser('demo')
    args = parser.parse_args()
    if args.command == 'demo':
        _demo()
    else:
        with serve_loopback(args.data_dir, args.port) as server:
            print(f'Listening on 127.0.0.1:{server.server_port}', flush=True)
            server.serve_forever()


if __name__ == '__main__':
    main()
