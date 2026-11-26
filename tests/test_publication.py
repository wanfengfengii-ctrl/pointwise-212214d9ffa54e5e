from tests import MuseumTest, scenario


class TestPublication(MuseumTest):
    def test_touching_cues_publish(self):
        checked = self.draft()
        actual = [(row['start'], row['end']) for row in checked['intervals']]
        expected = [(1, 3), (3, 4)]
        self.assertTrue(checked['passed'])
        self.assertEqual(checked['conflicts'], [])
        self.assertEqual(actual, expected)
        released = self.ok('/publish', self.publication(checked['revision']))
        frozen = [cue['cue_id'] for cue in released['cues']]
        self.assertEqual(frozen, ['C', 'D'])
        self.assertEqual(self.claim_at('乙', 'first')['command']['origin']['edition_id'], released['edition_id'])
        scenario('v1', self.sample['cues'], expected, actual, ['C', 'D'], frozen,
                 ['script/timing.py', 'script/proofs.py', 'release/publication.py', 'routing/dispatch.py'],
                 '手算 1+2=3，3+1=4。两段只有一个端点接触，按列表顺序冻结。')

    def test_overlap_blocks_publication(self):
        cues = [self.sample['cues'][0], {**self.sample['cues'][1], 'start': 2, 'duration': 2}]
        checked = self.draft(cues)
        self.assertFalse(checked['passed'])
        expected = [{'channel': '讲解', 'first': 'C', 'second': 'D'}]
        self.assertEqual(checked['conflicts'], expected)
        error = self.error(409, 'revision_not_proved', '/publish', self.publication(checked['revision']))
        count = self.control_count('SELECT COUNT(*) FROM editions')
        self.assertEqual(count, 0)
        self.error(404, 'unknown_show', '/claim', {'show_id': self.show, 'seat': '甲', 'request_id': 'bad'})
        scenario('v2', cues, expected, checked['conflicts'], {'error': 'revision_not_proved', 'editions': 0},
                 {'error': error['error'], 'editions': count},
                 ['script/timing.py', 'script/proofs.py', 'release/publication.py'],
                 '两个半开区间共同占用拍 2，驳回后发行表为空。')

    def test_independent_channels(self):
        cues = [self.sample['cues'][0], {**self.sample['cues'][1], 'channel': '提示', 'start': 1}]
        checked = self.draft(cues)
        self.assertTrue(checked['passed'])
        self.assertEqual(checked['conflicts'], [])
        self.assertEqual(len(self.ok('/publish', self.publication(checked['revision']))['cues']), 2)

    def test_enclosing_interval(self):
        cues = [
            {'cue_id': cue_id, 'channel': '共同', 'start': start, 'duration': duration, 'text': cue_id}
            for cue_id, start, duration in [('L', 0, 10), ('P', 1, 1), ('Q', 3, 1), ('R', 8, 1), ('T', 10, 1)]
        ]
        checked = self.draft(cues)
        self.assertEqual([(pair['first'], pair['second']) for pair in checked['conflicts']], [('L', 'P'), ('L', 'Q'), ('L', 'R')])
        self.assertFalse(checked['passed'])

    def test_invalid_fields_are_attributed_to_cues(self):
        bad = [
            {'cue_id': 'C', 'start': True, 'duration': 0, 'text': '  '},
            {'cue_id': 'C', 'channel': '讲解', 'start': 1.5, 'duration': 2, 'text': '可以读'},
            {'channel': '讲解', 'start': 3, 'duration': False, 'text': None},
        ]
        checked = self.draft(bad)
        self.assertFalse(checked['passed'])
        self.assertEqual(checked['intervals'], [])
        observed = {(item['position'], item['field'], item['code']) for item in checked['field_errors']}
        self.assertEqual(observed, {
            (1, 'channel', 'text_required'), (1, 'start', 'invalid_beat'),
            (1, 'duration', 'invalid_beat'), (1, 'text', 'text_required'),
            (2, 'cue_id', 'duplicate'), (2, 'start', 'invalid_beat'),
            (3, 'cue_id', 'text_required'), (3, 'duration', 'invalid_beat'), (3, 'text', 'text_required'),
        })
        empty = self.draft([])
        self.assertEqual(empty['field_errors'], [{'field': 'cues', 'code': 'nonempty_list_required'}])
        self.error(409, 'revision_not_proved', '/publish', self.publication(checked['revision']))

    def test_proof_revision_mismatch(self):
        valid = self.draft()
        invalid = self.draft([self.sample['cues'][0], {**self.sample['cues'][1], 'start': 2}])
        self.assertTrue(valid['passed'])
        self.assertFalse(invalid['passed'])
        self.assertGreater(invalid['revision'], valid['revision'])
        self.error(409, 'revision_not_proved', '/publish', self.publication(invalid['revision']))
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM editions'), 0)
        released = self.ok('/publish', self.publication(valid['revision']))
        self.assertEqual(released['revision'], valid['revision'])

    def test_frozen_revision_and_initialization_preserve_draft(self):
        original = self.publish_sample()
        edited_cues = [{**self.sample['cues'][0], 'text': '次场校样讲词'}, self.sample['cues'][1]]
        edited = self.draft(edited_cues)
        self.assertTrue(edited['passed'])
        self.reopen()
        current = self.ok('/publish', self.publication(edited['revision'], show='同稿次场'))
        self.assertEqual(current['cues'][0]['text'], '次场校样讲词')
        self.assertEqual(self.draft()['revision'], edited['revision'] + 1)
        frozen = self.claim_at('甲', 'frozen')['command']
        self.assertEqual(frozen['text'], '标本采自北坡')
        self.assertEqual(frozen['origin']['revision'], original['revision'])
        self.assertEqual(frozen['origin']['edition_id'], original['edition_id'])

    def test_duplicate_show_does_not_freeze_or_change_seats(self):
        self.publish_sample()
        newer = self.draft()
        self.error(409, 'show_already_bound', '/publish', self.publication(newer['revision'], seats=['丙']))
        self.assertEqual(self.control_count('SELECT COUNT(*) FROM editions'), 1)
        self.assertEqual(self.claim_at('乙', 'still-enabled')['command']['origin']['revision'], 1)
        self.error(404, 'seat_not_enabled', '/claim', {'show_id': self.show, 'seat': '丙', 'request_id': 'wrong'})
