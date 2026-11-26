from tests import MuseumTest, scenario


class TestCloseout(MuseumTest):
    def test_waits_for_unsettled_seat(self):
        issued = self.publish_sample()
        original = self.claim_at('甲', 'a-c')['command']
        self.play_at('甲', original, 'first')
        self.claim_at('乙', 'b-c')
        order = self.ok('/amend', self.correction())
        for seat in ('甲', '乙'):
            command = self.claim_at(seat, 'd-' + seat)['command']
            self.play_at(seat, command, 'd')
        self.play_at('乙', self.correction_command(order, '乙'), 'new')
        erratum = self.playback_request('甲', self.correction_command(order, '甲'), 'fix')
        self.assertEqual(self.call('/play', erratum, discard=True), (200, None))
        self.assertEqual(self.ok('/amend_status', query={'show_id': self.show, 'amendment_id': 'M'})['seats']['甲']['status'], 'pending')
        # Reconcile both seats at intake before proceeding to the next scenario step.
        status, early = self.call('/close', self.close_request())
        self.assertEqual(status, 409)
        self.assertEqual(early['status'], 'pending')
        expected_pending = [
            {'seat': seat, 'cue_id': 'C', 'amendment_id': 'M', 'reason': 'amendment_pending'} for seat in ('甲', '乙')
        ]
        self.assertEqual(early['pending'], expected_pending)
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM reports'), 0)
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM close_receipts'), 0)
        self.error(404, 'unknown_report', '/report', query={'report_id': 'report:' + self.show})

        settled = self.ok('/amend', self.correction())
        self.assertEqual(settled['seats']['甲']['amendment_seq'], 3)
        self.assertEqual(settled['seats']['乙']['amendment_seq'], 2)
        fixed = self.fixed_report(self.ok('/close', self.close_request()))
        actual = {seat: [(row['seq'], row['origin']['cue_id'], row['text']) for row in rows]
                  for seat, rows in fixed['seats'].items()}
        expected = {
            '甲': [(1, 'C', '标本采自北坡'), (2, 'D', '请触摸模型边缘'), (3, 'C', '更正，刚才的北坡应为南坡')],
            '乙': [(1, 'D', '请触摸模型边缘'), (2, 'C', '标本采自南坡')],
        }
        self.assertEqual(actual, expected)
        self.assertTrue(all(row['origin']['edition_id'] == issued['edition_id']
                            for entries in fixed['seats'].values() for row in entries))
        scenario('v7', {'played_erratum_response': 'discarded', 'amendment_reconciliation': 'deferred'},
                 expected_pending, early['pending'], expected, actual,
                 ['review/obligations.py', 'review/receipts.py', 'review/reconcile.py', 'review/closeout.py'],
                 '续核前 C 更正仍待核。补证后依实际播放次序手列三条甲席记录及两条乙席记录。')

    def test_missing_unclaimed_seat_and_partial_amendment_evidence(self):
        self.publish_sample()
        a = self.claim_at('甲', 'a-c')['command']
        self.play_at('甲', a, 'initial')
        self.play_at('甲', self.claim_at('甲', 'a-d')['command'], 'second')
        status, result = self.call('/close', self.close_request())
        self.assertEqual(status, 409)
        self.assertEqual([(row['seat'], row['cue_id'], row['reason']) for row in result['pending']],
                         [('乙', 'C', 'missing_playback'), ('乙', 'D', 'missing_playback')])
        self.claim_at('乙', 'b-c')
        order = self.ok('/amend', self.correction())
        self.play_at('乙', self.correction_command(order, '乙'), 'replacement')
        self.play_at('乙', self.claim_at('乙', 'b-d')['command'], 'second')
        self.ok('/amend', self.correction())
        status, result = self.call('/close', self.close_request())
        self.assertEqual(status, 409)
        self.assertEqual(result['pending'], [{'seat': '甲', 'cue_id': 'C', 'amendment_id': 'M', 'reason': 'amendment_pending'}])
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM close_receipts'), 0)
        self.play_at('甲', self.correction_command(order, '甲'), 'fix')
        self.ok('/amend', self.correction())
        self.assertEqual(self.ok('/close', self.close_request())['status'], 'closed')

    def test_report_stays_fixed(self):
        issued = self.publish_sample()
        for seat in ('甲', '乙'):
            for position in (1, 2):
                handle = str(position)
                self.play_at(seat, self.claim_at(seat, seat + handle)['command'], handle)
        receipt = self.ok('/close', self.close_request('save'))
        original = self.fixed_report(receipt)
        self.reopen()
        recovered = self.ok('/close', self.close_request('save'))
        reread = self.fixed_report(recovered)
        self.assertEqual(recovered, receipt)
        self.assertEqual(reread, original)
        self.assertEqual(recovered['report_id'], 'report:' + self.show)
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM reports'), 1)
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM close_receipts'), 1)
        self.error(409, 'show_closed', '/close', self.close_request('fresh'))
        self.error(409, 'request_mismatch', '/close', {**self.close_request('save'), 'show_id': '别场'})
        self.error(409, 'show_closed', '/amend', self.correction())
        self.error(404, 'unknown_report', '/report', query={'report_id': 'phantom'})
        self.assertEqual(self.fixed_report(receipt), original)
        expected = {seat: [[1, 'C', '标本采自北坡'], [2, 'D', '请触摸模型边缘']] for seat in ('甲', '乙')}
        actual = {seat: [[row['seq'], row['origin']['cue_id'], row['text']] for row in rows]
                  for seat, rows in reread['seats'].items()}
        self.assertEqual(actual, expected)
        self.assertEqual(reread['seats']['乙'][0]['origin']['edition_id'], issued['edition_id'])
        scenario('v8', {'close_id': 'save', 'reinitialized': True}, receipt, recovered, expected, actual,
                 ['review/closeout.py', 'review/reports.py', 'routing/http_api.py'],
                 '两席各顺播 C、D，重开按原号返回同一收场首执和签存记录。')
