from pathlib import Path
import unittest
from run import docker_command

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


if __name__ == '__main__':
    unittest.main()
