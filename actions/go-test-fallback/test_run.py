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

    def test_waits_for_real_result_using_stable_identity(self):
        env = dict(FALLBACK_REPOSITORY='CUHKSZ-ITSO-Dev/Chat', FALLBACK_COMMIT='a' * 40,
                   RUNNER_TEMP='/tmp', FALLBACK_RUN_ID='100', FALLBACK_RUN_ATTEMPT='2')
        for phase, expected in [('Succeeded', 0), ('Failed', 1), ('Stale', 1)]:
            with self.subTest(phase=phase), patch.dict(os.environ, env), patch.object(fallback, 'disk_exhausted', return_value=True), patch.object(fallback.time, 'sleep'), patch.object(fallback, 'request_result', side_effect=[dict(phase='Queued', message='waiting'), dict(phase=phase, message='result')]) as request:
                self.assertEqual(fallback.main(), expected)
                self.assertEqual(request.call_args_list[0], request.call_args_list[1])
                self.assertEqual(request.call_args.args[0]['commit'], 'a' * 40)


if __name__ == '__main__':
    unittest.main()
