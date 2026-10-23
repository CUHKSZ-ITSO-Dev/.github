from plan import parse_rows, plan, select_targets, shard_groups
import unittest


ROWS = [
    {'path': 'example/api', 'dir': 'api', 'imports': {'example/core', 'fmt'},
     'embeds': [], 'tests': 2},
    {'path': 'example/core', 'dir': 'core', 'imports': {'example/util'},
     'embeds': [], 'tests': 0},
    {'path': 'example/util', 'dir': 'util', 'imports': set(), 'embeds': [], 'tests': 1},
    {'path': 'example/cmd', 'dir': 'cmd', 'imports': {'example/api'}, 'embeds': [],
     'tests': 0},
    {'path': 'example/migrate', 'dir': 'migrate', 'imports': set(),
     'embeds': ['migrations/*.sql', 'all:static'], 'tests': 1},
]


class SelectTargetsTest(unittest.TestCase):
    def select(self, files, rows=None):
        return select_targets(files, rows if rows is not None else ROWS)

    def test_changed_source_covers_reverse_import_closure(self):
        targets, _ = self.select(['util/helper.go'])
        self.assertEqual(targets, {'example/util', 'example/core', 'example/api',
                                   'example/cmd'})

    def test_test_file_change_only_runs_owning_package(self):
        targets, _ = self.select(['api/handler_test.go'])
        self.assertEqual(targets, {'example/api'})

    def test_testdata_maps_to_containing_package(self):
        targets, _ = self.select(['core/testdata/fixture.json'])
        self.assertIn('example/core', targets)

    def test_embed_patterns_map_to_embedding_package(self):
        for file in ('migrate/migrations/000001_up.sql', 'migrate/static/app.js'):
            targets, _ = self.select([file])
            self.assertIn('example/migrate', targets, file)

    def test_module_and_vendor_changes_run_everything(self):
        for file in ('go.mod', 'go.sum', 'go.work', 'sub/go.mod',
                     'vendor/lib/x.go'):
            self.assertIsNone(self.select([file])[0], file)

    def test_unmapped_change_cannot_prove_coverage(self):
        for file in ('manifest/config/config.yaml', 'scripts/tool.sh',
                     'docs/guide.md', 'unknown/x.go'):
            self.assertIsNone(self.select([file])[0], file)

    def test_ignored_paths_skip_unmapped_files(self):
        targets, reason = select_targets(
            ['util/helper.go', 'docs/guide.md'], ROWS,
            ignored_patterns=('**/docs/**',))
        self.assertIn('example/util', targets)
        self.assertIn('忽略', reason)
        self.assertIsNone(select_targets(['docs/guide.md'], ROWS,
                                         ignored_patterns=('**/docs/**',))[0])

    def test_literal_reference_maps_runtime_dependency(self):
        texts = {'example/migrate': 'data, _ := os.ReadFile("../../../../scripts/fix.sql")'}
        targets, _ = select_targets(['scripts/fix.sql'], ROWS, texts=texts)
        self.assertIn('example/migrate', targets)
        targets, _ = select_targets(['mod/scripts/fix.sql'], ROWS,
                                    module_root='mod', texts=texts)
        self.assertIn('example/migrate', targets)

    def test_nested_module_file_is_skipped(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, 'mod', 'tools', 'gen')
            os.makedirs(nested)
            open(os.path.join(nested, 'go.mod'), 'w').close()
            targets, _ = select_targets(
                ['util/helper.go', 'mod/tools/gen/x.go'], ROWS,
                module_root='mod', workspace=tmp, texts={})
            self.assertIn('example/util', targets)

    def test_root_package_owns_root_file(self):
        rows = [{'path': 'example/root', 'dir': '.', 'imports': set(),
                 'embeds': [], 'tests': 1}]
        targets, _ = self.select(['main.go'], rows)
        self.assertEqual(targets, {'example/root'})


