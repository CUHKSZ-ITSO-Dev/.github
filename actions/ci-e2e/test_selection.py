import json
from pathlib import Path
import tempfile
import unittest
from selection import select


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


if __name__ == '__main__':
    unittest.main()
