import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('capture', Path(__file__).with_name('capture.py'))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureTests(unittest.TestCase):
    def test_ordinary_failure_is_not_a_disk_failure(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root):
            self.assertEqual(capture.capture('echo assertion failed; exit 1'), 1)
            self.assertFalse(capture.marker().exists())

    def test_disk_error_marks_failure_and_releases_reserve(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root):
            reserve = Path(root) / 'go-test-handoff-reserve'
            reserve.write_text('reserve')
            self.assertEqual(capture.capture('echo "No space left on device"; exit 1'), 1)
            self.assertTrue(capture.marker().exists())
            self.assertFalse(reserve.exists())

    def test_successful_output_does_not_request_fallback(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root):
            self.assertEqual(capture.capture('echo "test case: No space left on device"'), 0)
            self.assertFalse(capture.marker().exists())

    def test_ordinary_failure_records_failed_test_names(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root):
            self.assertEqual(capture.capture(
                "echo '--- FAIL: TestAlpha (0.1s)'; echo '--- FAIL: TestBeta'; "
                "printf 'FAIL\texample/pkg\t1.2s\n'; exit 1"), 1)
            self.assertFalse(capture.marker().exists())
            self.assertEqual(capture.summary_marker().read_text().strip(),
                             'TestAlpha、TestBeta、example/pkg')

    def test_disk_failure_does_not_record_test_summary(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root):
            self.assertEqual(capture.capture(
                "echo '--- FAIL: TestAlpha'; echo 'no space left on device'; exit 1"), 1)
            self.assertTrue(capture.marker().exists())
            self.assertFalse(capture.summary_marker().exists())
            self.assertIn('ENOSPC', capture.reason_marker().read_text())

    def test_preflight_records_space_shortage_reason(self):
        from collections import namedtuple
        usage = namedtuple('Usage', 'total used free')
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root, GITHUB_WORKSPACE=root, MINIMUM_FREE_GIB='20', GITHUB_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth'), patch.object(capture.shutil, 'disk_usage', return_value=usage(100, 95, 7.8 * 1024 ** 3)):
            self.assertEqual(capture.check_space(), 125)
            reason = capture.reason_marker().read_text()
            self.assertIn('7.8 GiB', reason)
            self.assertIn('20 GiB', reason)

    def test_preflight_detects_low_space_only_for_supported_fallback(self):
        from collections import namedtuple
        usage = namedtuple('Usage', 'total used free')
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root, GITHUB_WORKSPACE=root, MINIMUM_FREE_GIB='20', GITHUB_REPOSITORY='CUHKSZ-ITSO-Dev/Chat'), patch.object(capture.shutil, 'disk_usage', return_value=usage(100, 95, 5 * 1024 ** 3)):
            self.assertEqual(capture.check_space(), 125)
            self.assertTrue(capture.marker().exists())
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, RUNNER_TEMP=root, GITHUB_WORKSPACE=root, MINIMUM_FREE_GIB='20', GITHUB_REPOSITORY='example/other'), patch.object(capture.shutil, 'disk_usage', return_value=usage(100, 95, 5 * 1024 ** 3)):
            self.assertEqual(capture.check_space(), 0)
            self.assertFalse(capture.marker().exists())


if __name__ == '__main__':
    unittest.main()
