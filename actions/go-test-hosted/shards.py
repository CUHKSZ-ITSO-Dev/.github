"""Run shard groups on one runner: per-group worktree and env-file isolation.

Each group gets GO_TEST_GROUP_INDEX so prepare-command can isolate databases
(e.g. suffixed names); without it the behavior matches ordinary sequential runs.
Live output is interleaved raw so capture.py still sees ENOSPC and --- FAIL lines;
failed groups are reprinted under a folded section for readability.

git worktree add/remove are not safe to run concurrently against one repository:
a sibling add can enumerate a half-written .git/worktrees/<id> and die with
"failed to read .../commondir". They are serialized under WORKTREE_LOCK (seconds),
retried after cleanup, and a setup failure is reported as such instead of as a
test failure. Only go test itself runs in parallel.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

ENV_ASSIGNMENT = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)(=|<<)(.*)$')
PRINT_LOCK = threading.Lock()
WORKTREE_LOCK = threading.Lock()
WORKTREE_ATTEMPTS = 3


def emit(text):
    with PRINT_LOCK:
        print(text, flush=True)


def parse_env_file(path):
    """Parse the GITHUB_ENV format: NAME=value and NAME<<DELIM blocks."""
    values = {}
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return values
    index = 0
    while index < len(lines):
        matched = ENV_ASSIGNMENT.match(lines[index])
        index += 1
        if not matched:
            continue
        name, operator, rest = matched.groups()
        if operator == '=':
            values[name] = rest
            continue
        body = []
        while index < len(lines) and lines[index] != rest:
            body.append(lines[index])
            index += 1
        index += 1  # skip the closing delimiter line
        values[name] = '\n'.join(body)
    return values


def stream(command, cwd, env, sink):
    process = subprocess.Popen(['bash', '-e', '-o', 'pipefail', '-c', command],
                               cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in iter(process.stdout.readline, b''):
        sink.write(line)
        sink.flush()
        with PRINT_LOCK:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
    process.stdout.close()
    return process.wait()


def git(workspace, *args):
    return subprocess.run(['git', *args], cwd=workspace, env=dict(os.environ),
                          capture_output=True)


def remove_worktree(workspace, checkout):
    with WORKTREE_LOCK:
        git(workspace, 'worktree', 'remove', '--force', str(checkout))
        shutil.rmtree(checkout, ignore_errors=True)
        git(workspace, 'worktree', 'prune')


def add_worktree(index, workspace, checkout, sink, attempts=WORKTREE_ATTEMPTS):
    """Create the shard checkout serially; clean up and retry transient failures."""
    code = 1
    for attempt in range(1, attempts + 1):
        with WORKTREE_LOCK:
            result = git(workspace, 'worktree', 'add', '--detach', str(checkout), 'HEAD')
        sink.write(result.stdout + result.stderr)
        sink.flush()
        code = result.returncode
        if not code:
            return 0
        if attempt < attempts:
            emit(f'[分片 {index}] 工作区创建失败（exit {code}），清理后重试 {attempt}/{attempts - 1}')
            remove_worktree(workspace, checkout)
            time.sleep(attempt)
    return code


def run_group(index, packages, workspace, workdir, prepare, flags, temp, test_command=None):
    """Returns (index, log path, exit code); worktree removed before returning."""
    checkout = Path(temp) / f'ws-{index}'
    envfile = Path(temp) / f'env-{index}'
    log = Path(temp) / f'group-{index}.log'
    env = dict(os.environ)
    env['GO_TEST_GROUP_INDEX'] = str(index)
    env['GITHUB_WORKSPACE'] = str(checkout)
    env['GITHUB_ENV'] = str(envfile)
    with log.open('wb') as sink:
        code = add_worktree(index, workspace, checkout, sink)
        if code:
            # capture.py 把 "FAIL <名称>" 收进失败摘要，回退步骤据此报基础设施失败而非测试失败
            status = f'FAIL\t分片{index}工作区准备失败（git-worktree-exit-{code}，未执行测试）'
        else:
            cwd = checkout / workdir
            if prepare:
                emit(f'[分片 {index}] 准备测试配置')
                code = stream(prepare, cwd, env, sink)
            if not code:
                env.update(parse_env_file(envfile))
                emit(f'[分片 {index}] 执行 go test（{len(packages.split())} 包）')
                code = stream(test_command or f'go test {flags} {packages}', cwd, env, sink)
            status = f"[分片 {index}] {'通过' if not code else '失败'}（exit {code}）"
        emit(status)
        sink.write(status.encode() + b'\n')
    remove_worktree(workspace, checkout)
    return index, log, code


def main():
    groups = json.loads(os.environ['PARALLEL_GROUPS'])
    workspace = Path(os.environ['GITHUB_WORKSPACE'])
    workdir = os.environ.get('POLICY_WORKING_DIRECTORY') or '.'
    prepare = os.environ.get('PREPARE_COMMAND') or ''
    flags = os.environ.get('TEST_FLAGS') or ''
    temp = Path(os.environ['RUNNER_TEMP']) / 'go-test-groups'
    temp.mkdir(parents=True, exist_ok=True)
    # 清掉同一 runner 上次中断留下的工作区登记，避免 add 因同名残留失败
    git(workspace, 'worktree', 'prune')
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        futures = [pool.submit(run_group, i + 1, packages, workspace, workdir,
                               prepare, flags, temp)
                   for i, packages in enumerate(
                       ' '.join(group) if isinstance(group, list) else group
                       for group in groups)]
        results = [future.result() for future in futures]
    failed = [(index, log) for index, log, code in results if code]
    for index, log in failed:
        print(f'::group::分片 {index} 完整日志')
        sys.stdout.buffer.write(Path(log).read_bytes())
        sys.stdout.buffer.flush()
        print('::endgroup::')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
