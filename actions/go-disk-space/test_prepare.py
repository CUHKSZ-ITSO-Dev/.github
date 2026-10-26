import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location('disk_prepare', Path(__file__).with_name('prepare.py'))
disk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disk)


class PrepareTests(unittest.TestCase):
    def test_enough_space_cleans_nothing(self):
        removed = disk.prepare('/ws', 8, free=lambda: 12 * 1024 ** 3,
                               remove=MagicMock(side_effect=AssertionError('不应清理')),
                               exists=lambda path: True,
                               prune_images=MagicMock(side_effect=AssertionError('不应清理')))
        self.assertEqual(removed, [])

    def test_shortage_removes_every_sdk_and_hosted_tool_except_go(self):
        removed_at = []
        with tempfile.TemporaryDirectory() as toolcache:
            for name in ('go', 'node', 'CodeQL', 'python'):
                Path(toolcache, name).mkdir()
            removed = disk.prepare('/ws', 8, free=lambda: 6 * 1024 ** 3,
                                   remove=removed_at.append,
                                   exists=lambda path: '/opt/ghc' not in path,
                                   prune_images=lambda: [], hosted_root=toolcache)
            self.assertEqual(removed, removed_at)
        self.assertIn('/usr/share/dotnet', removed_at)
        self.assertIn('/usr/local/lib/android', removed_at)
        self.assertIn(str(Path(toolcache, 'CodeQL')), removed_at)
        self.assertIn(str(Path(toolcache, 'python')), removed_at)
        self.assertNotIn(str(Path(toolcache, 'go')), removed_at)

    def test_shortage_prunes_docker_images_but_keeps_database_images(self):
        commands = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            if command[:2] == ['docker', 'images']:
                fake = MagicMock(returncode=0)
                fake.stdout = ('abc123 postgres:18.6\ndef456 alpine:3\n'
                               'def456 alpine:latest\n789aaa mcr.microsoft.com/mssql/server:2025\n')
                return fake
            fake = MagicMock(returncode=0 if command[-1] == 'def456' else 1)
            return fake

        removed = disk.prepare('/ws', 8, free=lambda: 6 * 1024 ** 3,
                               remove=lambda path: None, exists=lambda path: False,
                               prune_images=lambda: disk.prune_foreign_docker_images(fake_run))
        removals = [command[-1] for command in commands if command[:2] == ['docker', 'rmi']]
        self.assertEqual(removals, ['def456'], '数据库镜像与已删镜像不得重复 rmi')
        self.assertIn('alpine:3', removed)
        self.assertNotIn('postgres:18.6', removed)
        self.assertNotIn('mcr.microsoft.com/mssql/server:2025', removed)

    def test_docker_absent_skips_prune(self):
        with patch('shutil.which', return_value=None):
            self.assertEqual(disk.prune_foreign_docker_images(), [])


if __name__ == '__main__':
    unittest.main()
