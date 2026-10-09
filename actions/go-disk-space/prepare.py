"""Free unused SDKs only when cached Go tests need more disk headroom."""
import os
from pathlib import Path
import shutil
import subprocess

SDK_PATHS = ('/usr/share/dotnet', '/opt/ghc', '/usr/local/lib/android')


def prepare(workspace, minimum_gib, free=None, remove=None, exists=None):
    free = free or (lambda: shutil.disk_usage(workspace).free)
    remove = remove or (lambda path: subprocess.run(['sudo', 'rm', '-rf', path], check=True))
    exists = exists or (lambda path: Path(path).exists())
    minimum = minimum_gib * 1024 ** 3
    removed = []
    for path in SDK_PATHS:
        if free() >= minimum:
            break
        if exists(path):
            print(f'磁盘余量不足 {minimum_gib} GiB，清理 {path}。', flush=True)
            remove(path)
            removed.append(path)
    remaining = free() / 1024 ** 3
    print(f'当前磁盘余量 {remaining:.1f} GiB；目标 {minimum_gib} GiB。')
    if remaining < minimum_gib:
        print('::warning::未达到目标磁盘余量，请留意后续编译空间。')
    return removed


if __name__ == '__main__':
    minimum_gib = int(os.environ['MINIMUM_FREE_GIB'])
    if minimum_gib <= 0:
        raise ValueError('目标磁盘余量必须为正整数 GiB')
    prepare(os.environ['GITHUB_WORKSPACE'], minimum_gib)
