import json
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

    def test_repository_case_cannot_bypass_policy(self):
        result = resolve('cuhksz-itso-dev/chat', 'go-test', {'test-flags': ''}, self.policy)
        self.assertIn('-race', result['test-flags'])

    def test_database_integration_is_preserved(self):
        result = resolve('CUHKSZ-ITSO-Dev/UniAuth', 'go-test', {}, self.policy)
        for variable in ['FEEDBACK_TEST_LINK', 'QUOTA_POOL_TEST_LINK',
                         'MIGRATION_TEST_DATABASE_URL', 'PGADAPTER_TEST_DATABASE_URL']:
            self.assertIn(variable, result['prepare-command'])
        self.assertIn('-race', result['test-flags'])

    def test_unknown_managed_profile_fails_closed(self):
        with self.assertRaises(ValueError):
            resolve('CUHKSZ-ITSO-Dev/Chat', 'frontend-check', {'check-command': 'true'}, self.policy)

    def test_unmanaged_repository_keeps_existing_behavior(self):
        result = resolve('CUHKSZ-ITSO-Dev/UI', 'frontend-check',
                         {'check-command': 'pnpm run test:e2e', 'node-version': '24'}, self.policy)
        self.assertEqual(result['check-command'], 'pnpm run test:e2e')
        self.assertEqual(result['node-version'], '24')

    def test_migration_guards_remain_enabled(self):
        result = resolve('CUHKSZ-ITSO-Dev/open-platform', 'migration-check',
                         {'immutable-migration-files': False, 'full-rollback': False}, self.policy)
        self.assertTrue(result['immutable-migration-files'])
        self.assertTrue(result['full-rollback'])
        self.assertIn('assert_postgres_schema.sql', result['binary-check-command'])


if __name__ == '__main__':
    unittest.main()
