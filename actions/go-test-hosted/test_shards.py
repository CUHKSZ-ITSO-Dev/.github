import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('shards', Path(__file__).with_name('shards.py'))
shards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shards)
capture_spec = importlib.util.spec_from_file_location('capture', Path(__file__).with_name('capture.py'))
capture = importlib.util.module_from_spec(capture_spec)
capture_spec.loader.exec_module(capture)


def make_repo(root):
    repo = Path(root) / 'repo'
    (repo / 'mod').mkdir(parents=True)
    (repo / 'mod' / 'file.txt').write_text('data')
    for command in (['git', 'init', '-q'],
                    ['git', '-c', 'user.email=t@t', '-c', 'user.name=t',
                     'commit', '--allow-empty', '-qm', 'init'],
                    ['git', 'add', '.'],
                    ['git', '-c', 'user.email=t@t', '-c', 'user.name=t',
                     'commit', '-qm', 'add']):
        subprocess.run(command, cwd=repo, check=True, capture_output=True)
    return repo


@unittest.skipUnless(shutil.which('git'), 'git 不可用')
class ParseEnvFileTests(unittest.TestCase):
    def test_assignments_and_heredoc_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            env = Path(root) / 'env'
            env.write_text('A=1\nB<<EOF\nline1\nline2\nEOF\nC=x=y\n')
            self.assertEqual(shards.parse_env_file(env),
                             {'A': '1', 'B': 'line1\nline2', 'C': 'x=y'})

    def test_missing_file_and_malformed_lines_are_ignored(self):
        self.assertEqual(shards.parse_env_file('/nonexistent'), {})
        with tempfile.TemporaryDirectory() as root:
            env = Path(root) / 'env'
            env.write_text('not an assignment\n=bad\nOK=1\n')
            self.assertEqual(shards.parse_env_file(env), {'OK': '1'})


class MainTests(unittest.TestCase):
    def test_groups_json_accepts_lists_of_package_lists(self):
        with tempfile.TemporaryDirectory() as root:
            env = {'PARALLEL_GROUPS': '[["a","b"],["c"]]', 'GITHUB_WORKSPACE': root,
                   'RUNNER_TEMP': root, 'TEST_FLAGS': '', 'PREPARE_COMMAND': '',
                   'POLICY_WORKING_DIRECTORY': '.'}
            calls = []
            with patch.dict(os.environ, env), \
                 patch.object(shards, 'run_group', side_effect=lambda *a, **k: calls.append(a) or (a[0], None, 0)):
                self.assertEqual(shards.main(), 0)
            self.assertEqual([call[1] for call in calls], ['a b', 'c'])


