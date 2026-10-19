import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('migration_check', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class MigrationFilesTest(unittest.TestCase):
    def test_concurrent_index_must_be_a_single_statement(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            up = directory / '000001_index.up.sql'
            (directory / '000001_index.down.sql').write_text('DROP INDEX CONCURRENTLY test_idx;')
            up.write_text('-- 注释不算语句\nCREATE UNIQUE INDEX CONCURRENTLY test_idx ON test(id);')
            self.assertEqual(check.validate(directory), 1)
            up.write_text(up.read_text() + '\nSELECT 1;')
            with self.assertRaisesRegex(ValueError, 'CONCURRENTLY'):
                check.validate(directory)

    def test_action_process_fails_on_invalid_sql_instead_of_only_logging(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            directory = workspace / 'uniauth-gf/manifest/sql/postgres'
            directory.mkdir(parents=True)
            event = workspace / 'event.json'
            event.write_text(json.dumps({}))
            env = dict(os.environ, GITHUB_REPOSITORY='CUHKSZ-ITSO-Dev/UniAuth',
                       CHECK_ENTRY='pr-check', GITHUB_WORKSPACE=root,
                       GITHUB_EVENT_PATH=str(event), GITHUB_EVENT_NAME='workflow_dispatch')
            for version, expected in [('000001', 0), ('000003', 1)]:
                for path in directory.iterdir():
                    path.unlink()
                for direction in ['up', 'down']:
                    (directory / f'{version}_init.{direction}.sql').write_text('SELECT 1;')
                result = subprocess.run([sys.executable, str(Path(check.__file__))], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_valid_and_invalid_migration_sets(self):
        pair = ['000001_init.up.sql', '000001_init.down.sql']
        cases = [
            (pair, None),
            (pair + ['000002_next.up.sql', '000002_next.down.sql'], None),
            (pair + ['000001_other.up.sql', '000001_other.down.sql'], '编号'),
            (pair + ['000003_next.up.sql', '000003_next.down.sql'], '编号'),
            (['000001_init.up.sql'], '配对'),
            (['000001_init.down.sql'], '配对'),
            (['001_init.up.sql', '001_init.down.sql'], '命名'),
            (['000000_init.up.sql', '000000_init.down.sql'], '编号'),
            (['000001_init_.up.sql'], '命名'),
            (['README.md'], '没有 up'),
            ([], '没有 up'),
        ]
        for names, error in cases:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as root:
                directory = Path(root)
                for name in names:
                    (directory / name).write_text('SELECT 1;\n')
                if error:
                    with self.assertRaisesRegex(ValueError, error):
                        check.validate(directory)
                else:
                    self.assertEqual(check.validate(directory), len(names) // 2)

    def test_missing_directory_and_symlink_fail(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            with self.assertRaisesRegex(ValueError, '不存在'):
                check.validate(directory / 'missing')
            (directory / '000001_init.up.sql').symlink_to('outside.sql')
            with self.assertRaisesRegex(ValueError, '类型'):
                check.validate(directory)

    def test_all_four_sql_repositories_use_the_existing_ci_entry(self):
        for repo, entry, directory in [
            ('Chat', 'pr-check', 'manifest/sql/mssql'),
            ('UniAuth', 'pr-check', 'uniauth-gf/manifest/sql/postgres'),
            ('open-platform', 'pr-check', 'manifest/sql/postgres'),
            ('Doubao-Speech-Service', 'go-test', 'migrations/postgres'),
        ]:
            repository = 'CUHKSZ-ITSO-Dev/' + repo
            self.assertEqual(check.configuration(repository.lower(), entry)['directory'], directory)
            self.assertIsNone(check.configuration(repository, 'wrong-entry'))
        for repo in ['UI', 'Gateway', 'ITSM', 'Docs', 'rag', 'docparse', 'unknown']:
            self.assertIsNone(check.configuration('CUHKSZ-ITSO-Dev/' + repo, 'pr-check'))

    def test_historical_sql_changes_and_deletions_fail(self):
        base = 'a' * 40
        for current in [subprocess.CompletedProcess([], 0, 'original\n'),
                        subprocess.CompletedProcess([], 0, 'changed\n'),
                        subprocess.CompletedProcess([], 128, '')]:
            with self.subTest(current=current), patch.object(check, 'git', side_effect=[
                'sql/000001_init.up.sql\nsql/000001_init.down.sql\n', 'original\n', 'original\n'
            ]), patch.object(check.subprocess, 'run', side_effect=[
                subprocess.CompletedProcess([], 0), current, current
            ]):
                if current.stdout.strip() == 'original':
                    check.protect_history(Path('/workspace'), 'sql', base)
                else:
                    with self.assertRaisesRegex(ValueError, '不能删除、改名或改写'):
                        check.protect_history(Path('/workspace'), 'sql', base)
        with self.assertRaisesRegex(ValueError, '基线'):
            check.protect_history(Path('/workspace'), 'sql', '--invalid')

    def test_sql_gate_is_not_hidden_behind_test_scope_or_draft_filters(self):
        root = Path(__file__).parents[2]
        pr = (root / '.github/workflows/pr-check.yml').read_text()
        go = (root / '.github/workflows/go-test.yml').read_text()
        self.assertLess(pr.index('      - name: Checkout'), pr.index('      - name: 检查迁移文件'))
        self.assertLess(go.index('      - name: 检查迁移文件'), go.index('      - name: 判断检查范围'))
        for workflow in [pr, go]:
            block = workflow.split('      - name: 检查迁移文件\n')[1].split('      - name:')[0]
            self.assertNotIn('if:', block)
            self.assertIn('actions/check-migration-files@main', block)


if __name__ == '__main__':
    unittest.main()
