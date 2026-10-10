import unittest
import json
from pathlib import Path
import tempfile
from compare import inventory, compare


def report(status='expected', expected='passed'):
    return {'stats': {'duration': 1000}, 'suites': [{'suites': [{'specs': [{'id': 'case', 'title': '真实页面',
             'tests': [{'projectName': '', 'expectedStatus': expected, 'status': status}]}]}]}]}


class CoverageTest(unittest.TestCase):
    def test_nested_test_identity_and_skip_state_are_preserved(self):
        self.assertEqual(inventory(report()), {('case', ''): ('passed', 'expected')})
        mixed = report()
        mixed['suites'][0]['specs'] = [{'id': 'unsupported', 'title': '浏览器专属能力',
             'tests': [{'projectName': '', 'expectedStatus': 'skipped', 'status': 'skipped'}]}]
        self.assertEqual(len(inventory(mixed)), 2)

    def test_failure_flakiness_and_zero_execution_are_rejected(self):
        for status in ['unexpected', 'flaky', 'skipped']:
            with self.assertRaises(ValueError):
                inventory(report(status))
        with self.assertRaises(ValueError):
            inventory({'suites': []})

    def test_duplicate_identity_is_rejected(self):
        data = report()
        data['suites'].append(data['suites'][0])
        with self.assertRaises(ValueError):
            inventory(data)


class ComparisonTest(unittest.TestCase):
    def test_changed_or_missing_coverage_cannot_pass_benchmark(self):
        with tempfile.TemporaryDirectory() as root:
            for browser in ['chromium', 'firefox', 'webkit']:
                for workers in [1, 2]:
                    directory = Path(root) / f'frontend-{browser}-{workers}' / 'test-results'
                    directory.mkdir(parents=True)
                    (directory / 'results.json').write_text(json.dumps(report()))
            self.assertIn('| webkit | 1 | 1.0s | 1.0s |', compare(root))
            target = Path(root) / 'frontend-webkit-2' / 'test-results' / 'results.json'
            changed = report()
            changed['suites'][0]['suites'][0]['specs'][0]['id'] = 'different-case'
            target.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, '不一致'):
                compare(root)
            target.unlink()
            with self.assertRaisesRegex(ValueError, '完整报告'):
                compare(root)
