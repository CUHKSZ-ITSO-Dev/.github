"""Capture ENOSPC without treating ordinary test failures as infrastructure errors."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

DISK_ERROR = re.compile(r'no space left on device|disk quota exceeded|ENOSPC', re.I)
TEST_FAILURE = re.compile(r'--- FAIL:\s*(\S+)')
PACKAGE_FAILURE = re.compile(r'^FAIL\s+(\S+)')


def marker():
    return Path(os.environ['RUNNER_TEMP']) / 'go-test-disk-exhausted'


def summary_marker():
    return Path(os.environ['RUNNER_TEMP']) / 'go-test-failure-summary'


def reason_marker():
    return Path(os.environ['RUNNER_TEMP']) / 'go-test-infra-reason'


def record_disk_failure(reason):
    # The preflight reserves room for the tiny handoff; no test output is stored.
    reserve = marker().with_name('go-test-handoff-reserve')
    reserve.unlink(missing_ok=True)
    marker().write_text('disk-exhausted\n')
    reason_marker().write_text(reason + '\n')


def record_failure_summary(names):
    if names:
        summary_marker().write_text('、'.join(names) + '\n')


def capture(command):
    process = subprocess.Popen(['bash', '-e', '-o', 'pipefail', '-c', command],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    disk_failure = False
    tests, packages = [], []
    for line in iter(process.stdout.readline, b''):
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
        text = line.decode('utf-8', errors='replace')
        disk_failure |= bool(DISK_ERROR.search(text))
        found = TEST_FAILURE.search(text)
        if found and found.group(1) not in tests:
            tests.append(found.group(1))
        found = PACKAGE_FAILURE.match(text)
        if found and found.group(1) not in packages:
            packages.append(found.group(1))
    process.stdout.close()
    code = process.wait()
    if code and disk_failure:
        record_disk_failure('测试执行中磁盘空间耗尽（ENOSPC）')
    elif code:
        record_failure_summary((tests + [name for name in packages if name not in tests])[:8])
    return code


def check_space():
    minimum = int(os.environ['MINIMUM_FREE_GIB']) * 1024 ** 3
    remaining = shutil.disk_usage(os.environ['GITHUB_WORKSPACE']).free
    if remaining < minimum:
        gib = remaining / 1024 ** 3
        print(f'::warning::清理后编译空间不足：{gib:.1f} GiB，需要 {minimum / 1024 ** 3:.0f} GiB。')
        if os.environ.get('GITHUB_REPOSITORY') not in {'CUHKSZ-ITSO-Dev/Chat', 'CUHKSZ-ITSO-Dev/UniAuth', 'CUHKSZ-ITSO-Dev/open-platform'}:
            return 0
        record_disk_failure(f'GitHub runner 可用空间不足：{gib:.1f} GiB，低于 {minimum / 1024 ** 3:.0f} GiB 门槛')
        return 125
    return 0


if __name__ == '__main__':
    reserve = marker().with_name('go-test-handoff-reserve')
    if not reserve.exists() and not marker().exists():
        try:
            reserve.write_bytes(b'0' * (1024 * 1024))
        except OSError:
            pass
    sys.exit(check_space() if '--check-space' in sys.argv else capture(os.environ['CAPTURE_COMMAND']))
