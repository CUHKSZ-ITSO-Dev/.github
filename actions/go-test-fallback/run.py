"""A GitHub-relayed handoff; the Actions job remains the result owner.

GitHub-hosted runners cannot reach the intranet DevPortal directly, so the
request travels as a commit status on the run's head SHA: this step writes a
pending marker, DevPortal's existing GitHub poll loop picks it up, executes the
tests on the intranet cluster and writes the terminal state back to the same
status context, which this step polls until it can exit with the real result.
"""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONTEXT = 'devportal/go-test-fallback'
REPOSITORIES = {'CUHKSZ-ITSO-Dev/Chat', 'CUHKSZ-ITSO-Dev/UniAuth', 'CUHKSZ-ITSO-Dev/open-platform'}
RUN_IDENTITY = re.compile(r'^run (\d+) attempt (\d+)')


def disk_exhausted():
    return ((Path(os.environ['RUNNER_TEMP']) / 'go-test-disk-exhausted').exists()
            or shutil.disk_usage(os.environ['GITHUB_WORKSPACE']).free < 256 * 1024 ** 2)


def failure_summary():
    temp = os.environ.get('RUNNER_TEMP')
    if not temp:
        return ''
    try:
        return (Path(temp) / 'go-test-failure-summary').read_text().strip()
    except OSError:
        return ''


def api(method, path, token, payload=None):
    request = Request('https://api.github.com' + path, method=method, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
    }, data=None if payload is None else json.dumps(payload).encode())
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def status_identity(status):
    match = RUN_IDENTITY.match(status.get('description') or '')
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def fallback_statuses(token, repository, commit):
    statuses = api('GET', f'/repos/{repository}/commits/{commit}/statuses?per_page=100', token)
    return [status for status in statuses if status.get('context') == CONTEXT]


def wait_for_result(token, repository, commit, run_id, attempt):
    identity = (run_id, attempt)
    deadline = time.monotonic() + 90 * 60
    outage_since = None
    previous = None
    while time.monotonic() < deadline:
        try:
            statuses = fallback_statuses(token, repository, commit)
            outage_since = None
        except (HTTPError, URLError, TimeoutError) as error:
            # 瞬时网络抖动与 API 限流不应终止等待；连续失败满 10 分钟才放弃。
            outage_since = outage_since or time.monotonic()
            if time.monotonic() - outage_since >= 10 * 60:
                print(f'::error::GitHub API 连续 10 分钟不可读（{error}），回退失败。')
                return 1
            time.sleep(20)
            continue
        superseded = False
        ours = None
        for status in statuses:
            # 状态按新到旧排列；旧 attempt 迟到的回写不覆盖本 attempt 的判断。
            owner = status_identity(status)
            if owner is None:
                continue
            if owner[0] != run_id:
                continue
            if owner[1] > attempt:
                # 更新的 attempt 已接管同一 commit 的回退，本次运行被取代。
                superseded = True
                break
            if owner[1] < attempt:
                continue
            ours = status
            break
        if superseded:
            print('::warning::回退请求已被更新的 run attempt 取代。')
            return 0
        if ours is not None:
            state = ours['state']
            if state == 'success':
                return 0
            if state in ('failure', 'error'):
                print(f"::error::DevPortal 回退测试未通过（{state}）。")
                return 1
            message = ours.get('description') or '等待 DevPortal 接收回退请求'
            if (state, message) != previous:
                print(f'DevPortal: {message}', flush=True)
                previous = (state, message)
        else:
            # 尚无本 run/attempt 的标记（首次请求或标记丢失）：创建 pending。
            try:
                api('POST', f'/repos/{repository}/statuses/{commit}', token, {
                    'state': 'pending',
                    'context': CONTEXT,
                    'description': f'run {run_id} attempt {attempt}：GitHub runner 磁盘不足，等待 DevPortal 执行测试',
                    'target_url': f'https://github.com/{repository}/actions/runs/{run_id}/attempts/{attempt}',
                })
            except HTTPError as error:
                if error.code == 403:
                    print('::error::写入回退请求被拒绝（HTTP 403）：workflow 需要 statuses: write 权限，'
                          '请检查仓库入口 workflow 的 permissions 配置。')
                    return 1
                if error.code not in (429, 502, 503, 504):
                    print(f'::error::写入回退请求失败（HTTP {error.code}）。')
                    return 1
            except (URLError, TimeoutError):
                pass
        time.sleep(20)
    print('::error::等待 DevPortal 回退结果超时。')
    return 1


def main():
    if not disk_exhausted():
        names = failure_summary()
        detail = f'：{names}' if names else '，失败详情见上方测试输出'
        print(f'::error::Go Test 未通过{detail}；失败与磁盘无关，不启动回退。')
        return 1
    repository = os.environ['FALLBACK_REPOSITORY']
    if repository not in REPOSITORIES:
        print('::error::GitHub runner 磁盘不足，但该仓库未启用 DevPortal 回退。')
        return 1
    (Path(os.environ['RUNNER_TEMP']) / 'go-test-handoff-reserve').unlink(missing_ok=True)
    run_id, attempt = int(os.environ['FALLBACK_RUN_ID']), int(os.environ['FALLBACK_RUN_ATTEMPT'])
    commit = os.environ['FALLBACK_COMMIT']
    token = os.environ['FALLBACK_TOKEN']
    print('GitHub runner 磁盘不足，经 GitHub status 请求 DevPortal 执行同一 commit。', flush=True)
    return wait_for_result(token, repository, commit, run_id, attempt)


if __name__ == '__main__':
    sys.exit(main())
