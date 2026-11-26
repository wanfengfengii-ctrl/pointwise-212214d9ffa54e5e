"""Exercise the north-slope correction through the museum's HTTP service."""

import json
import sys
import unittest

from tests import MuseumTest


def played_line(entry):
    return [entry['seq'], entry['kind'], entry['text']]


class CorrectionIncident(MuseumTest):
    demo_mode = False

    def test_two_seat_correction(self):
        self.publish_sample()
        original_a = self.claim_at('甲', 'claim-a')['command']
        original_b = self.claim_at('乙', 'claim-b')['command']
        lost_reply = self.playback_request('甲', original_a, 'original-a')
        held_request = self.playback_request('乙', original_b, 'original-b')
        self.assertEqual(self.call('/play', lost_reply, discard=True), (200, None))
        self.reopen()

        order = self.ok('/amend', self.correction())
        self.assertEqual(self.amendment_status(), order)
        late_status, late_result = self.call('/play', held_request)
        self.assertIn(late_status, (200, 409), late_result)
        if late_status == 200:
            old_play = late_result['playback']
            self.assertEqual(old_play['origin'], original_b['origin'])
            self.assertEqual(old_play['seat'], '乙')
            late_original = played_line(old_play)
        else:
            late_original = late_result['error']

        heard = {}
        for seat, state in order['seats'].items():
            token = state['play_token']
            if token is None:
                heard[seat] = None
            else:
                heard[seat] = played_line(self.play_at(seat, {'token': token}, 'correction'))
            followup = self.claim_at(seat, 'followup-' + seat)['command']
            unaffected = self.play_at(seat, followup, 'followup')
            self.assertEqual((unaffected['origin']['cue_id'], unaffected['text']), ('D', '请触摸模型边缘'))

        self.reopen()
        settled = self.ok('/amend', self.correction())
        self.assertEqual(self.amendment_status(), settled)
        self.assertEqual(self.ok('/amend', self.correction()), settled)
        self.error(409, 'request_mismatch', '/amend', self.correction(erratum_text='另一段勘误'))
        retained_original = self.ok('/play', lost_reply)['playback']
        close_status, close_result = self.call('/close', self.close_request())
        self.assertIn(close_status, (200, 409), close_result)
        if close_status == 200:
            report = self.fixed_report(close_result)
            self.assertEqual(self.ok('/close', self.close_request()), close_result)
            fixed = {seat: [played_line(entry) for entry in entries] for seat, entries in report['seats'].items()}
        else:
            self.assertEqual(close_result['status'], 'pending')
            fixed = None

        actual = {
            'original_a': played_line(retained_original),
            'late_b': [late_status, late_original],
            'correction_plays': heard,
            'settlement': {
                seat: [state['status'], state['original_seq'], state['amendment_seq']]
                for seat, state in settled['seats'].items()
            },
            'close': [close_status, close_result['status']],
            'report': fixed,
        }
        expected = {
            'original_a': [1, 'original', '标本采自北坡'],
            'late_b': [409, 'stale_original'],
            'correction_plays': {
                '甲': [2, 'erratum', '更正，刚才的北坡应为南坡'],
                '乙': [1, 'replacement', '标本采自南坡'],
            },
            'settlement': {'甲': ['erratum_played', 1, 2], '乙': ['replacement_played', None, 1]},
            'close': [200, 'closed'],
            'report': {
                '甲': [[1, 'original', '标本采自北坡'], [2, 'erratum', '更正，刚才的北坡应为南坡'],
                      [3, 'original', '请触摸模型边缘']],
                '乙': [[1, 'replacement', '标本采自南坡'], [2, 'original', '请触摸模型边缘']],
            },
        }
        print(json.dumps({'observed': actual, 'expected': expected}, ensure_ascii=False, indent=2), flush=True)
        if not self.demo_mode and actual != expected:
            print('MUSEUM_CORRECTION_DIVERGED', flush=True)
            self.assertEqual(actual, expected)


if __name__ == '__main__':
    if sys.argv[1:] == ['--demo']:
        CorrectionIncident.demo_mode = True
        del sys.argv[1:]
    unittest.main()
