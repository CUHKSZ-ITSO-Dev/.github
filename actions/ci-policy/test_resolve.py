import json
from fnmatch import fnmatchcase
from pathlib import Path
import unittest
from resolve import resolve


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(Path(__file__).with_name('policy.json').read_text())

    def test_caller_cannot_disable_race_or_replace_preparation(self):
        result = resolve('CUHKSZ-ITSO-Dev/Chat', 'go-test',
                         {'test-flags': '', 'prepare-command': 'true',
                          'changed-paths': 'never/**', 'clean-unused-sdks': False}, self.policy)
        self.assertIn('-race', result['test-flags'])
        self.assertIn('go generate', result['prepare-command'])
        self.assertIn('**/*.go', result['changed-paths'])
        self.assertTrue(result['clean-unused-sdks'])

    def test_disk_headroom_is_central_and_repository_specific(self):
        for repo, expected in [('Chat', 20), ('open-platform', 20), ('UniAuth', 8)]:
            result = resolve(f'CUHKSZ-ITSO-Dev/{repo}', 'go-test',
                             {'minimum-free-disk-gib': 1, 'clean-unused-sdks': False}, self.policy)
            self.assertEqual(result['minimum-free-disk-gib'], expected)
            self.assertTrue(result['clean-unused-sdks'])

    def test_repository_case_cannot_bypass_policy(self):
        result = resolve('cuhksz-itso-dev/chat', 'go-test', {'test-flags': ''}, self.policy)
        self.assertIn('-race', result['test-flags'])

    def test_database_integration_is_preserved(self):
        result = resolve('CUHKSZ-ITSO-Dev/UniAuth', 'go-test', {}, self.policy)
        for variable in ['FEEDBACK_TEST_LINK', 'QUOTA_POOL_TEST_LINK',
                         'MIGRATION_TEST_DATABASE_URL', 'PGADAPTER_TEST_DATABASE_URL',
                         'UNIAUTH_DATABASE_TEST', 'PSQL_WATCHER_TEST_DATABASE_URL',
                         'DASHBOARD_TEST_DATABASE_URL']:
            self.assertIn(variable, result['prepare-command'])
        self.assertIn('echo "UNIAUTH_DATABASE_TEST=1" >> "$GITHUB_ENV"', result['prepare-command'])
        self.assertIn('-race', result['test-flags'])

    def test_new_pr_database_regressions_export_the_prepared_database(self):
        for repo, variables, database in [
            ('UniAuth', ['PSQL_WATCHER_TEST_DATABASE_URL', 'DASHBOARD_TEST_DATABASE_URL'],
             'uniauth_go_test'),
            ('open-platform', ['BINDINGS_TEST_DATABASE_URL'], 'open_platform_go_test'),
        ]:
            result = resolve(f'CUHKSZ-ITSO-Dev/{repo}', 'go-test',
                             {'prepare-command': 'true'}, self.policy)
            for variable in variables:
                self.assertRegex(result['prepare-command'],
                                 rf'echo "{variable}=postgres(?:ql)?://[^\n]+/{database}\?sslmode=disable" >> "\$GITHUB_ENV"')

    def test_database_version_follows_repository_compatibility(self):
        uniauth = resolve('CUHKSZ-ITSO-Dev/UniAuth', 'go-test',
                          {'postgres-image': 'postgres:18'}, self.policy)
        other = resolve('CUHKSZ-ITSO-Dev/open-platform', 'go-test', {}, self.policy)
        self.assertTrue(uniauth['postgres-image'].startswith('postgres:17.11@sha256:'))
        self.assertTrue(other['postgres-image'].startswith('postgres:18.6@sha256:'))

    def test_uniauth_lint_uses_the_checked_out_module_toolchain(self):
        result = resolve('CUHKSZ-ITSO-Dev/UniAuth', 'golangci-lint',
                         {'go-version': '1.26.2', 'go-version-file': ''}, self.policy)
        self.assertEqual(result['go-version-file'], 'uniauth-gf/go.mod')

    def test_uniauth_frontend_caller_cannot_skip_build_or_browser_checks(self):
        result = resolve('CUHKSZ-ITSO-Dev/UniAuth', 'frontend-check',
                         {'check-command': 'pnpm run lint', 'node-version': '20',
                          'pnpm-version': '10.15.1', 'playwright-browsers': '',
                          'changed-paths': 'never/**', 'ignored-paths': '**/*'}, self.policy)
        self.assertEqual(result['check-command'].strip(), 'pnpm run check')
        self.assertEqual(result['playwright-browsers'], 'chromium')
        self.assertEqual(result['node-version'], '26.10.0')
        self.assertEqual(result['pnpm-version'], '12.8.1')
        self.assertEqual(result['ignored-paths'], '')
        patterns = result['changed-paths'].splitlines()
        for changed in ['uniauth-vite/src/pages/Dashboard/index.tsx',
                        'docs/规范/前端/README.md', 'docs/规范/manifest.json',
                        'docs/维护手册.md', 'AGENTS.md',
                        '.github/workflows/frontend-lint.yml',
                        '.github/workflows/frontend-build.yml',
                        '.github/frontend-check-contract.json',
                        'scripts/check_frontend_ci_policy.py',
                        'scripts/test_frontend_ci_policy.py']:
            self.assertTrue(any(fnmatchcase(changed, pattern) for pattern in patterns), changed)

    def test_unknown_managed_profile_fails_closed(self):
        with self.assertRaises(ValueError):
            resolve('CUHKSZ-ITSO-Dev/Chat', 'frontend-check', {'check-command': 'true'}, self.policy)

    def test_unmanaged_repository_keeps_existing_behavior(self):
        result = resolve('CUHKSZ-ITSO-Dev/Example', 'frontend-check',
                         {'check-command': 'pnpm run test:e2e', 'node-version': '24'}, self.policy)
        self.assertEqual(result['check-command'], 'pnpm run test:e2e')
        self.assertEqual(result['node-version'], '24')

    def test_ui_profiles_preserve_checks_and_ignore_caller_overrides(self):
        for profile in ['lint', 'chromium', 'firefox', 'webkit']:
            result = resolve('cuhksz-itso-dev/ui', 'frontend-check',
                             {'check-command': 'true', 'node-version': '99',
                              'ignored-paths': '**/*', 'skip-draft-pr': False,
                              'playwright-image': 'example.com/untrusted:latest'},
                             self.policy, profile)
            self.assertEqual(result['node-version'], '24')
            self.assertEqual(result['pnpm-version'], '12.2.1')
            self.assertEqual(result['ignored-paths'], '**/*.md\n.github/workflows/**\n')
            self.assertEqual(result['always-run-paths'], '')
            self.assertTrue(result['skip-draft-pr'])
            if profile == 'lint':
                self.assertEqual(result['check-command'].splitlines(),
                                 ['pnpm run lint', 'pnpm run i18n:check',
                                  'pnpm run test', 'pnpm run build'])
                self.assertEqual(result['playwright-browsers'], '')
                self.assertEqual(result['playwright-image'], '')
            else:
                self.assertEqual(result['playwright-browsers'], profile)
                self.assertRegex(result['playwright-image'], r'^mcr\.microsoft\.com/playwright:v1\.62\.1-noble@sha256:[0-9a-f]{64}$')
                self.assertEqual(result['check-command'].strip(),
                                 f'pnpm run test:e2e --browser={profile} --workers=2 --forbid-only --reporter=line,json')

    def test_old_ui_entries_keep_full_chromium_and_other_browsers(self):
        for browser in ['chromium', 'firefox', 'webkit', '']:
            result = resolve('CUHKSZ-ITSO-Dev/UI', 'frontend-check',
                             {'playwright-browsers': browser, 'check-command': 'true'}, self.policy)
            self.assertEqual(result['playwright-browsers'], browser)
            if browser == 'chromium':
                self.assertIn('pnpm run lint', result['check-command'])
                self.assertIn('pnpm run build', result['check-command'])
                self.assertEqual(result['check-command'].splitlines()[-1], 'pnpm run test:e2e --workers=2 --forbid-only --reporter=line,json')
            elif browser:
                self.assertEqual(result['check-command'].strip(), f'pnpm run test:e2e --browser={browser} --workers=2 --forbid-only --reporter=line,json')

    def test_unknown_frontend_profiles_fail_closed(self):
        for repo, profile in [('UI', 'unknown'), ('UI', 'legacy-chromium'),
                              ('UniAuth', 'chromium'), ('Example', 'lint')]:
            with self.assertRaises(ValueError):
                resolve(f'CUHKSZ-ITSO-Dev/{repo}', 'frontend-check', {}, self.policy, profile)
        with self.assertRaises(ValueError):
            resolve('CUHKSZ-ITSO-Dev/UI', 'frontend-check',
                    {'playwright-browsers': 'unknown'}, self.policy)

    def test_migration_guards_remain_enabled(self):
        result = resolve('CUHKSZ-ITSO-Dev/open-platform', 'migration-check',
                         {'immutable-migration-files': False, 'full-rollback': False}, self.policy)
        self.assertTrue(result['immutable-migration-files'])
        self.assertTrue(result['full-rollback'])
        self.assertIn('assert_postgres_schema.sql', result['binary-check-command'])

    def test_python_scope_is_central_but_execution_contract_is_preserved(self):
        for kind in ['python-uv-check', 'python-uv-redis-rabbitmq-check']:
            result = resolve('CUHKSZ-ITSO-Dev/doc-intelligence', kind,
                             {'changed-paths': 'never/**', 'ignored-paths': '**/*',
                              'skip-draft-pr': False, 'check-command': 'uv run pytest -m unit',
                              'python-version': '3.13', 'env-vars': 'ENABLE_LLM=false'}, self.policy)
            self.assertIn('app/**', result['changed-paths'])
            self.assertIn('**/*.py', result['changed-paths'])
            self.assertEqual(result['ignored-paths'], '')
            self.assertTrue(result['skip-draft-pr'])
            self.assertEqual(result['check-command'], 'uv run pytest -m unit')
            self.assertEqual(result['python-version'], '3.13')
            self.assertEqual(result['env-vars'], 'ENABLE_LLM=false')

    def test_unmanaged_python_callers_keep_their_scope(self):
        result = resolve('Example/Python', 'python-uv-check',
                         {'changed-paths': 'src/**', 'check-command': 'uv run pytest'}, self.policy)
        self.assertEqual(result['changed-paths'], 'src/**')

    def test_websearch_exclusions_use_or_with_excludes(self):
        result = resolve('CUHKSZ-ITSO-Dev/WebSearch', 'python-uv-check', {}, self.policy)
        self.assertEqual(result['predicate-quantifier'], 'some-with-excludes')
        self.assertIn('docs/**', result['ignored-paths'])


if __name__ == '__main__':
    unittest.main()
