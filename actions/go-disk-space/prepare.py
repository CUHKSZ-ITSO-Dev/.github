"""Free unused SDKs only when cached Go tests need more disk headroom."""
import os
from pathlib import Path
import shutil
import subprocess

SDK_PATHS = (
    '/usr/share/dotnet', '/opt/ghc', '/usr/local/lib/android', '/usr/share/swift',
    '/usr/lib/jvm', '/opt/hostedtoolcache/CodeQL', '/usr/local/.ghcup',
    '/usr/share/miniconda', '/usr/local/share/boost', '/usr/local/aws-cli',
    '/usr/local/share/powershell', '/usr/local/cargo', '/usr/local/rustup',
    '/usr/share/rust',
)
# Go 工具链由 setup-go 安装在 /opt/hostedtoolcache/go，必须在深度清理中保留。
KEEP_HOSTED_TOOLS = {'go'}
# go-test 自身要拉的数据库镜像不参与 Docker 清理；后台拉取与清理可能并发执行。
DB_IMAGE_MARKERS = ('postgres', 'mssql')


def hosted_toolcache_paths(exists=None, root=None):
    exists = exists or (lambda path: Path(path).exists())
    root = Path(root or '/opt/hostedtoolcache')
    if not root.is_dir():
        return []
    paths = [str(path) for path in sorted(root.iterdir())
             if path.is_dir() and path.name not in KEEP_HOSTED_TOOLS]
    return [path for path in paths if exists(path)]


def prune_foreign_docker_images(run=None):
    """删除预装的无关 Docker 镜像；数据库镜像按仓库名排除，避免误删在途拉取。"""
    run = run or subprocess.run
    if shutil.which('docker') is None:
        return []
    listing = run(['docker', 'images', '--format', '{{.ID}} {{.Repository}}:{{.Tag}}'],
                  capture_output=True, text=True)
    if listing.returncode:
        return []
    removed = []
    seen_ids = set()
    for line in listing.stdout.splitlines():
        image_id, _, reference = line.partition(' ')
        if not image_id or not reference or image_id in seen_ids:
            continue
        seen_ids.add(image_id)
        if any(marker in reference for marker in DB_IMAGE_MARKERS):
            continue
        removal = run(['docker', 'rmi', '-f', image_id], capture_output=True, text=True)
        if removal.returncode == 0:
            removed.append(reference)
    return removed


def prepare(workspace, minimum_gib, free=None, remove=None, exists=None, prune_images=None,
            hosted_root=None):
    free = free or (lambda: shutil.disk_usage(workspace).free)
    remove = remove or (lambda path: subprocess.run(['sudo', 'rm', '-rf', path], check=True))
    exists = exists or (lambda path: Path(path).exists())
    prune_images = prune_images or prune_foreign_docker_images
    minimum = minimum_gib * 1024 ** 3
    removed = []
    if free() < minimum:
        # 触发即深度清理。只清到门槛会让缓存恢复、工具链下载和镜像拉取
        # 在编译空间检查前再次击穿余量（UniAuth PR #542 的实际失败路径）。
        for path in [*SDK_PATHS, *hosted_toolcache_paths(exists, hosted_root)]:
            if not exists(path):
                continue
            print(f'磁盘余量不足 {minimum_gib} GiB，清理 {path}。', flush=True)
            remove(path)
            removed.append(path)
        removed.extend(prune_images() or [])
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
