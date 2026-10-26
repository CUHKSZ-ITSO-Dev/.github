"""An idempotent, authenticated handoff; the Actions job remains the result owner."""
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = 'https://testopenai-dev03.cuhk.edu.cn/dev/api/v1/go-test/fallback'
REPOSITORIES = {'CUHKSZ-ITSO-Dev/Chat', 'CUHKSZ-ITSO-Dev/UniAuth', 'CUHKSZ-ITSO-Dev/open-platform'}


def disk_exhausted():
    return ((Path(os.environ['RUNNER_TEMP']) / 'go-test-disk-exhausted').exists()
            or shutil.disk_usage(os.environ['GITHUB_WORKSPACE']).free < 256 * 1024 ** 2)


def request_result(payload):
    request = Request(URL, data=json.dumps(payload).encode(), method='POST', headers={
        'Authorization': 'Bearer ' + os.environ['FALLBACK_TOKEN'],
        'Content-Type': 'application/json',
    })
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def failure_summary():
    temp = os.environ.get('RUNNER_TEMP')
    if not temp:
        return ''
    try:
        return (Path(temp) / 'go-test-failure-summary').read_text().strip()
    except OSError:
        return ''


def main():
    if not disk_exhausted():
        names = failure_summary()
        detail = f'：{names}' if names else '，失败详情见上方测试输出'
        print(f'::error::Go Test 未通过{detail}；失败与磁盘无关，不启动回退。')
        return 1
    if os.environ['FALLBACK_REPOSITORY'] not in REPOSITORIES:
        print('::error::GitHub runner 磁盘不足，但该仓库未启用 DevPortal 回退。')
        return 1
    (Path(os.environ['RUNNER_TEMP']) / 'go-test-handoff-reserve').unlink(missing_ok=True)
    payload = dict(repository=os.environ['FALLBACK_REPOSITORY'], commit=os.environ['FALLBACK_COMMIT'],
                   runID=int(os.environ['FALLBACK_RUN_ID']), attempt=int(os.environ['FALLBACK_RUN_ATTEMPT']))
    print('GitHub runner 磁盘不足，等待 DevPortal 执行同一 commit。', flush=True)
    # Request keys are stable across retries. No credentials or raw API errors are printed.
    deadline = time.monotonic() + 90 * 60
    outage_since = None
    previous = None
    while time.monotonic() < deadline:
        try:
            result = request_result(payload)
        except HTTPError as error:
            if error.code not in (429, 502, 503, 504):
                print(f'::error::DevPortal 拒绝回退请求（HTTP {error.code}）。')
                return 1
            result = None
        except (URLError, TimeoutError):
            result = None
        if result:
            outage_since = None
            status = (result['phase'], result['message'])
            if status != previous:
                print(f"DevPortal: {result['phase']} — {result['message']}", flush=True)
                previous = status
            if result['phase'] == 'Succeeded':
                return 0
            if result['phase'] in ('Failed', 'Stale', 'Cancelled', 'Bypassed'):
                return 1
        else:
            # 瞬时网络抖动和门户重启不应终止等待；连续不可达满 10 分钟才放弃。
            outage_since = outage_since or time.monotonic()
            if time.monotonic() - outage_since >= 10 * 60:
                print('::error::DevPortal 连续 10 分钟不可达，回退失败。')
                return 1
        time.sleep(15)
    print('::error::等待 DevPortal 测试结果超时。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
