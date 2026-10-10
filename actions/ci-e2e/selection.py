"""Select verified UI test groups, falling back to the existing full command."""
import json
import os
from pathlib import Path
import re
import shlex
from uuid import uuid4


def select(event, repository, profile, reliable, files, config, workspace):
    if event != 'pull_request' or not reliable:
        return [], '非 PR 或变更证据不足：全量 E2E'
    if repository.casefold() != 'cuhksz-itso-dev/ui' or profile not in ('chromium', 'firefox', 'webkit'):
        return [], '未配置经过验证的映射：全量 E2E'
    if not files:
        return [], '变更列表为空：全量 E2E'
    tests = set(config['smoke'])
    groups = set()
    for path in files:
        if path.startswith('.github/workflows/') or path.endswith('.md'):
            continue
        matched = False
        for group in config['groups']:
            if path in group['sources']:
                tests.update(group['tests'])
                groups.add(group['name'])
                matched = True
        if re.fullmatch(r'playwright/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.spec\.ts', path):
            tests.add(path)
            matched = True
        if not matched:
            return [], f'未映射路径 {path!r}：全量 E2E'
    # Old branches, renamed/deleted tests and incomplete mappings cannot turn
    # into an empty green run. A missing file means the full suite is required.
    if any(not (workspace / path).is_file() for path in tests):
        return [], '选中用例不存在：全量 E2E'
    return sorted(tests), '定向 E2E + 应用壳冒烟：' + ', '.join(sorted(groups) or ['测试文件变更'])


def main():
    config = json.loads(Path(__file__).with_name('ui.json').read_text())
    tests, reason = select(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REPOSITORY'],
                           os.environ['PROFILE'], os.environ['RELIABLE'] == 'true',
                           json.loads(os.environ['FILES_JSON']), config,
                           Path(os.environ['GITHUB_WORKSPACE']))
    command = os.environ['CHECK_COMMAND']
    if tests:
        # Playwright CLI file arguments are regexes, not literal paths.
        command = command.rstrip() + ' ' + ' '.join(
            shlex.quote(r'(^|/)' + re.escape(path) + '$') for path in tests) + '\n'
    delimiter = 'command_' + uuid4().hex
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'command<<{delimiter}\n{command.rstrip()}\n{delimiter}\n')
    print(reason)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('### 浏览器用例选择\n\n' + reason.replace('\n', ' ') + '\n\n')
        summary.write('```json\n' + json.dumps(tests, ensure_ascii=True, indent=2) + '\n```\n')


if __name__ == '__main__':
    main()
