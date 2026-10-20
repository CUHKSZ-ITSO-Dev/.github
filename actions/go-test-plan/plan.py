"""Select affected test packages by reverse import closure; uncertainty runs all."""
import json
import os
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import subprocess

LIST = ('{{.ImportPath}}|{{.Dir}}|{{join .Imports ","}}|{{join .TestImports ","}}|'
        '{{join .XTestImports ","}}|{{join .EmbedPatterns ","}}|'
        '{{join .TestEmbedPatterns ","}}|{{join .XTestEmbedPatterns ","}}|'
        '{{join .TestGoFiles ","}}|{{join .XTestGoFiles ","}}')
MODULE_FILES = {'go.mod', 'go.sum', 'go.work', 'go.work.sum'}


def truthy(value):
    return str(value).strip().lower() in ('true', '1', 'yes')


def wants_listing(policy):
    try:
        shards = int(str(policy.get('test-shards') or '1'))
    except ValueError:
        shards = 1
    return truthy(policy.get('test-selection')) or shards > 1


def parse_rows(text):
    rows = []
    for line in text.splitlines():
        fields = (line.split('|') + [''] * 10)[:10]
        if not fields[0]:
            continue
        rows.append({
            'path': fields[0],
            'dir': fields[1],
            'imports': {name for field in fields[2:5] for name in field.split(',') if name},
            'embeds': [name for field in fields[5:8] for name in field.split(',') if name],
            'tests': sum(bool(name) for field in fields[8:10] for name in field.split(',')),
        })
    return rows


def package_rows(directory):
    result = subprocess.run(['go', 'list', '-e', '-f', LIST, './...'],
                            cwd=directory, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr[-2000:])
        return None
    return parse_rows(result.stdout) or None


def relativize(rows, workspace):
    for row in rows:
        row['dir'] = PurePosixPath(os.path.relpath(row['dir'], workspace)).as_posix()
    return rows


def embed_owner(file, rows):
    for row in rows:
        prefix = '' if row['dir'] == '.' else row['dir'] + '/'
        if prefix and not file.startswith(prefix):
            continue
        relative = file[len(prefix):]
        for pattern in row['embeds']:
            pattern = pattern.removeprefix('all:')
            if fnmatchcase(relative, pattern) or relative.startswith(pattern.rstrip('/') + '/'):
                return row['path']
    return None


def select_targets(files, rows):
    """Affected import paths, or (None, reason) when coverage cannot be proven."""
    by_dir = {row['dir']: row['path'] for row in rows}
    imported_by = {}
    for row in rows:
        for dep in row['imports']:
            imported_by.setdefault(dep, set()).add(row['path'])
    seeds, test_only = set(), set()
    for file in files:
        parts = PurePosixPath(file).parts
        if not parts or parts[-1] in MODULE_FILES or 'vendor' in parts:
            return None, f'依赖或工作区变更 {file}：全量'
        owners = set()
        if 'testdata' in parts:
            directory = PurePosixPath(*parts[:parts.index('testdata')]).as_posix()
            if directory in by_dir:
                owners.add(by_dir[directory])
        elif file.endswith('.go'):
            if PurePosixPath(file).parent.as_posix() in by_dir:
                owners.add(by_dir[PurePosixPath(file).parent.as_posix()])
        embedded = embed_owner(file, rows)
        if embedded:
            owners.add(embedded)
        if not owners:
            return None, f'未映射变更 {file}：全量'
        if file.endswith('_test.go') and not embedded:
            test_only |= owners
        else:
            seeds |= owners
    affected = seeds | test_only
    queue = list(seeds)
    while queue:
        node = queue.pop()
        for parent in imported_by.get(node, ()):
            if parent not in affected:
                affected.add(parent)
                queue.append(parent)
    if not affected:
        return None, '受影响包为空：全量'
    return affected, f'定向 {len(affected)}/{len(rows)} 个包'


def shard_groups(rows, targets, count):
    weights = {row['path']: 1 + row['tests'] for row in rows if row['path'] in targets}
    count = max(1, min(count, len(weights)))
    groups, loads = [[] for _ in range(count)], [0] * count
    for path in sorted(weights, key=lambda name: (-weights[name], name)):
        index = loads.index(min(loads))
        groups[index].append(path)
        loads[index] += weights[path]
    return [group for group in groups if group]


def plan(policy, event_name, reliable, files, rows):
    """Return (matrix, mode, reason); rows=None means the module was not listed."""
    try:
        shards = int(str(policy.get('test-shards') or '1'))
    except ValueError:
        shards = 1
    if rows is None:
        return ({'include': [{'index': 1, 'packages': './...'}]},
                'bypassed', '包列表不可用：全量')
    targets = {row['path'] for row in rows}
    mode, reason = 'all', f'全部分片 {len(rows)} 个包'
    if truthy(policy.get('test-selection')):
        if event_name != 'pull_request':
            reason = '非 PR 事件：全量'
        elif reliable != 'true':
            reason = '变更证据不足：全量'
        elif not isinstance(files, list) or any(not isinstance(f, str) for f in files) or not files:
            reason = '变更列表无效或为空：全量'
        else:
            selected, reason = select_targets(files, rows)
            if selected is not None:
                targets, mode = selected, 'affected'
    if mode == 'all' and shards <= 1:
        return {'include': [{'index': 1, 'packages': './...'}]}, mode, reason
    groups = shard_groups(rows, targets, shards)
    include = [{'index': index + 1, 'packages': ' '.join(group)}
               for index, group in enumerate(groups)]
    return {'include': include}, mode, reason


def main():
    policy = json.loads(os.environ['POLICY_JSON'])
    rows = None
    if wants_listing(policy):
        workspace = os.environ['GITHUB_WORKSPACE']
        directory = Path(workspace) / (policy.get('working-directory') or '.')
        listed = package_rows(directory)
        if listed:
            rows = relativize(listed, workspace)
    try:
        files = json.loads(os.environ.get('FILES_JSON') or '[]')
    except ValueError:
        files = None
    matrix, mode, reason = plan(policy, os.environ['GITHUB_EVENT_NAME'],
                                os.environ.get('RELIABLE', ''), files, rows)
    if not wants_listing(policy):
        reason = '未启用定向或分片：全量'
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('matrix=' + json.dumps(matrix, ensure_ascii=True) + '\n')
        output.write('selection=' + mode + '\n')
    print(reason)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        legs = ', '.join(f"分片 {entry['index']}（{len(entry['packages'].split())} 包）"
                         for entry in matrix['include'])
        summary.write(f'### Go Test 执行计划\n\n{reason}；{legs}。\n\n')


if __name__ == '__main__':
    main()
