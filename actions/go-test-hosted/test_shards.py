import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('shards', Path(__file__).with_name('shards.py'))
shards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shards)


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
