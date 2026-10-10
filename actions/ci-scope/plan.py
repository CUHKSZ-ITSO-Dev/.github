"""Keep uncertain change detection conservative; never execute candidate code."""
import json
import os
from pathlib import Path


def plan(event_name, event, skip_draft, outcome, changed, always, files):
    if event_name == 'pull_request' and skip_draft and event['pull_request'].get('draft'):
        return False, False, [], '草稿 PR'
    if event_name not in ('pull_request', 'push'):
        return True, False, [], '手动、队列或其他事件：完整检查'
    if outcome != 'success':
        return True, False, [], '路径识别失败：完整检查'
    if not isinstance(files, list) or any(not isinstance(f, str) for f in files):
        return True, False, [], '文件列表无效：完整检查'
    # The API is capped at 3000 entries. Renames can produce two paths, so
    # equality is deliberately conservative as well.
    if event_name == 'pull_request':
        count = event['pull_request'].get('changed_files')
        if count is None or count >= 3000 or len(files) < count or len(files) >= 3000:
            return True, False, [], 'PR 文件列表可能不完整：完整检查'
    if changed not in ('true', 'false') or always not in ('true', 'false'):
        return True, False, [], '路径判断缺失：完整检查'
    run = changed == 'true' or always == 'true'
    return run, True, files, '存在相关变更' if run else '无相关变更'


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    try:
        files = json.loads(os.environ.get('FILES_JSON', ''))
    except ValueError:
        files = None
    run, reliable, files, reason = plan(
        os.environ['GITHUB_EVENT_NAME'], event, os.environ['SKIP_DRAFT'] == 'true',
        os.environ['FILTER_OUTCOME'], os.environ['CHANGED'], os.environ['ALWAYS'], files)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'run={str(run).lower()}\nreliable={str(reliable).lower()}\n')
        output.write('files=' + json.dumps(files, ensure_ascii=True) + '\n')
    print(reason)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write(f'### 检查范围\n\n{reason}；识别文件数：{len(files)}。\n')


if __name__ == '__main__':
    main()
