import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fallback', Path(__file__).with_name('run.py'))
fallback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fallback)


class FallbackTests(unittest.TestCase):
    def test_no_disk_error_preserves_original_failure(self):
        with patch.object(fallback, 'disk_exhausted', return_value=False), patch.object(fallback, 'request_result') as request:
            self.assertEqual(fallback.main(), 1)
            request.assert_not_called()

    def test_failure_summary_names_tests_without_fallback(self):
        import contextlib, io, tempfile
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'go-test-failure-summary').write_text('TestAlpha、TestBeta\n')
            env = dict(RUNNER_TEMP=root, FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth')
            out = io.StringIO()
            with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=False), contextlib.redirect_stdout(out):
                self.assertEqual(fallback.main(), 1)
            self.assertIn('TestAlpha', out.getvalue())

    def test_disk_exhaustion_without_allowlist_reports_missing_fallback(self):
        import contextlib, io
        env = dict(RUNNER_TEMP='/tmp', FALLBACK_REPOSITORY='example/other')
        out = io.StringIO()
        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), contextlib.redirect_stdout(out):
            self.assertEqual(fallback.main(), 1)
        self.assertIn('未启用 DevPortal 回退', out.getvalue())

    def test_waits_for_real_result_using_stable_identity(self):
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/Chat', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        for phase, expected in [('Succeeded', 0), ('Failed', 1), ('Stale', 1)]:
            with self.subTest(phase=phase), patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), patch.object(fallback.time, 'sleep'), patch.object(fallback, 'request_result', side_effect=[dict(phase='Queued', message='waiting'), dict(phase=phase, message='result')]) as request:
                self.assertEqual(fallback.main(), expected)
                self.assertEqual(request.call_args_list[0], request.call_args_list[1])
                self.assertEqual(request.call_args.args[0]['commit'], 'a' * 40)

    def test_transient_outage_recovers_and_succeeds(self):
        import contextlib, io
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        monotonic = [0.0]
        attempts = []

        def request(_payload):
            monotonic[0] += 120  # 每次尝试间隔 2 分钟，共 4 次失败仍未达 10 分钟容忍线
            attempts.append(1)
            if len(attempts) < 5:
                raise fallback.URLError('temporary')
            return dict(phase='Succeeded', message='result')

        out = io.StringIO()
        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback.time, 'monotonic', lambda: monotonic[0]), \
                patch.object(fallback, 'request_result', request), contextlib.redirect_stdout(out):
            self.assertEqual(fallback.main(), 0)
        self.assertEqual(len(attempts), 5)

    def test_persistent_outage_gives_up_after_ten_minutes(self):
        import contextlib, io
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        monotonic = [0.0]

        def request(_payload):
            monotonic[0] += 120
            raise fallback.URLError('down')

        out = io.StringIO()
        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback.time, 'monotonic', lambda: monotonic[0]), \
                patch.object(fallback, 'request_result', request), contextlib.redirect_stdout(out):
            self.assertEqual(fallback.main(), 1)
        self.assertIn('连续 10 分钟不可达', out.getvalue())


if __name__ == '__main__':
    unittest.main()
