from tests import MuseumTest, scenario


class TestPlayback(MuseumTest):
    def test_claim_and_play(self):
        issued = self.publish_sample()
        first = self.claim_at('甲', 'a1')['command']
        receipt = self.play_at('甲', first, 'p1')
        second = self.claim_at('乙', 'b1')['command']
        self.assertEqual((receipt['seq'], receipt['text'], receipt['kind']), (1, '标本采自北坡', 'original'))
        self.assertEqual(receipt['origin'], {
            'edition_id': issued['edition_id'], 'draft_id': self.sample['draft_id'],
            'revision': 1, 'cue_id': 'C', 'position': 1,
        })
        self.assertEqual(first['origin'], second['origin'])
        self.assertNotEqual(first['token'], second['token'])
        actual = {'甲': first['origin']['cue_id'], '乙': second['origin']['cue_id']}
        self.assertEqual(actual, {'甲': 'C', '乙': 'C'})
        scenario('v3', {'seats': ['甲', '乙'], 'operations': ['甲领播', '乙领取']},
                 {'甲': 'C', '乙': 'C'}, actual, {'seq': 1, 'text': '标本采自北坡'},
                 {'seq': receipt['seq'], 'text': receipt['text']},
                 ['routing/claims.py', 'routing/dispatch.py', 'seats/execution.py'],
                 '甲的首次领取和实播独立于乙的领取位次，固定列表首句为 C。')

    def test_receipt_replay_after_reopen(self):
        self.publish_sample()
        first = self.claim_at('甲', 'a1')['command']
        request = self.playback_request('甲', first, 'start')
        self.assertEqual(self.call('/play', request, discard=True), (200, None))
        self.reopen()
        recovered = self.ok('/play', request)
        self.assertEqual(recovered['request_id'], 'start')
        self.assertEqual(recovered['playback']['seq'], 1)
        self.assertEqual(recovered['playback']['text'], '标本采自北坡')
        self.assertEqual(recovered, self.ok('/play', request))
        next_command = self.claim_at('甲', 'a2')['command']
        mismatch = self.error(409, 'request_mismatch', '/play', {**request, 'token': next_command['token']})
        self.error(409, 'command_already_played', '/play', {**request, 'request_id': 'fresh'})
        next_play = self.play_at('甲', next_command, 'next')
        self.assertEqual(next_play['seq'], 2)
        actual = {'same_receipt': self.ok('/play', request) == recovered, 'original_seq': recovered['playback']['seq']}
        self.assertEqual(actual, {'same_receipt': True, 'original_seq': 1})
        scenario('v4', {'seat': '甲', 'request_id': 'start', 'first_body_discarded': True},
                 {'same_receipt': True, 'original_seq': 1}, actual,
                 {'next_seq': 2, 'changed_request': 'request_mismatch'},
                 {'next_seq': next_play['seq'], 'changed_request': mismatch['error']},
                 ['seats/store.py', 'seats/execution.py', 'seats/receipts.py'],
                 '首播占序 1，复领动作没有消费另一个序号，下一次实际播出占序 2。')

    def test_claim_retry_per_seat_cursor_and_end(self):
        self.publish_sample()
        a_first = self.claim_at('甲', 'a1')
        a_next = self.claim_at('甲', 'a2')
        self.assertEqual(a_next['command']['origin']['cue_id'], 'D')
        a_end = self.claim_at('甲', 'a3')
        self.assertIsNone(a_end['command'])
        self.reopen()
        self.assertEqual(self.claim_at('甲', 'a1'), a_first)
        self.assertEqual(self.claim_at('甲', 'a3'), a_end)
        self.error(409, 'request_mismatch', '/claim', {'show_id': self.show, 'seat': '乙', 'request_id': 'a1'})
        self.assertEqual(self.claim_at('乙', 'b1')['command']['origin']['cue_id'], 'C')

    def test_inactive_seat_and_foreign_token(self):
        self.publish_sample()
        self.error(404, 'seat_not_enabled', '/claim', {'show_id': self.show, 'seat': '丙', 'request_id': 'claim'})
        original = self.claim_at('甲', 'claim')['command']
        self.error(404, 'unknown_play_token', '/play', self.playback_request('乙', original, 'play'))
        proper = self.play_at('甲', original, 'play')
        self.assertEqual(proper['seq'], 1)
