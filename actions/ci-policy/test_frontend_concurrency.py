from pathlib import Path
import re
import unittest


class FrontendConcurrencyTest(unittest.TestCase):
    def group(self, browser, pr=293, directory='.', sha='old', profile=''):
        workflow = (Path(__file__).resolve().parents[2] /
                    '.github/workflows/frontend-check.yml').read_text()
        template = re.search(r'^      group: (.+)$', workflow, re.MULTILINE).group(1)
        context = {
            'github.repository': 'CUHKSZ-ITSO-Dev/UI',
            'github.workflow': '前端检查',
            'github.event.pull_request.number': pr,
            'github.ref': f'refs/pull/{pr}/merge',
            'github.sha': sha,
            'inputs.working-directory': directory,
            'inputs.playwright-browsers': browser,
            'inputs.check-profile': profile,
        }

        def resolve(match):
            # These concurrency expressions use context values with || fallbacks.
            for operand in match.group(1).split('||'):
                operand = operand.strip()
                value = operand[1:-1] if operand.startswith("'") else context[operand]
                if value:
                    return str(value)
            return ''

        return re.sub(r'\$\{\{\s*(.*?)\s*\}\}', resolve, template).lower()

    def test_parallel_browsers_do_not_cancel_each_other(self):
        groups = {self.group(browser) for browser in ['chromium', 'firefox', 'webkit']}
        self.assertEqual(len(groups), 3)

    def test_parallel_profiles_do_not_cancel_each_other(self):
        groups = {self.group('', profile=profile)
                  for profile in ['lint', 'chromium', 'firefox', 'webkit']}
        self.assertEqual(len(groups), 4)
        self.assertEqual(self.group('', profile='firefox', sha='old'),
                         self.group('', profile='firefox', sha='new'))

    def test_new_commit_still_supersedes_same_browser(self):
        self.assertEqual(self.group('chromium', sha='old'),
                         self.group('chromium', sha='new'))

    def test_different_prs_and_modules_do_not_cancel_each_other(self):
        self.assertNotEqual(self.group('chromium'), self.group('chromium', pr=294))
        self.assertNotEqual(self.group('chromium'),
                            self.group('chromium', directory='web'))


if __name__ == '__main__':
    unittest.main()
