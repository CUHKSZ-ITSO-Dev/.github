"""Select verified frontend test groups, falling back to the existing full command."""
import json
import os
from pathlib import Path
import re
import shlex
from uuid import uuid4


def select(event, repository, profile, reliable, files, config, workspace):
    if event != 'pull_request' or not reliable:
        return [], '非 PR 或变更证据不足：全量 E2E'
    expected_repository = config.get('repository', 'cuhksz-itso-dev/ui').casefold()
    profiles = config.get('profiles', ('chromium', 'firefox', 'webkit'))
    if repository.casefold() != expected_repository or profile not in profiles:
        return [], '未配置经过验证的映射：全量 E2E'
    if not files:
        return [], '变更列表为空：全量 E2E'
    prefix = config.get('path-prefix', '')
    tests = set(config['smoke'])
    groups = set()
    for original_path in files:
        path = original_path.removeprefix(prefix) if prefix else original_path
        documentation = original_path.endswith('.md') and not (prefix and path.startswith(('src/', 'public/')))
        if original_path.startswith('.github/workflows/') or documentation or original_path == 'AGENTS.md':
            continue
        matched = False
        for group in config['groups']:
            if path in group['sources']:
                tests.update(group['tests'])
                groups.add(group['name'])
                matched = True
        if re.fullmatch(config.get('test-pattern', r'playwright/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.spec\.ts'), path):
            tests.add(path)
            matched = True
        if not matched:
            return [], f'未映射路径 {path!r}：全量 E2E'
    # Old branches, renamed/deleted tests and incomplete mappings cannot turn
    # into an empty green run. A missing file means the full suite is required.
    if any(not (workspace / prefix / path).is_file() for path in tests):
        return [], '选中用例不存在：全量 E2E'
    return sorted(tests), '定向 E2E + ' + config.get('smoke-name', '应用壳冒烟') + '：' + ', '.join(sorted(groups) or ['测试文件变更'])


def ci_only(files):
    return bool(files) and all(path.startswith('.github/') or path in (
        'scripts/check_frontend_ci_policy.py', 'scripts/test_frontend_ci_policy.py') for path in files)


def browser_required(event, repository, reliable, files):
    # Normative documents still run static gates, but do not need a browser install.
    def static_only(path):
        return (path.startswith('.github/') or
                path in ('scripts/check_frontend_ci_policy.py', 'scripts/test_frontend_ci_policy.py') or
                (path.endswith('.md') and not path.startswith(('uniauth-vite/src/', 'uniauth-vite/public/'))) or
                path == 'AGENTS.md')

    return not (repository.casefold() == 'cuhksz-itso-dev/uniauth' and
                event == 'pull_request' and reliable and files and all(map(static_only, files)))


def selected_command(repository, reliable, files, tests, command, workspace):
    if repository.casefold() == 'cuhksz-itso-dev/uniauth':
        package = workspace / 'uniauth-vite/package.json'
        # Older branches have no CI mode; preserve their full command.
        if reliable and package.is_file() and json.loads(package.read_text()).get('scripts', {}).get('check:ci') == 'node scripts/run-checks.mjs --ci':
            if ci_only(files):
                return "echo 'CI 入口已由前置配置契约和公共工作流语法检查验证。'"
            return ('UNIAUTH_CHECK_PATHS_JSON=' + shlex.quote(json.dumps(files)) +
                    ' UNIAUTH_UI_TESTS_JSON=' + shlex.quote(json.dumps(tests)) + ' pnpm run check:ci')
        return command
    if tests:
        return command.rstrip() + ' ' + ' '.join(
            shlex.quote(r'(^|/)' + re.escape(path) + '$') for path in tests) + '\n'
    return command


def main():
    repository = os.environ['GITHUB_REPOSITORY']
    config_name = 'uniauth.json' if repository.casefold() == 'cuhksz-itso-dev/uniauth' else 'ui.json'
    config = json.loads(Path(__file__).with_name(config_name).read_text())
    tests, reason = select(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REPOSITORY'],
                           os.environ['PROFILE'], os.environ['RELIABLE'] == 'true',
                           json.loads(os.environ['FILES_JSON']), config,
                           Path(os.environ['GITHUB_WORKSPACE']))
    files = json.loads(os.environ['FILES_JSON'])
    reliable = os.environ['RELIABLE'] == 'true' and os.environ['GITHUB_EVENT_NAME'] == 'pull_request'
    command = selected_command(repository, reliable, files, tests, os.environ['CHECK_COMMAND'],
                               Path(os.environ['GITHUB_WORKSPACE']))
    ci_without_dependencies = reliable and repository.casefold() == 'cuhksz-itso-dev/uniauth' and ci_only(files) and command.startswith("echo 'CI 入口")
    needs_browser = browser_required(os.environ['GITHUB_EVENT_NAME'], repository, reliable, files)
    legacy_uniauth = repository.casefold() == 'cuhksz-itso-dev/uniauth' and not command.endswith('pnpm run check:ci')
    delimiter = 'command_' + uuid4().hex
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('dependencies-required=' + str(not ci_without_dependencies).lower() + '\n')
        output.write('browser-required=' + str(not ci_without_dependencies and (needs_browser or legacy_uniauth)).lower() + '\n')
        output.write(f'command<<{delimiter}\n{command.rstrip()}\n{delimiter}\n')
    print(reason)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('### 浏览器用例选择\n\n' + reason.replace('\n', ' ') + '\n\n')
        summary.write('```json\n' + json.dumps(tests, ensure_ascii=True, indent=2) + '\n```\n')


if __name__ == '__main__':
    main()
