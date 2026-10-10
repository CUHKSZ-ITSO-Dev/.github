import unittest
from plan import plan


class ScopeTest(unittest.TestCase):
    def result(self, **kwargs):
        args = dict(event_name='pull_request', event={'pull_request': {'changed_files': 1}},
                    skip_draft=True, outcome='success', changed='false', always='false',
                    files=['README.md'])
        args.update(kwargs)
        return plan(**args)

    def test_unrelated_pr_skips_but_related_and_always_run(self):
        self.assertEqual(self.result()[:2], (False, True))
        self.assertTrue(self.result(changed='true')[0])
        self.assertTrue(self.result(always='true')[0])

    def test_detector_failure_and_missing_outputs_run_conservatively(self):
        for change in [dict(outcome='failure'), dict(changed=''), dict(files=None),
                       dict(files=['README.md', 42])]:
            self.assertEqual(self.result(**change)[:2], (True, False))

    def test_truncated_api_and_missing_count_cannot_skip(self):
        for count in [2, 3000, 3001, None]:
            event = {'pull_request': {'changed_files': count}}
            self.assertEqual(self.result(event=event)[:2], (True, False))

    def test_renames_include_both_paths(self):
        self.assertEqual(self.result(files=['old.py', 'new.py'], changed='true')[:2],
                         (True, True))

    def test_dispatch_queue_and_schedule_run_full(self):
        for event in ['workflow_dispatch', 'merge_group', 'schedule', 'release']:
            self.assertEqual(self.result(event_name=event)[:2], (True, False))

    def test_draft_skip_is_explicit_and_opt_out_works(self):
        event = {'pull_request': {'draft': True, 'changed_files': 1}}
        self.assertFalse(self.result(event=event, outcome='failure')[0])
        self.assertTrue(self.result(event=event, skip_draft=False, changed='true')[0])

    def test_push_filters_remain_compatible(self):
        self.assertEqual(self.result(event_name='push', event={})[:2], (False, True))


if __name__ == '__main__':
    unittest.main()
