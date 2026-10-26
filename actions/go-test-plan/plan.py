"""Select affected test packages by reverse import closure; uncertainty runs all."""
import json
import os
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import subprocess

LIST = ('{{.ImportPath}}|{{.Dir}}|{{join .Imports ","}}|{{join .TestImports ","}}|'
        '{{join .XTestImports ","}}|{{join .EmbedPatterns ","}}|'
        '{{join .TestEmbedPatterns ","}}|{{join .XTestEmbedPatterns ","}}|'
        '{{join .TestGoFiles ","}}|{{join .XTestGoFiles ","}}|'
        '{{join .GoFiles ","}}|{{join .CgoFiles ","}}')
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
        fields = (line.split('|') + [''] * 12)[:12]
        if not fields[0]:
            continue
        rows.append({
            'path': fields[0],
            'dir': fields[1],
            'imports': {name for field in fields[2:5] for name in field.split(',') if name},
            'embeds': [name for field in fields[5:8] for name in field.split(',') if name],
            'tests': sum(bool(name) for field in fields[8:10] for name in field.split(',')),
            'files': [name for field in fields[8:12] for name in field.split(',') if name],
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


def source_index(rows, workspace):
    texts = {}
    for row in rows:
        chunks = []
        for name in row.get('files', []):
            try:
                chunks.append((Path(workspace) / row['dir'] / name).read_text(errors='replace'))
            except OSError:
                pass
        texts[row['path']] = '\n'.join(chunks)
    return texts


def literal_owners(file, texts, module_root=''):
    """Sources quoting the changed path own it as a runtime dependency."""
    forms = [file]
    prefix = '' if module_root in ('', '.') else module_root.rstrip('/') + '/'
    if prefix and file.startswith(prefix):
        forms.append(file[len(prefix):])
    needles = tuple(needle for form in forms for needle in
                    ('"' + form + '"', "'" + form + "'", '`' + form + '`',
                     '/' + form + '"', '/' + form + "'", '/' + form + '`'))
    return {path for path, text in texts.items()
            if any(needle in text for needle in needles)}


def nested_module(file, module_root, workspace):
    """Files under a nested module never join the parent module's ./... sweep."""
    prefix = '' if module_root in ('', '.') else module_root.rstrip('/') + '/'
    if not file.startswith(prefix):
        return False
    stop = PurePosixPath(module_root or '.')
    for directory in [file and PurePosixPath(file).parent, *PurePosixPath(file).parent.parents]:
        if directory == stop or directory == PurePosixPath('.'):
            break
        if (Path(workspace) / directory / 'go.mod').is_file():
            return True
    return False


def ignored(file, patterns):
    return any(fnmatchcase(file, pattern)
               or (pattern.startswith('**/') and fnmatchcase(file, pattern[3:]))
               for pattern in patterns)


def select_targets(files, rows, module_root='', ignored_patterns=(), workspace=None, texts=None):
    """Affected import paths, or (None, reason) when coverage cannot be proven."""
    by_dir = {row['dir']: row['path'] for row in rows}
    imported_by = {}
    for row in rows:
        for dep in row['imports']:
            imported_by.setdefault(dep, set()).add(row['path'])
    seeds, test_only, skipped = set(), set(), 0
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
        if owners:
            if file.endswith('_test.go') and not embedded:
                test_only |= owners
            else:
                seeds |= owners
            continue
        if texts is None:
            texts = source_index(rows, workspace or '.')
        literals = literal_owners(file, texts, module_root)
        if literals:
            seeds |= literals
            continue
        if workspace and nested_module(file, module_root, workspace):
            skipped += 1
            continue
        if ignored(file, ignored_patterns):
            skipped += 1
            continue
        return None, f'未映射变更 {file}：全量'
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
    suffix = f'，忽略 {skipped} 个无证据文件' if skipped else ''
    return affected, f'定向 {len(affected)}/{len(rows)} 个包{suffix}'


def shard_groups(rows, targets, count):
    weights = {row['path']: 1 + row['tests'] for row in rows if row['path'] in targets}
    count = max(1, min(count, len(weights)))
    groups, loads = [[] for _ in range(count)], [0] * count
    for path in sorted(weights, key=lambda name: (-weights[name], name)):
        index = loads.index(min(loads))
        groups[index].append(path)
        loads[index] += weights[path]
    return [group for group in groups if group]


def plan(policy, event_name, reliable, files, rows, workspace=None):
    """Return (matrix, mode, reason); rows=None means the module was not listed."""
    try:
        shards = int(str(policy.get('test-shards') or '1'))
    except ValueError:
        shards = 1
    if rows is None:
        entry = {'index': 1, 'packages': './...'}
        if truthy(policy.get('single-runner')):
            entry['label'] = '全量'
        return ({'include': [entry]}, 'bypassed', '包列表不可用：全量')
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
            patterns = [line for line in
                        str(policy.get('selection-ignored-paths') or '').splitlines() if line]
            selected, reason = select_targets(
                files, rows, policy.get('working-directory') or '.',
                patterns, workspace)
            if selected is not None:
                targets, mode = selected, 'affected'
    if mode == 'all' and shards <= 1:
        entry = {'index': 1, 'packages': './...'}
        if truthy(policy.get('single-runner')):
            entry['label'] = '全量'
        return {'include': [entry]}, mode, reason
    groups = shard_groups(rows, targets, shards)
    if truthy(policy.get('single-runner')):
        # 单 runner 模式：一个 job 内并行执行全部分片组，检查列表只剩一条执行记录。
        # label 如实反映选择模式：定向或全量，避免「全部」这种含义不明的叫法。
        merged = ' '.join(pkg for group in groups for pkg in group) or './...'
        include = [{'index': 1, 'label': '定向' if mode == 'affected' else '全量',
                    'packages': merged, 'groups': json.dumps(groups, ensure_ascii=True)}]
        return {'include': include}, mode, reason
    include = [{'index': index + 1, 'packages': ' '.join(group)}
               for index, group in enumerate(groups)]
    return {'include': include}, mode, reason


def main():
    policy = json.loads(os.environ['POLICY_JSON'])
    workspace = os.environ['GITHUB_WORKSPACE']
    rows = None
    if wants_listing(policy):
        directory = Path(workspace) / (policy.get('working-directory') or '.')
        listed = package_rows(directory)
        if listed:
            rows = relativize(listed, workspace)
    try:
        files = json.loads(os.environ.get('FILES_JSON') or '[]')
    except ValueError:
        files = None
    matrix, mode, reason = plan(policy, os.environ['GITHUB_EVENT_NAME'],
                                os.environ.get('RELIABLE', ''), files, rows, workspace)
    if not wants_listing(policy):
        reason = '未启用定向或分片：全量'
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('matrix=' + json.dumps(matrix, ensure_ascii=True) + '\n')
        output.write('selection=' + mode + '\n')
    print(reason)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        legs = ', '.join(
            '{}（{} 包）'.format(entry.get('label') or '分片 ' + str(entry['index']),
                                len(entry['packages'].split()))
            for entry in matrix['include'])
        summary.write(f'### Go Test 执行计划\n\n{reason}；{legs}。\n\n')


if __name__ == '__main__':
    main()