@unittest.skipUnless(shutil.which('git'), 'git 不可用')
class RunGroupTests(unittest.TestCase):
    def test_prepare_env_and_group_index_reach_the_test_command(self):
        with tempfile.TemporaryDirectory() as root:
            repo = make_repo(root)
            temp = Path(root) / 'tmp'
            temp.mkdir()
            with patch.dict(os.environ, {'GITHUB_WORKSPACE': str(repo), 'RUNNER_TEMP': root}):
                _, log, code = shards.run_group(
                    2, 'pkg', repo, 'mod',
                    'echo "MARK=hit" >> "$GITHUB_ENV"', '', temp,
                    test_command='[ "$MARK" = hit ] && [ "$GO_TEST_GROUP_INDEX" = "2" ] '
                                 '&& [ -f file.txt ]')
            self.assertEqual(code, 0)
            self.assertIn('通过', Path(log).read_text())
            self.assertEqual(subprocess.run(['git', 'worktree', 'list', '--porcelain'],
                             cwd=repo, capture_output=True, text=True).stdout.count('worktree'), 1)

    def test_parallel_groups_all_pass_and_leave_no_worktrees(self):
        with tempfile.TemporaryDirectory() as root:
            repo = make_repo(root)
            env = {'PARALLEL_GROUPS': json.dumps([['p'] for _ in range(6)]),
                   'GITHUB_WORKSPACE': str(repo), 'RUNNER_TEMP': root, 'TEST_FLAGS': '',
                   'PREPARE_COMMAND': '', 'POLICY_WORKING_DIRECTORY': 'mod'}
            real = shards.run_group
            with patch.dict(os.environ, env), \
                 patch.object(shards, 'run_group',
                              side_effect=lambda *a: real(*a, test_command='[ -f file.txt ]')):
                self.assertEqual(shards.main(), 0)
            listed = subprocess.run(['git', 'worktree', 'list', '--porcelain'], cwd=repo,
                                    capture_output=True, text=True).stdout
            self.assertEqual(listed.count('worktree '), 1)

    def test_worktree_operations_never_overlap(self):
        active, peak, guard = [0], [0], threading.Lock()

        def fake_git(workspace, *args):
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with guard:
                active[0] -= 1
            return subprocess.CompletedProcess(args, 0, b'', b'')

        with tempfile.TemporaryDirectory() as root, patch.object(shards, 'git', side_effect=fake_git):
            threads = [threading.Thread(target=shards.add_worktree,
                                        args=(i, root, Path(root) / f'ws-{i}', io.BytesIO()))
                       for i in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(peak[0], 1)

    def test_transient_add_failure_is_cleaned_and_retried(self):
        with tempfile.TemporaryDirectory() as root:
            repo = make_repo(root)
            checkout = Path(root) / 'ws-1'
            real, calls = shards.git, []

            def flaky(workspace, *args):
                calls.append(args[:2])
                if args[:2] == ('worktree', 'add') and calls.count(('worktree', 'add')) == 1:
                    return subprocess.CompletedProcess(args, 128, b'', b'fatal: failed to read commondir\n')
                return real(workspace, *args)

            with patch.object(shards, 'git', side_effect=flaky), patch.object(shards.time, 'sleep'):
                self.assertEqual(shards.add_worktree(1, repo, checkout, io.BytesIO()), 0)
            self.assertTrue((checkout / 'mod' / 'file.txt').exists())
            self.assertIn(('worktree', 'prune'), calls)

    def test_setup_failure_is_attributed_and_tests_are_not_run(self):
        with tempfile.TemporaryDirectory() as root:
            repo = make_repo(root)
            temp = Path(root) / 'tmp'
            temp.mkdir()
            marker = Path(root) / 'ran'
            failing = subprocess.CompletedProcess([], 128, b'', b'fatal: boom\n')
            with patch.dict(os.environ, {'GITHUB_WORKSPACE': str(repo), 'RUNNER_TEMP': root}), \
                 patch.object(shards, 'git', return_value=failing), \
                 patch.object(shards.time, 'sleep'):
                _, log, code = shards.run_group(3, 'pkg', repo, '.', '', '', temp,
                                                test_command=f'touch {marker}')
            text = Path(log).read_text()
            self.assertEqual(code, 128)
            self.assertFalse(marker.exists())
            found = capture.PACKAGE_FAILURE.match(text.splitlines()[-1])
            self.assertEqual(found.group(1), '分片3工作区准备失败（git-worktree-exit-128，未执行测试）')

    def test_failure_is_reported_and_worktree_is_removed(self):
        with tempfile.TemporaryDirectory() as root:
            repo = make_repo(root)
            temp = Path(root) / 'tmp'
            temp.mkdir()
            with patch.dict(os.environ, {'GITHUB_WORKSPACE': str(repo), 'RUNNER_TEMP': root}):
                _, log, code = shards.run_group(1, 'pkg', repo, '.', '', '', temp,
                                                test_command='echo boom; exit 3')
            self.assertEqual(code, 3)
            self.assertIn('boom', Path(log).read_text())


if __name__ == '__main__':
    unittest.main()
