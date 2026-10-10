"""Run the unchanged frontend command with preinstalled browser dependencies."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def docker_command(image, workspace, directory, node, pnpm, uid, gid, command):
    # Fail before pulling or executing an unpinned or unrelated image.
    if not re.fullmatch(r'mcr\.microsoft\.com/playwright:v\d+\.\d+\.\d+-noble@sha256:[0-9a-f]{64}', image):
        raise ValueError('浏览器镜像必须为固定 digest 的 Playwright 官方 noble 镜像')
    workspace = Path(workspace).resolve()
    directory = (workspace / directory).resolve()
    if not directory.is_relative_to(workspace):
        raise ValueError('前端目录必须位于当前工作区')
    tool_dirs = list(dict.fromkeys(str(Path(tool).resolve().parent) for tool in [node, pnpm]))
    tool_roots = list(dict.fromkeys(str(Path(path).parent) for path in tool_dirs))
    args = ['docker', 'run', '--rm', '--init', '--network=host', '--ipc=host',
            '--user', f'{uid}:{gid}', '--workdir', str(directory)]
    for source in [str(workspace), *tool_roots]:
        # Mount whole tool directories: pnpm may use siblings of its launcher.
        args += ['--volume', f'{source}:{source}' + (':ro' if source != str(workspace) else '')]
    args += ['--env', 'CI=true', '--env', 'HOME=/tmp/frontend-home',
             '--env', 'PLAYWRIGHT_BROWSERS_PATH=/ms-playwright',
             '--env', 'PLAYWRIGHT_JSON_OUTPUT_NAME=test-results/results.json',
             '--env', 'PATH=' + ':'.join(tool_dirs) + ':/usr/local/bin:/usr/bin:/bin',
             image, 'bash', '-euo', 'pipefail', '-c',
             'mkdir -p "$HOME"\n' + command]
    return args


def main():
    args = docker_command(os.environ['FRONTEND_IMAGE'], os.environ['GITHUB_WORKSPACE'],
                          os.environ['FRONTEND_DIRECTORY'], shutil.which('node'),
                          shutil.which('pnpm'), os.getuid(), os.getgid(),
                          os.environ['FRONTEND_COMMAND'])
    expected = re.search(r':v(\d+\.\d+\.\d+)-noble@', os.environ['FRONTEND_IMAGE']).group(1)
    installed = subprocess.check_output(
        ['node', '-p', "require('@playwright/test/package.json').version"],
        cwd=args[args.index('--workdir') + 1], text=True).strip()
    if installed != expected:
        raise ValueError(f'Playwright 版本不匹配：依赖 {installed}，镜像 {expected}；请更新集中镜像')
    started = time.monotonic()
    subprocess.run(['docker', 'pull', os.environ['FRONTEND_IMAGE']], check=True)
    pull_seconds = time.monotonic() - started
    print(f'浏览器镜像准备：{pull_seconds:.1f}s', flush=True)
    started = time.monotonic()
    try:
        subprocess.run(args, check=True)
    finally:
        test_seconds = time.monotonic() - started
        print(f'浏览器完整检查：{test_seconds:.1f}s', flush=True)
        results_dir = Path(args[args.index('--workdir') + 1]) / 'test-results'
        results_dir.mkdir(parents=True, exist_ok=True)
        metrics = {'image': os.environ['FRONTEND_IMAGE'], 'pullSeconds': pull_seconds,
                   'checkSeconds': test_seconds}
        (results_dir / 'runtime.json').write_text(json.dumps(metrics, indent=2) + '\n')


if __name__ == '__main__':
    main()
