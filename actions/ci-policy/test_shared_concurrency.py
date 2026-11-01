"""共享检查工作流并发组的统一契约。

每个带参共享工作流的并发组必须以「全部入参的指纹」结尾（actions/concurrency-key）：

- 不同入参的调用（同一 PR 多次调用，如不同检查命令/浏览器/数据库）组不同，互不取消；
- 同一入参组合的新提交指纹不变，仍按原组取代旧运行；
- 不同 PR/分支组不同，互不影响。

并发组若改回手工枚举入参或漏接指纹，这里会直接失败。
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / '.github/workflows'
KEY_ACTION = 'uses: CUHKSZ-ITSO-Dev/.github/actions/concurrency-key@main'

# 带参共享检查工作流 → 验证互不取消所用的差异化入参（覆盖各工作流的主要调用维度）。
FINGERPRINTED = {
    'python-uv-check.yml': {
        'base': {'working-directory': '.', 'check-command': 'pytest'},
        'vary': ['check-command', 'python-version', 'working-directory', 'env-vars'],
    },
    'python-uv-redis-rabbitmq-check.yml': {
        'base': {'working-directory': '.', 'check-command': 'pytest'},
        'vary': ['check-command', 'working-directory'],
    },
    'golangci-lint.yml': {
        'base': {'working-directory': '.'},
        'vary': ['go-version', 'working-directory'],
    },
    'migration-check.yml': {
        'base': {'working-directory': '.'},
        'vary': ['database-kind', 'working-directory'],
    },
    'go-test.yml': {
        'base': {'working-directory': '.'},
        'vary': ['database-kind', 'test-shards', 'working-directory'],
    },
    'docker-build-push.yml': {
        'base': {'image-name': 'app', 'context': '.', 'dockerfile': 'Dockerfile', 'push': True},
        'vary': ['image-name', 'context', 'build-args', 'push'],
    },
    'frontend-check.yml': {
        'base': {'working-directory': '.', 'check-profile': ''},
        'vary': ['check-profile', 'playwright-browsers', 'check-command', 'node-version', 'working-directory'],
    },
}

CHANGED = {
    'check-command': 'other-check',
    'python-version': '3.14',
    'env-vars': 'A=1',
    'go-version': '1.28.0',
    'database-kind': 'mysql',
    'test-shards': 3,
    'image-name': 'other',
    'context': 'services/app',
    'build-args': 'A=1',
    'push': False,
    'check-profile': 'lint',
    'playwright-browsers': 'firefox',
    'node-version': '27.0.0',
    'working-directory': 'web',
}


def fingerprint(inputs):
    """并发组指纹的平行模拟：对全部入参做规范化序列化后取 sha256 前 12 位。

    与 actions/concurrency-key 的算法同构但不等值：action 对 GitHub
    `toJSON(inputs)` 的原始文本哈希（键序为工作流入参声明序），本函数用
    Python 序列化。端到端行为（确定性、敏感性、格式）由
    `test_action_script_behaviour` 直接执行 action 脚本验证，不依赖本模拟。
    """
    payload = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _has_workflow_call_inputs(source):
    """workflow_call 是否声明 inputs（对 on: 块做缩进扫描，容忍注释与空行）。"""
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if not re.match(r'^on:\s*$', line):
            continue
        for j in range(i + 1, len(lines)):
            follow = lines[j]
            if follow.strip() == '' or follow.lstrip().startswith('#'):
                continue
            if not re.match(r'^  workflow_call:\s*$', follow):
                break
            for tail in lines[j + 1:]:
                if tail.strip() == '' or tail.lstrip().startswith('#'):
                    continue
                if len(tail) - len(tail.lstrip()) <= 2:
                    return False
                if re.match(r'\s*inputs:', tail):
                    return True
        return False
    return False


class SharedWorkflow:
    def __init__(self, path):
        self.name = path.name
        self.text = path.read_text()
        self.workflow_name = re.search(r'^name: (.+)$', self.text, re.M).group(1)
        self.groups = re.findall(r'^      group: (.+)$', self.text, re.M)

    def resolve(self, inputs, pr=293, sha='old'):
        context = {
            'github.repository': 'CUHKSZ-ITSO-Dev/docparse',
            'github.workflow': self.workflow_name,
            'github.event.pull_request.number': pr,
            'github.ref': f'refs/pull/{pr}/merge',
            'github.sha': sha,
            'matrix.index': 1,
            'needs.identity.outputs.key': fingerprint(inputs),
            'needs.scope.outputs.key': fingerprint(inputs),
            'needs.plan.outputs.key': fingerprint(inputs),
        }
        context.update({f'inputs.{name}': value for name, value in inputs.items()})

        def resolve_expression(match):
            for operand in match.group(1).split('||'):
                operand = operand.strip()
                if operand.startswith("'"):
                    return operand[1:-1]
                if operand not in context:
                    raise AssertionError(f'并发组引用了未建模的上下文：{operand}')
                value = context[operand]
                if value != '' and value is not None:
                    return str(value)
            return ''

        return [re.sub(r'\$\{\{\s*(.*?)\s*\}\}', resolve_expression, group).lower()
                for group in self.groups]


class SharedConcurrencyTest(unittest.TestCase):
    def workflow(self, name):
        return SharedWorkflow(WORKFLOWS / name)

    def test_distinct_invocations_do_not_cancel_each_other(self):
        for name, spec in FINGERPRINTED.items():
            wf = self.workflow(name)
            base = wf.resolve(spec['base'])
            self.assertTrue(base, f'{name} 未找到并发组')
            for vary in spec['vary']:
                groups = wf.resolve(dict(spec['base'], **{vary: CHANGED[vary]}))
                for expected, group in zip(base, groups):
                    self.assertNotEqual(expected, group,
                                        f'{name} 入参 {vary} 变化后并发组不变，会互相取消')

    def test_new_commit_supersedes_same_invocation(self):
        for name, spec in FINGERPRINTED.items():
            wf = self.workflow(name)
            self.assertEqual(wf.resolve(spec['base'], sha='old'),
                             wf.resolve(spec['base'], sha='new'),
                             f'{name} 同一调用在新提交后应取代旧运行')

    def test_different_prs_do_not_cancel_each_other(self):
        for name, spec in FINGERPRINTED.items():
            wf = self.workflow(name)
            self.assertNotEqual(wf.resolve(spec['base']), wf.resolve(spec['base'], pr=294), name)

    def test_fingerprint_wiring_is_uniform(self):
        for name in FINGERPRINTED:
            source = (WORKFLOWS / name).read_text()
            self.assertIn(KEY_ACTION, source, f'{name} 未接调用指纹 action')
            self.assertIn('payload: ${{ toJSON(inputs) }}', source, f'{name} 指纹未覆盖全部入参')
            for group in re.findall(r'^      group: (.+)$', source, re.M):
                self.assertIn('outputs.key', group, f'{name} 并发组缺少指纹：{group}')

    def test_action_script_behaviour(self):
        """端到端执行 action 的实际脚本：确定性、敏感性、输出格式。"""
        if shutil.which('sha256sum') is None:
            self.skipTest('本机没有 sha256sum（CI 的 ubuntu runner 必有）')
        action = (ROOT / 'actions/concurrency-key/action.yml').read_text()
        block = action.split('run: |', 1)[1].splitlines()
        script = '\n'.join(line[8:] for line in block
                           if line.startswith(' ' * 8) or not line.strip())
        with tempfile.TemporaryDirectory() as tmp:
            def run(payload):
                output = Path(tmp) / 'output'
                output.write_text('')
                subprocess.run(['bash', '-c', script], check=True,
                               env={**os.environ, 'PAYLOAD': payload,
                                    'GITHUB_OUTPUT': str(output)},
                               cwd=tmp, capture_output=True, text=True)
                match = re.search(r'^key=(.+)$', output.read_text(), re.M)
                self.assertIsNotNone(match, 'action 未产出 key')
                return match.group(1)

            self.assertRegex(run('{"check-command":"pytest"}'), r'^[0-9a-f]{12}$')
            self.assertEqual(run('{"check-command":"pytest"}'),
                             run('{"check-command":"pytest"}'), '同入参指纹应稳定')
            self.assertNotEqual(run('{"check-command":"pytest"}'),
                                run('{"check-command":"other"}'), '不同入参指纹应不同')

    def test_every_shared_group_is_accounted_for(self):
        for path in sorted(WORKFLOWS.glob('*.yml')):
            wf = SharedWorkflow(path)
            if not wf.groups or path.name in FINGERPRINTED:
                continue
            # 不带指纹的共享组只允许出现在无 workflow_call 入参的工作流中；
            # 给这类工作流加入参时必须先接入指纹机制。
            self.assertFalse(_has_workflow_call_inputs(path.read_text()),
                             f'{path.name} 声明了入参但并发组未接指纹')
            for group in wf.groups:
                self.assertNotIn('inputs.', group,
                                 f'{path.name} 并发组手工引用入参，应改用统一指纹：{group}')


if __name__ == '__main__':
    unittest.main()
