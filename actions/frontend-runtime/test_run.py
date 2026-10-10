from pathlib import Path
import unittest
import os
import subprocess
import tempfile
from unittest.mock import patch
from run import docker_command, main

IMAGE = 'mcr.microsoft.com/playwright:v1.62.1-noble@sha256:' + 'a' * 64


class RuntimeTest(unittest.TestCase):
    def command(self, **kwargs):
        values = dict(image=IMAGE, workspace='/workspace', directory='web',
                      node='/tools/node/bin/node', pnpm='/tools/pnpm/bin/pnpm',
                      uid=1001, gid=1001, command='pnpm run test:e2e\n')
        return docker_command(**(values | kwargs))

    def test_preserves_full_command_without_shell_interpolation(self):
        command = 'pnpm test:e2e --browser=webkit --workers=2\nprintf "%s" "literal $(text)"'
        args = self.command(command=command)
        self.assertEqual(args[-1], 'mkdir -p "$HOME"\n' + command)
        self.assertIn('--network=host', args)
        self.assertIn('1001:1001', args)
        self.assertIn('PLAYWRIGHT_BROWSERS_PATH=/ms-playwright', args)
        self.assertIn('/tools/pnpm:/tools/pnpm:ro', args)
        self.assertIn('/tools/node:/tools/node:ro', args)
        self.assertIn('/workspace:/workspace', args)
        self.assertNotIn('GITHUB_TOKEN', ' '.join(args))

    def test_unpinned_and_unrelated_images_are_rejected(self):
        for image in ['mcr.microsoft.com/playwright:latest', IMAGE.replace('mcr.microsoft.com', 'example.com')]:
            with self.assertRaises(ValueError):
                self.command(image=image)

    def test_directory_escape_is_rejected(self):
        for directory in ['../outside', '/outside']:
            with self.assertRaises(ValueError):
                self.command(directory=directory)


    def test_version_mismatch_fails_before_container_execution(self):
        env = {'FRONTEND_IMAGE': IMAGE.replace('v1.62.1', 'v1.62.2'),
               'GITHUB_WORKSPACE': '/workspace', 'FRONTEND_DIRECTORY': 'web',
               'FRONTEND_COMMAND': 'pnpm test:e2e'}
        with patch.dict(os.environ, env), patch('run.shutil.which', side_effect=['/tools/node/bin/node', '/tools/pnpm/bin/pnpm']), patch('run.subprocess.check_output', return_value='1.62.1\n'), patch('run.subprocess.run') as execute:
            with self.assertRaisesRegex(ValueError, '版本不匹配'):
                main()
            execute.assert_not_called()

    def test_browser_failure_is_not_converted_to_success(self):
        env = {'FRONTEND_IMAGE': IMAGE, 'GITHUB_WORKSPACE': '/workspace',
               'FRONTEND_DIRECTORY': 'web', 'FRONTEND_COMMAND': 'pnpm test:e2e'}
        with tempfile.TemporaryDirectory() as workspace, patch.dict(os.environ, env | {'GITHUB_WORKSPACE': workspace}), patch('run.shutil.which', side_effect=['/tools/node/bin/node', '/tools/pnpm/bin/pnpm']), patch('run.subprocess.check_output', return_value='1.62.1\n'), patch('run.subprocess.run', side_effect=[None, subprocess.CalledProcessError(1, ['docker'])]):
            with self.assertRaises(subprocess.CalledProcessError):
                main()


if __name__ == '__main__':
    unittest.main()