class ShardGroupsTest(unittest.TestCase):
    def test_split_is_deterministic_and_covers_all(self):
        targets = {row['path'] for row in ROWS}
        first = shard_groups(ROWS, targets, 2)
        self.assertEqual(first, shard_groups(ROWS, targets, 2))
        merged = sorted(path for group in first for path in group)
        self.assertEqual(merged, sorted(targets))
        self.assertEqual(len(first), 2)

    def test_heavier_packages_spread_across_shards(self):
        first, second = shard_groups(ROWS, {row['path'] for row in ROWS}, 2)
        weights = {row['path']: 1 + row['tests'] for row in ROWS}
        self.assertAlmostEqual(sum(weights[p] for p in first),
                               sum(weights[p] for p in second), delta=1)

    def test_shards_never_exceed_targets(self):
        groups = shard_groups(ROWS, {'example/util'}, 4)
        self.assertEqual(groups, [['example/util']])


class PlanTest(unittest.TestCase):
    POLICY = {'test-selection': 'true', 'test-shards': '2'}

    def test_pr_with_reliable_files_selects_affected(self):
        matrix, mode, _ = plan(self.POLICY, 'pull_request', 'true',
                               ['util/helper.go'], ROWS)
        self.assertEqual(mode, 'affected')
        legs = [entry['packages'].split() for entry in matrix['include']]
        self.assertEqual(sorted(p for leg in legs for p in leg),
                         sorted({'example/util', 'example/core', 'example/api',
                                 'example/cmd'}))

    def test_unmapped_change_falls_back_to_all_shards(self):
        matrix, mode, _ = plan(self.POLICY, 'pull_request', 'true',
                               ['config.yaml'], ROWS)
        self.assertEqual(mode, 'all')
        legs = [p for entry in matrix['include'] for p in entry['packages'].split()]
        self.assertEqual(sorted(legs), sorted(row['path'] for row in ROWS))

    def test_non_pr_and_unreliable_evidence_run_everything(self):
        for event, reliable in [('push', 'true'), ('pull_request', 'false')]:
            matrix, mode, _ = plan(self.POLICY, event, reliable,
                                   ['util/helper.go'], ROWS)
            self.assertEqual(mode, 'all')
            legs = [p for entry in matrix['include'] for p in entry['packages'].split()]
            self.assertEqual(len(legs), len(ROWS))

    def test_missing_listing_and_defaults_return_plain_sweep(self):
        for policy in ({}, self.POLICY):
            matrix, mode, _ = plan(policy, 'pull_request', 'true',
                                   ['util/helper.go'], None)
            self.assertEqual(matrix, {'include': [{'index': 1, 'packages': './...'}]})
            self.assertEqual(mode, 'bypassed')

    def test_disabled_selection_shards_everything(self):
        matrix, mode, _ = plan({'test-selection': 'false', 'test-shards': '2'},
                               'pull_request', 'true', ['util/helper.go'], ROWS)
        self.assertEqual(mode, 'all')
        self.assertEqual(len(matrix['include']), 2)

    def test_single_runner_merges_groups_into_one_labeled_entry(self):
        import json
        policy = dict(self.POLICY, **{'single-runner': 'true'})
        matrix, mode, _ = plan(policy, 'pull_request', 'true',
                               ['util/helper.go'], ROWS)
        self.assertEqual(mode, 'affected')
        entry, = matrix['include']
        self.assertEqual(entry['label'], '全部')
        groups = json.loads(entry['groups'])
        self.assertGreater(len(groups), 1)
        merged = sorted(pkg for group in groups for pkg in group)
        self.assertEqual(merged, sorted(entry['packages'].split()))

    def test_single_runner_bypassed_entry_is_labeled(self):
        matrix, mode, _ = plan({'single-runner': 'true'}, 'pull_request', 'true',
                               ['util/helper.go'], None)
        self.assertEqual(mode, 'bypassed')
        self.assertEqual(matrix['include'][0]['label'], '全部')


if __name__ == '__main__':
    unittest.main()
