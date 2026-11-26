import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode

from routing.http_api import serve_loopback


SAMPLE_PATH = Path(__file__).resolve().parents[1] / 'samples' / 'day.json'


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': code_paths,
        'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))


class MuseumTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='museum-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.sample = json.loads(SAMPLE_PATH.read_text(encoding='utf-8'))
        self.show = self.sample['show_id']
        self.server = None
        self.addCleanup(self.stop)
        self.start()

    def start(self):
        self.server = serve_loopback(self.root)
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.worker.start()

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.worker.join(timeout=5)
            self.server.server_close()
            self.server = None
            self.assertFalse(self.worker.is_alive())

    def reopen(self):
        self.stop()
        self.start()

    def call(self, path, payload=None, *, query=None, discard=False):
        if query is not None:
            path += '?' + urlencode(query)
        with closing(http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)) as connection:
            if payload is None:
                connection.request('GET', path)
            else:
                connection.request('POST', path, json.dumps(payload), {'Content-Type': 'application/json'})
            with connection.getresponse() as response:
                status = response.status
                # Headers witness that the server reached the reply boundary. The client drops the receipt body.
                if discard:
                    return status, None
                return status, json.load(response)

    def ok(self, path, payload=None, *, query=None):
        status, result = self.call(path, payload, query=query)
        self.assertEqual(status, 200, result)
        return result

    def error(self, level, code, path, payload=None, *, query=None):
        status, result = self.call(path, payload, query=query)
        self.assertEqual((status, result.get('error')), (level, code), result)
        return result

    def draft(self, cues=None):
        if cues is None:
            cues = self.sample['cues']
        return self.ok('/proof', {'draft_id': self.sample['draft_id'], 'cues': cues})

    def publication(self, revision, *, show=None, seats=None):
        return {
            'draft_id': self.sample['draft_id'], 'revision': revision,
            'show_id': self.show if show is None else show,
            'seats': self.sample['seats'] if seats is None else seats,
        }

    def publish_sample(self):
        return self.ok('/publish', self.publication(self.draft()['revision']))

    def claim_at(self, seat, request_id):
        return self.ok('/claim', {'show_id': self.show, 'seat': seat, 'request_id': request_id})

    def playback_request(self, seat, command, request_id):
        return {'show_id': self.show, 'seat': seat, 'token': command['token'], 'request_id': request_id}

    def play_at(self, seat, command, request_id):
        return self.ok('/play', self.playback_request(seat, command, request_id))['playback']

    def correction(self, **changes):
        return {'show_id': self.show, **self.sample['amendment'], **changes}

    def amendment_status(self):
        return self.ok('/amend_status', query={'show_id': self.show, 'amendment_id': 'M'})

    def correction_command(self, order, seat):
        token = order['seats'][seat]['play_token']
        self.assertIsInstance(token, str)
        return {'token': token}

    def close_request(self, request_id='close'):
        return {'show_id': self.show, 'request_id': request_id}

    def fixed_report(self, receipt):
        return self.ok('/report', query={'report_id': receipt['report_id']})

    def control_count(self, query):
        with closing(sqlite3.connect(self.root / 'control.sqlite3')) as db:
            return db.execute(query).fetchone()[0]
