import json
from pathlib import Path
import tempfile
import unittest
from selection import select, browser_required


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        self.config = json.loads(Path(__file__).with_name('ui.json').read_text())
        self.preview = self.config['groups'][0]['tests'][0]
        for path in [*self.config['smoke'], self.preview, 'playwright/new.spec.ts']:
            file = self.workspace / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('test fixture')

    def result(self, files, **kwargs):
        args = dict(event='pull_request', repository='CUHKSZ-ITSO-Dev/UI', profile='webkit',
                    reliable=True, files=files, config=self.config, workspace=self.workspace)
        args.update(kwargs)
        return select(**args)[0]

    def test_preview_includes_smoke(self):
        for path in self.config['groups'][0]['sources']:
            self.assertEqual(set(self.result([path])), {*self.config['smoke'], self.preview})

    def test_test_only_change_selects_new_test_and_smoke(self):
        self.assertEqual(set(self.result(['playwright/new.spec.ts'])),
                         {*self.config['smoke'], 'playwright/new.spec.ts'})

    def test_global_critical_and_unmapped_changes_always_run_full(self):
        for path in ['pnpm-lock.yaml', 'src/router.tsx', 'src/index.css', 'src/stores/a.ts',
                     'playwright/fixtures/bootstrapMocks.ts', 'playwright.config.ts', 'src/components/UpdateNotification/AnnouncementCard.tsx',
                     'src/components/UpdateNotification/UpdateNotificationContent.tsx',
                     'src/pages/NewPage.tsx', "x'; touch /tmp/untrusted; '"]:
            self.assertEqual(self.result([self.config['groups'][0]['sources'][0], path]), [], path)

    def test_other_events_profiles_and_unreliable_evidence_run_full(self):
        for args in [dict(event='push'), dict(event='workflow_dispatch'), dict(event='merge_group'),
                     dict(profile='lint'), dict(profile=''), dict(repository='Other/UI'),
                     dict(reliable=False)]:
            self.assertEqual(self.result([self.preview], **args), [])
        self.assertEqual(self.result([]), [])

    def test_missing_deleted_or_renamed_test_falls_back_full(self):
        (self.workspace / self.preview).unlink()
        self.assertEqual(self.result([self.config['groups'][0]['sources'][0]]), [])
        self.assertEqual(self.result([self.preview, 'playwright/new.spec.ts']), [])

    def test_renamed_source_cannot_hide_unknown_old_path(self):
        self.assertEqual(self.result(['src/pages/OtherPage.tsx',
                                     self.config['groups'][0]['sources'][0]]), [])

class UniAuthSelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        self.config = json.loads(Path(__file__).with_name('uniauth.json').read_text())
        for path in [*self.config['smoke'], *self.config['groups'][0]['tests'], 'tests/ui/new.spec.ts']:
            file = self.workspace / 'uniauth-vite' / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('fixture')

    def result(self, files, **kwargs):
        args = dict(event='pull_request', repository='CUHKSZ-ITSO-Dev/UniAuth', profile='',
                    reliable=True, files=files, config=self.config, workspace=self.workspace)
        args.update(kwargs)
        return select(**args)[0]

    def test_verified_sources_and_changed_specs_include_smoke(self):
        for source in self.config['groups'][0]['sources']:
            self.assertEqual(set(self.result(['uniauth-vite/' + source])),
                             {*self.config['smoke'], *self.config['groups'][0]['tests']})
        self.assertEqual(set(self.result(['uniauth-vite/tests/ui/new.spec.ts'])),
                         {*self.config['smoke'], 'tests/ui/new.spec.ts'})

    def test_shared_unknown_dependencies_and_missing_specs_fallback(self):
        for path in ['src/components/ui/overflowScroll.css', 'src/App.tsx', 'pnpm-lock.yaml',
                     'tests/ui/strict-api-mock.ts', 'src/pages/NewPage/index.tsx', 'playwright.config.ts']:
            self.assertEqual(self.result(['uniauth-vite/' + path]), [], path)
        (self.workspace / 'uniauth-vite' / self.config['groups'][0]['tests'][0]).unlink()
        self.assertEqual(self.result(['uniauth-vite/' + self.config['groups'][0]['sources'][0]]), [])

    def test_ci_mode_uses_reliable_paths_without_shell_injection(self):
        from selection import selected_command
        import shlex
        package = self.workspace / 'uniauth-vite/package.json'
        package.write_text(json.dumps({'scripts': {'check:ci': 'node scripts/run-checks.mjs --ci'}}))
        paths = ["uniauth-vite/src/x'; touch /tmp/untrusted; '.ts"]
        command = selected_command('CUHKSZ-ITSO-Dev/UniAuth', True, paths, [], 'pnpm run check', self.workspace)
        tokens = shlex.split(command)
        self.assertEqual(json.loads(tokens[0].split('=', 1)[1]), paths)
        self.assertEqual(tokens[-3:], ['pnpm', 'run', 'check:ci'])
        self.assertEqual(selected_command('CUHKSZ-ITSO-Dev/UniAuth', False, paths, [], 'pnpm run check', self.workspace), 'pnpm run check')
        package.write_text('{"scripts": {"check:ci": "true"}}')
        self.assertEqual(selected_command('CUHKSZ-ITSO-Dev/UniAuth', True, paths, [], 'pnpm run check', self.workspace), 'pnpm run check')
        package.write_text('{"scripts": {}}')
        self.assertEqual(selected_command('CUHKSZ-ITSO-Dev/UniAuth', True, paths, [], 'pnpm run check', self.workspace), 'pnpm run check')

    def test_docs_skip_browser_install_but_embedded_markdown_does_not(self):
        args = ('pull_request', 'CUHKSZ-ITSO-Dev/UniAuth', True)
        self.assertFalse(browser_required(*args, ['docs/规范/前端/README.md']))
        self.assertTrue(browser_required(*args, ['uniauth-vite/src/help.md']))
        self.assertTrue(browser_required('push', 'CUHKSZ-ITSO-Dev/UniAuth', True, ['README.md']))
        self.assertTrue(browser_required('pull_request', 'CUHKSZ-ITSO-Dev/UniAuth', False, ['README.md']))

    def test_ci_only_skips_dependencies_only_for_new_registered_runner(self):
        from selection import selected_command
        package = self.workspace / 'uniauth-vite/package.json'
        package.write_text(json.dumps({'scripts': {'check:ci': 'node scripts/run-checks.mjs --ci'}}))
        paths = ['.github/workflows/frontend-lint.yml']
        command = selected_command('CUHKSZ-ITSO-Dev/UniAuth', True, paths, [], 'pnpm run check', self.workspace)
        self.assertTrue(command.startswith("echo 'CI 入口"))
        self.assertEqual(selected_command('CUHKSZ-ITSO-Dev/UniAuth', False, paths, [], 'pnpm run check', self.workspace), 'pnpm run check')
        self.assertIn('UNIAUTH_CHECK_PATHS_JSON=', selected_command('CUHKSZ-ITSO-Dev/UniAuth', True,
                      paths + ['uniauth-vite/src/new.ts'], [], 'pnpm run check', self.workspace))


if __name__ == '__main__':
    unittest.main()
