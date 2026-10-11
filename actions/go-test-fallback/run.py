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


def main():
    if not disk_exhausted() or os.environ['FALLBACK_REPOSITORY'] not in REPOSITORIES:
        print('::error::原 Go Test 失败；未确认磁盘不足，不启动回退。')
        return 1
    (Path(os.environ['RUNNER_TEMP']) / 'go-test-handoff-reserve').unlink(missing_ok=True)
    payload = dict(repository=os.environ['FALLBACK_REPOSITORY'], commit=os.environ['FALLBACK_COMMIT'],
                   runID=int(os.environ['FALLBACK_RUN_ID']), attempt=int(os.environ['FALLBACK_RUN_ATTEMPT']))
    print('GitHub runner 磁盘不足，等待 DevPortal 执行同一 commit。', flush=True)
    # Request keys are stable across retries. No credentials or raw API errors are printed.
    deadline = time.monotonic() + 90 * 60
    previous = None
    failures = 0
    while time.monotonic() < deadline:
        try:
            result = request_result(payload)
            failures = 0
        except HTTPError as error:
            if error.code not in (429, 502, 503, 504):
                print(f'::error::DevPortal 拒绝回退请求（HTTP {error.code}）。')
                return 1
            failures += 1
            result = None
        except (URLError, TimeoutError):
            failures += 1
            result = None
        if failures >= 10:
            print('::error::DevPortal 持续不可用，回退失败。')
            return 1
        if result:
            status = (result['phase'], result['message'])
            if status != previous:
                print(f"DevPortal: {result['phase']} — {result['message']}", flush=True)
                previous = status
            if result['phase'] == 'Succeeded':
                return 0
            if result['phase'] in ('Failed', 'Stale', 'Cancelled', 'Bypassed'):
                return 1
        time.sleep(15)
    print('::error::等待 DevPortal 测试结果超时。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
