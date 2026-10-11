"""Capture ENOSPC without treating ordinary test failures as infrastructure errors."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

DISK_ERROR = re.compile(r'no space left on device|disk quota exceeded|ENOSPC', re.I)


def marker():
    return Path(os.environ['RUNNER_TEMP']) / 'go-test-disk-exhausted'


def record_disk_failure():
    # The preflight reserves room for the tiny handoff; no test output is stored.
    reserve = marker().with_name('go-test-handoff-reserve')
    reserve.unlink(missing_ok=True)
    marker().write_text('disk-exhausted\n')


def capture(command):
    process = subprocess.Popen(['bash', '-e', '-o', 'pipefail', '-c', command],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    disk_failure = False
    for line in iter(process.stdout.readline, b''):
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
        disk_failure |= bool(DISK_ERROR.search(line.decode('utf-8', errors='replace')))
    process.stdout.close()
    code = process.wait()
    if code and disk_failure:
        record_disk_failure()
    return code


def check_space():
    minimum = int(os.environ['MINIMUM_FREE_GIB']) * 1024 ** 3
    remaining = shutil.disk_usage(os.environ['GITHUB_WORKSPACE']).free
    if remaining < minimum:
        print(f'::warning::清理后编译空间不足：{remaining / 1024 ** 3:.1f} GiB，需要 {minimum / 1024 ** 3:.0f} GiB。')
        if os.environ.get('GITHUB_REPOSITORY') not in {'CUHKSZ-ITSO-Dev/Chat', 'CUHKSZ-ITSO-Dev/UniAuth', 'CUHKSZ-ITSO-Dev/open-platform'}:
            return 0
        record_disk_failure()
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
