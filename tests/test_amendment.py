from tests import MuseumTest, scenario


class TestAmendment(MuseumTest):
    def test_two_seats_with_lost_response(self):
        self.publish_sample()
        old_a = self.claim_at('甲', 'a1')['command']
        old_b = self.claim_at('乙', 'b1')['command']
        request_a = self.playback_request('甲', old_a, 'old-a')
        self.assertEqual(self.call('/play', request_a, discard=True), (200, None))
        self.reopen()
        order = self.ok('/amend', self.correction())
        self.assertEqual([item['status'] for item in order['seats'].values()], ['pending', 'pending'])
        self.assertEqual(self.amendment_status(), order)
        self.error(409, 'stale_original', '/play', self.playback_request('乙', old_b, 'old-b'))

        b_replacement = self.play_at('乙', self.correction_command(order, '乙'), 'b-new')
        self.assertEqual((b_replacement['seq'], b_replacement['text']), (1, '标本采自南坡'))
        partial = self.ok('/amend', self.correction())
        self.assertEqual(partial['seats']['甲']['status'], 'pending')
        self.assertEqual(partial['seats']['乙']['status'], 'replacement_played', 'AMENDMENT_SEAT_OUTCOME')

        erratum = self.correction_command(order, '甲')
        request_erratum = self.playback_request('甲', erratum, 'a-fix')
        self.assertEqual(self.call('/play', request_erratum, discard=True), (200, None))
        self.assertEqual(self.amendment_status()['seats']['甲']['status'], 'pending')
        self.reopen()
        done = self.ok('/amend', self.correction())
        actual = {seat: [result[key] for key in ('status', 'original_seq', 'amendment_seq')]
                  for seat, result in done['seats'].items()}
        expected = {'甲': ['erratum_played', 1, 2], '乙': ['replacement_played', None, 1]}
        self.assertEqual(actual, expected, 'AMENDMENT_SEAT_OUTCOME')
        self.assertEqual(self.amendment_status(), done)
        self.assertEqual(self.ok('/amend', self.correction()), done)
        self.assertEqual(self.ok('/play', request_a)['playback']['seq'], 1)
        self.assertEqual(self.ok('/play', request_erratum)['playback']['seq'], 2)

        for seat in ('甲', '乙'):
            next_word = self.claim_at(seat, 'next-' + seat)['command']
            self.play_at(seat, next_word, 'next')
        fixed = self.fixed_report(self.ok('/close', self.close_request()))
        texts = {seat: [entry['text'] for entry in entries] for seat, entries in fixed['seats'].items()}
        expected_texts = {'甲': ['标本采自北坡', '更正，刚才的北坡应为南坡', '请触摸模型边缘'],
                          '乙': ['标本采自南坡', '请触摸模型边缘']}
        self.assertEqual(texts, expected_texts, 'AMENDMENT_SEAT_OUTCOME')
        scenario('v5', {'lost_play_response': '甲', 'held_original': '乙', 'order': self.correction()},
                 expected, actual, expected_texts, texts,
                 ['release/amendments.py', 'release/status.py', 'seats/execution.py', 'review/reconcile.py'],
                 '同领 C 后甲实际占序 1，乙没有旧播。根据这两个独立事实手列更正与复盘内容。')

    def test_late_original_after_effect(self):
        self.publish_sample()
        old_b = self.claim_at('乙', 'old-b')['command']
        held = self.playback_request('乙', old_b, 'held')
        self.reopen()
        pending = self.ok('/amend', self.correction())
        self.assertIsNone(pending['seats']['乙']['original_seq'])
        self.assertEqual(pending['seats']['乙']['status'], 'pending')
        unaffected = self.claim_at('乙', 'unaffected')['command']
        played = self.play_at('乙', unaffected, 'ordinary')
        self.assertEqual((played['origin']['cue_id'], played['seq'], played['text']), ('D', 1, '请触摸模型边缘'))
        self.reopen()
        result = self.error(409, 'stale_original', '/play', held)
        for seat in ('甲', '乙'):
            self.play_at(seat, self.correction_command(pending, seat), 'correct')
        settled = self.ok('/amend', self.correction())
        states = settled['seats']['乙']
        self.assertEqual((states['status'], states['original_seq'], states['amendment_seq']), ('replacement_played', None, 2))
        self.error(409, 'stale_original', '/play', held)
        downstream = [played['text'], self.ok('/play', self.playback_request('乙', self.correction_command(pending, '乙'), 'correct'))['playback']['text']]
        self.assertEqual(downstream, ['请触摸模型边缘', '标本采自南坡'])
        scenario('v6', {'held': '乙-C', 'effect_before_held': True, 'unaffected': 'D'},
                 'stale_original', result['error'], ['请触摸模型边缘', '标本采自南坡'], downstream,
                 ['seats/queue.py', 'seats/execution.py', 'release/status.py'],
                 '更正先于扣留的 C，因此乙实际顺序为 D、南坡。序号从 1 开始且没有旧 C。')

    def test_original_sent_before_effect_after_reopen(self):
        self.publish_sample()
        word = self.claim_at('乙', 'before')['command']
        held = self.playback_request('乙', word, 'held')
        self.reopen()
        self.assertEqual(self.call('/play', held, discard=True), (200, None))
        pending = self.ok('/amend', self.correction())
        self.assertEqual(pending['seats']['乙']['status'], 'pending')
        followup = self.play_at('乙', self.claim_at('乙', 'second')['command'], 'unrelated')
        self.assertEqual(followup['seq'], 2)
        correction = self.play_at('乙', self.correction_command(pending, '乙'), 'fixed')
        self.assertEqual((correction['kind'], correction['text'], correction['seq']),
                         ('erratum', '更正，刚才的北坡应为南坡', 3))
        settled = self.ok('/amend', self.correction())['seats']['乙']
        self.assertEqual((settled['status'], settled['original_seq'], settled['amendment_seq']), ('erratum_played', 1, 3))

    def test_amend_retry_mismatch_and_unclaimed_original(self):
        self.publish_sample()
        self.assertEqual(self.call('/amend', self.correction(), discard=True), (200, None))
        self.reopen()
        order = self.ok('/amend', self.correction())
        result = self.play_at('甲', self.correction_command(order, '甲'), 'correct')
        self.assertEqual((result['seq'], result['text']), (1, '标本采自南坡'))
        done = self.ok('/amend', self.correction())
        self.error(409, 'request_mismatch', '/amend', self.correction(erratum_text='另一段勘误'))
        self.error(409, 'request_mismatch', '/amend', self.correction(corrected_text='另一段正确词'))
        self.error(409, 'original_already_amended', '/amend', self.correction(amendment_id='second'))
        self.assertEqual(self.amendment_status(), done)
        freshly_claimed = self.claim_at('甲', 'fresh')['command']
        self.error(409, 'stale_original', '/play', self.playback_request('甲', freshly_claimed, 'old'))
        self.assertEqual(self.play_at('甲', self.correction_command(order, '甲'), 'correct'), result)

    def test_foreign_original_and_unknown_amendment(self):
        self.publish_sample()
        new_cue = {**self.sample['cues'][0], 'cue_id': 'X'}
        other = self.draft([new_cue])
        self.ok('/publish', self.publication(other['revision'], show='另一场'))
        self.error(404, 'unknown_original_cue', '/amend', self.correction(cue_id='X'))
        self.error(404, 'unknown_amendment', '/amend_status', query={'show_id': self.show, 'amendment_id': 'M'})
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM amendments'), 0)
