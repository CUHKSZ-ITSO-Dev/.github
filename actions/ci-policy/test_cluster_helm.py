"""执行集中命令，验证真实 Chart 发现、矩阵覆盖与失败传播。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


POLICY = json.loads(Path(__file__).with_name('policy.json').read_text())
CONFIG = POLICY['repositories']['CUHKSZ-ITSO-Dev/Cluster']['helm-check']
CHARTS = ('gpt-docs', 'gpt-retention', 'gpt-shared-ai',
          'gpt-platform', 'gpt-delivery-pipeline')


class ClusterHelmTest(unittest.TestCase):
    def execute(self, charts=CHARTS, failure=''):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            for chart in charts:
                (workspace / chart).mkdir()
                (workspace / chart / 'Chart.yaml').write_text('apiVersion: v2\n')
            # 没有 Chart.yaml 的普通目录不能被当作 Chart。
            (workspace / 'docs').mkdir()
            tools = workspace / 'bin'
            tools.mkdir()
            stub = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == 'helm':
    if not pathlib.Path(sys.argv[2], 'Chart.yaml').is_file():
        sys.exit(91)
    if sys.argv[2] == os.environ.get('FAIL_CHART'):
        sys.exit(92)
'''
            for name in ('helm', 'python'):
                path = tools / name
                path.write_text(stub)
                path.chmod(0o755)
            log = workspace / 'commands.jsonl'
            result = subprocess.run(
                ['bash', '-euo', 'pipefail', '-c', CONFIG['check-command']],
                cwd=workspace, env=dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                                        COMMAND_LOG=str(log), FAIL_CHART=failure),
                capture_output=True, text=True)
            return result, [json.loads(line) for line in log.read_text().splitlines()]

    def test_existing_charts_and_original_matrices_run_without_sandbox(self):
        result, commands = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        helm = [command for command in commands if command[0] == 'helm']
        expected = [['helm', 'lint', chart] for chart in CHARTS[:3]]
        expected += [['helm', 'lint', 'gpt-platform', '-f',
                      f'gpt-platform-env/{environment}/values.yaml']
                     for environment in ('dev', 'uat', 'prod')]
        expected += [['helm', 'lint', 'gpt-delivery-pipeline', '-f',
                      f'gpt-delivery-pipeline/scopes/{scope}.yaml']
                     for scope in ('shared', 'secret-reloader', 'dev', 'uat', 'prod')]
        self.assertCountEqual(helm, expected)
        self.assertIn(['python', '-m', 'compileall', '-q', 'scripts'], commands)

    def test_each_existing_chart_failure_stops_the_complete_check(self):
        for chart in CHARTS:
            with self.subTest(chart=chart):
                result, commands = self.execute(failure=chart)
                self.assertEqual(result.returncode, 92)
                self.assertFalse(any(command[0] == 'python' for command in commands))

    def test_new_chart_is_discovered_without_a_policy_update(self):
        result, commands = self.execute(CHARTS + ('future-chart',))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(['helm', 'lint', 'future-chart'], commands)
        result, _ = self.execute(CHARTS + ('future-chart',), failure='future-chart')
        self.assertEqual(result.returncode, 92)
        # 任意顶层 Chart 的所有输入均在范围内，不限特定名称或扩展名。
        self.assertIn('*/**', CONFIG['changed-paths'].splitlines())


if __name__ == '__main__':
    unittest.main()
