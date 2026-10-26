import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fallback', Path(__file__).with_name('run.py'))
fallback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fallback)


def status(context=fallback.CONTEXT, state='pending', run=100, attempt=2):
    return {'context': context, 'state': state, 'description': f'run {run} attempt {attempt}：DevPortal 回退'}


class FallbackTests(unittest.TestCase):
    def test_no_disk_error_preserves_original_failure(self):
        with patch.object(fallback, 'disk_exhausted', return_value=False), patch.object(fallback, 'api') as api:
            self.assertEqual(fallback.main(), 1)
            api.assert_not_called()

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

    def test_requests_pending_status_and_waits_for_terminal_state(self):
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/Chat', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_TOKEN='test', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        calls = []

        def api(method, path, token, payload=None):
            calls.append((method, path, payload))
            if method == 'POST':
                return {}
            reads = sum(1 for call in calls if call[0] == 'GET')
            if reads == 1:
                return []  # 尚无任何回退标记：应创建 pending
            if reads == 2:
                return [status(state='pending'), status(state='success', run=99, attempt=1)]
            return [status(state='success')]

        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback, 'api', api):
            self.assertEqual(fallback.main(), 0)
        written = [call for call in calls if call[0] == 'POST']
        self.assertEqual(len(written), 1)
        method, path, payload = written[0]
        self.assertEqual(path, '/repos/CUHKSZ-ITSO-Dev/Chat/statuses/' + 'a' * 40)
        self.assertEqual(payload['state'], 'pending')
        self.assertTrue(payload['description'].startswith('run 100 attempt 2'))
        self.assertTrue(payload['target_url'].endswith('/actions/runs/100/attempts/2'))
        # 轮询只认本 run/attempt 的终态；旧 attempt 的迟到终态不参与判断。
        self.assertEqual(calls[-1][1].startswith('/repos/CUHKSZ-ITSO-Dev/Chat/commits/'), True)

    def test_reuses_existing_pending_marker_without_rewriting(self):
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_TOKEN='test', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        posts = []

        def api(method, path, token, payload=None):
            if method == 'POST':
                posts.append(path)
                return {}
            reads = getattr(api, 'reads', 0) + 1
            api.reads = reads
            if reads == 1:
                return [status(state='pending')]
            return [status(state='success')]

        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback, 'api', api):
            self.assertEqual(fallback.main(), 0)
        self.assertEqual(posts, [])

    def test_missing_write_permission_fails_with_clear_message(self):
        import contextlib, io
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_TOKEN='test', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        out = io.StringIO()

        def api(method, path, token, payload=None):
            if method == 'POST':
                raise fallback.HTTPError(path, 403, 'forbidden', None, None)
            return []

        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback, 'api', api), contextlib.redirect_stdout(out):
            self.assertEqual(fallback.main(), 1)
        self.assertIn('statuses: write', out.getvalue())

    def test_newer_attempt_takes_over_and_releases_the_old_runner(self):
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_TOKEN='test', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')

        def api(method, path, token, payload=None):
            return [status(state='pending', run=100, attempt=3)]

        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback, 'api', api):
            self.assertEqual(fallback.main(), 0)

    def test_stale_write_back_from_older_attempt_is_ignored(self):
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_TOKEN='test', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        states = [[status(state='failure', run=100, attempt=1)], [status(state='success')]]

        def api(method, path, token, payload=None):
            return states.pop(0) if states else [status(state='success')]

        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback, 'api', api):
            self.assertEqual(fallback.main(), 0)

    def test_transient_api_outage_recovers_within_ten_minutes(self):
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_TOKEN='test', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        monotonic = [0.0]
        reads = []

        def api(method, path, token, payload=None):
            if method == 'POST':
                return {}
            monotonic[0] += 120
            reads.append(1)
            if len(reads) < 5:
                raise fallback.URLError('temporary')
            return [status(state='success')]

        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback.time, 'monotonic', lambda: monotonic[0]), \
                patch.object(fallback, 'api', api):
            self.assertEqual(fallback.main(), 0)
        self.assertEqual(len(reads), 5)

    def test_persistent_api_outage_gives_up_after_ten_minutes(self):
        import contextlib, io
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_TOKEN='test', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        monotonic = [0.0]
        out = io.StringIO()

        def api(method, path, token, payload=None):
            if method == 'POST':
                return {}
            monotonic[0] += 120
            raise fallback.URLError('down')

        with patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), \
                patch.object(fallback.time, 'sleep'), patch.object(fallback.time, 'monotonic', lambda: monotonic[0]), \
                patch.object(fallback, 'api', api), contextlib.redirect_stdout(out):
            self.assertEqual(fallback.main(), 1)
        self.assertIn('连续 10 分钟不可读', out.getvalue())


if __name__ == '__main__':
    unittest.main()
