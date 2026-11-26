from tests import MuseumTest, scenario


class TestCorrectionIncident(MuseumTest):
    def test_north_slope_correction_incident(self):
        # 甲、乙两席领到「标本采自北坡」后领讲人发现口误：甲已实播但回包丢失，
        # 乙的播放请求被扣留。更正为南坡后，甲保留原播并补勘误，乙只播正确词。
        self.publish_sample()
        original_a = self.claim_at('甲', 'claim-a')['command']
        original_b = self.claim_at('乙', 'claim-b')['command']
        lost_reply = self.playback_request('甲', original_a, 'original-a')
        held_request = self.playback_request('乙', original_b, 'original-b')
        self.assertEqual(self.call('/play', lost_reply, discard=True), (200, None))
        self.reopen()

        order = self.ok('/amend', self.correction())
        self.assertEqual(self.amendment_status(), order)
        # 两席都领到本席更正凭据，查实前均为待定。
        self.assertEqual(
            {seat: state['status'] for seat, state in order['seats'].items()},
            {'甲': 'pending', '乙': 'pending'},
        )
        for state in order['seats'].values():
            self.assertIsInstance(state['play_token'], str)

        # 更正先于乙受理，乙扣留的旧凭据失去首次实播资格。
        self.error(409, 'stale_original', '/play', held_request)

        heard = {}
        expected_words = {'甲': '更正，刚才的北坡应为南坡', '乙': '标本采自南坡'}
        expected_kinds = {'甲': 'erratum', '乙': 'replacement'}
        for seat in ('甲', '乙'):
            played = self.play_at(seat, {'token': order['seats'][seat]['play_token']}, 'correction-' + seat)
            self.assertEqual((played['kind'], played['text']), (expected_kinds[seat], expected_words[seat]))
            heard[seat] = [played['seq'], played['kind'], played['text']]
            followup = self.claim_at(seat, 'followup-' + seat)['command']
            unaffected = self.play_at(seat, followup, 'followup-' + seat)
            self.assertEqual((unaffected['origin']['cue_id'], unaffected['text']), ('D', '请触摸模型边缘'))

        self.reopen()
        settled = self.ok('/amend', self.correction())
        self.assertEqual(self.ok('/amend', self.correction()), settled)
        self.error(409, 'request_mismatch', '/amend', self.correction(erratum_text='另一段勘误'))
        settlement = {
            seat: [state['status'], state['original_seq'], state['amendment_seq']]
            for seat, state in settled['seats'].items()
        }
        self.assertEqual(settlement, {'甲': ['erratum_played', 1, 2], '乙': ['replacement_played', None, 1]})

        # 甲的原播已实执，仍可用原播放号复领首执；乙的旧凭据查实后依旧失效。
        retained = self.ok('/play', lost_reply)['playback']
        self.assertEqual([retained['seq'], retained['kind'], retained['text']], [1, 'original', '标本采自北坡'])
        self.error(409, 'stale_original', '/play', held_request)

        report = self.fixed_report(self.ok('/close', self.close_request()))
        fixed = {
            seat: [[row['seq'], row['kind'], row['text']] for row in rows]
            for seat, rows in report['seats'].items()
        }
        expected_report = {
            '甲': [[1, 'original', '标本采自北坡'], [2, 'erratum', '更正，刚才的北坡应为南坡'],
                  [3, 'original', '请触摸模型边缘']],
            '乙': [[1, 'replacement', '标本采自南坡'], [2, 'original', '请触摸模型边缘']],
        }
        self.assertEqual(fixed, expected_report)
        scenario('v9', {'played_then_lost': '甲', 'held_original': '乙', 'correction': self.correction()},
                 {'甲': 'erratum', '乙': 'replacement'}, heard, expected_report, fixed,
                 ['release/amendments.py', 'seats/execution.py', 'seats/queue.py', 'review/reconcile.py'],
                 '甲已实播原句故保留原播补勘误，乙未实播故只播正确词；迟到旧凭据拒绝首播，收场按各席实播顺序。')
