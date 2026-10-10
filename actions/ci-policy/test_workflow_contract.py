import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WorkflowContractTest(unittest.TestCase):
    def test_existing_workflow_and_job_names_remain_stable(self):
        identities = json.loads(Path(__file__).with_name('workflow-identities.json').read_text())
        for path, expected in identities.items():
            source = (ROOT / path).read_text()
            self.assertEqual(re.search(r'^name: (.+)$', source, re.M).group(1), expected['name'])
            for job, name in expected['jobs'].items():
                block = re.search(r'^  ' + re.escape(job) + r':\n(.*?)(?=^  \w[^\n]*:|\Z)',
                                  source, re.M | re.S)
                self.assertIsNotNone(block, f'{path}/{job}')
                self.assertEqual(re.search(r'^    name: (.+)$', block.group(1), re.M).group(1), name)

    def test_service_job_only_skips_for_explicit_successful_scope(self):
        source = (ROOT / '.github/workflows/python-uv-redis-rabbitmq-check.yml').read_text()
        predicate = re.search(r'^    if: (.+)$', source, re.M).group(1)
        self.assertIn('!cancelled()', predicate)
        self.assertIn("needs.scope.result != 'success'", predicate)
        self.assertIn("needs.scope.outputs.run != 'false'", predicate)
        # Truth table for the declared contract, including absent outputs.
        for result, run, expected in [('success', 'false', False), ('success', 'true', True),
                                      ('success', '', True), ('failure', '', True),
                                      ('skipped', '', True)]:
            expression = predicate.removeprefix('${{').removesuffix('}}').strip()
            expression = expression.replace('!cancelled()', 'True')
            expression = expression.replace('needs.scope.result', repr(result))
            expression = expression.replace('needs.scope.outputs.run', repr(run))
            expression = expression.replace('&&', ' and ').replace('||', ' or ')
            self.assertEqual(eval(expression, {'__builtins__': {}}, {}), expected)
        cancelled = predicate.removeprefix('${{').removesuffix('}}').strip()
        cancelled = cancelled.replace('!cancelled()', 'False')
        cancelled = cancelled.replace('needs.scope.result', repr('failure'))
        cancelled = cancelled.replace('needs.scope.outputs.run', repr(''))
        cancelled = cancelled.replace('&&', ' and ').replace('||', ' or ')
        self.assertFalse(eval(cancelled, {'__builtins__': {}}, {}))

    def test_docker_publication_and_explicit_ref_are_not_path_filtered(self):
        source = (ROOT / '.github/workflows/docker-build-push.yml').read_text()
        self.assertIn("if: github.event_name == 'pull_request' && inputs.push == false && inputs.checkout-ref == ''", source)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' && inputs.push == false }}", source)

    def test_browser_evidence_covers_host_and_container_failure_paths(self):
        source = (ROOT / '.github/workflows/frontend-check.yml').read_text()
        block = source.split('      - name: 保存浏览器测试证据\n', 1)[1].split('      - name:', 1)[0]
        predicate = re.search(r'^        if: (.+)$', block, re.M).group(1)
        for run, browsers, image, expected in [('true', 'chromium', '', True),
                                               ('true', '', 'image@sha256:hash', True),
                                               ('false', 'chromium', '', False),
                                               ('true', '', '', False)]:
            expression = predicate.replace('always()', 'True')
            for name, value in [('run', run), ('playwright-browsers', browsers), ('playwright-image', image)]:
                expression = expression.replace('steps.plan.outputs.run' if name == 'run' else 'steps.policy.outputs.' + name, repr(value))
            expression = expression.replace('&&', ' and ').replace('||', ' or ')
            self.assertEqual(eval(expression, {'__builtins__': {}}, {}), expected)
        self.assertGreater(source.index('      - name: 保存浏览器测试证据'), source.index('      - name: 执行前端检查'))
        self.assertGreater(source.index('      - name: 保存浏览器测试证据'), source.index('      - name: 在预装浏览器环境执行完整检查'))
        self.assertIn('/.playwright/results', block)
        self.assertIn('include-hidden-files: true', block)

    def test_always_paths_are_independent_of_and_predicate(self):
        source = (ROOT / 'actions/ci-scope/action.yml').read_text()
        block = source.split('    - id: always\n', 1)[1].split('    - id: plan\n')[0]
        self.assertNotIn('predicate-quantifier:', block)


if __name__ == '__main__':
    unittest.main()
