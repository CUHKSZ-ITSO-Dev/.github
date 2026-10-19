"""从共享 action 的可信配置读取目录，不执行候选分支的校验脚本。"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


FILENAME = re.compile(r"([0-9]{6})_([a-z0-9]+(?:_[a-z0-9]+)*)\.(up|down)\.sql")


def configuration(repository, entry):
    policy = json.loads((Path(__file__).parents[1] / 'ci-policy/policy.json').read_text())
    repositories = {key.casefold(): value for key, value in policy['repositories'].items()}
    config = repositories.get(repository.casefold(), {}).get('migration-files', {})
    return config if config.get('entry') == entry else None


def validate(directory):
    if not directory.is_dir():
        raise ValueError(f'迁移目录不存在：{directory}')
    files = sorted(path.name for path in directory.iterdir() if path.name.endswith('.sql'))
    up = []
    for name in files:
        match = FILENAME.fullmatch(name)
        if not match or not (directory / name).is_file() or (directory / name).is_symlink():
            raise ValueError(f'迁移文件命名或类型不符合规范：{name}')
        if match[3] == 'up':
            up.append((name, match[1]))
        opposite = name.replace('.up.sql', '.down.sql') if match[3] == 'up' else name.replace('.down.sql', '.up.sql')
        if opposite not in files:
            raise ValueError(f'迁移文件缺少配对：{name} → {opposite}')
        # 与 UniAuth 原有静态门禁一致：并发索引必须独占一条简单 SQL。
        # 这里不是 SQL 解析器，含字符串或美元引用的复杂迁移应使用数据库回归验证。
        sql = re.sub(r'--[^\n]*', '', (directory / name).read_text())
        if re.search(r'\b(?:CREATE\s+(?:UNIQUE\s+)?|DROP\s+)INDEX\s+CONCURRENTLY\b', sql, re.I):
            if len([statement for statement in sql.split(';') if statement.strip()]) != 1:
                raise ValueError(f'CONCURRENTLY 迁移必须只包含一条 SQL 语句：{name}')
    if not up:
        raise ValueError('迁移目录没有 up SQL 文件')
    for expected, (name, version) in enumerate(up, 1):
        if version != f'{expected:06d}':
            raise ValueError(f'迁移编号不连续或重复：{name}，期望 {expected:06d}')
    return len(up)


def git(workspace, *args):
    return subprocess.check_output(['git', '-C', str(workspace), *args], text=True)


def protect_history(workspace, directory, base):
    if not re.fullmatch(r'[0-9a-f]{40}', base):
        raise ValueError('无法确定历史迁移基线提交')
    # 入口完整检出历史；基线缺失时拒绝，避免历史保护静默失效。
    present = subprocess.run(['git', '-C', str(workspace), 'cat-file', '-e', base + '^{commit}'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if present.returncode:
        raise ValueError('历史迁移基线不可读；需要完整检出当前 PR 的目标分支历史')
    base_files = git(workspace, 'ls-tree', '-r', '--name-only', base, '--', directory).splitlines()
    for path in base_files:
        if path.endswith(('.up.sql', '.down.sql')):
            # 比较 blob 标识：不依赖 rename 检测，也不会把改名当作合法新增。
            before = git(workspace, 'rev-parse', base + ':' + path).strip()
            current = subprocess.run(['git', '-C', str(workspace), 'rev-parse', 'HEAD:' + path],
                                     capture_output=True, text=True)
            if current.returncode or current.stdout.strip() != before:
                raise ValueError(f'历史迁移不能删除、改名或改写：{path}')


def main():
    config = configuration(os.environ['GITHUB_REPOSITORY'], os.environ['CHECK_ENTRY'])
    if '--configure' in sys.argv:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'enabled={str(bool(config)).lower()}\n')
        return
    if not config:
        return
    workspace = Path(os.environ['GITHUB_WORKSPACE'])
    directory = config['directory']
    count = validate(workspace / directory)
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if 'pull_request' in event:
        protect_history(workspace, directory, event['pull_request']['base']['sha'])
    elif os.environ['GITHUB_EVENT_NAME'] == 'push' and event.get('before', '').strip('0'):
        protect_history(workspace, directory, event['before'])
    print(f'迁移文件检查通过：{directory}，共 {count} 个版本')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'::error::{error}')
        sys.exit(1)
