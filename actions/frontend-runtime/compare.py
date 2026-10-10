"""Reject benchmark results that improve time by losing or destabilizing tests."""
import json
from pathlib import Path
import sys


def inventory(report):
    tests = {}

    def visit(suite):
        for spec in suite.get('specs', []):
            for test in spec['tests']:
                key = (spec['id'], test['projectName'])
                if key in tests:
                    raise ValueError(f'重复测试身份：{key}')
                tests[key] = (test['expectedStatus'], test['status'])
                if test['status'] not in ('expected', 'skipped'):
                    raise ValueError(f'首次执行失败或不稳定：{spec["title"]}')
        for child in suite.get('suites', []):
            visit(child)

    for suite in report['suites']:
        visit(suite)
    if not tests or not any(status == 'expected' for _, status in tests.values()):
        raise ValueError('基准没有实际执行成功的用例')
    return tests


def compare(root):
    rows = ['| 浏览器 | 完整用例数 | 1 worker | 2 workers |',
            '| --- | ---: | ---: | ---: |']
    for browser in ['chromium', 'firefox', 'webkit']:
        reports = []
        for workers in [1, 2]:
            files = list((Path(root) / f'frontend-{browser}-{workers}').rglob('results.json'))
            if len(files) != 1:
                raise ValueError(f'{browser}/{workers} 必须恰好提供一份完整报告')
            reports.append(json.loads(files[0].read_text()))
        baseline, parallel = [inventory(report) for report in reports]
        if baseline != parallel:
            raise ValueError(f'{browser} 的用例集合或跳过状态不一致')
        durations = [report['stats']['duration'] / 1000 for report in reports]
        rows.append(f'| {browser} | {len(baseline)} | {durations[0]:.1f}s | {durations[1]:.1f}s |')
    return '\n'.join(rows) + '\n'


if __name__ == '__main__':
    print(compare(sys.argv[1]))
