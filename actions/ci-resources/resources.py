"""Bounded machine-level samples; includes test database and build processes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def cpu_ticks(source):
    values = [int(v) for v in source.splitlines()[0].split()[1:]]
    # Guest time is already included in user/nice.
    return sum(values[:8]), values[3] + values[4]


def memory_used(source):
    values = {line.split(':')[0]: int(line.split()[1]) * 1024
              for line in source.splitlines()}
    return values['MemTotal'] - values['MemAvailable']


def storage(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def sample(folder, workspace):
    previous = cpu_ticks(Path('/proc/stat').read_text())
    baseline = storage(workspace)
    result = {'sampleSeconds': 5, 'samples': 0,
              'memoryUsedPeakBytes': 0, 'cpuBusyPeakCores': 0,
              'diskFreeStartBytes': baseline, 'diskFreeMinBytes': baseline}
    while True:
        current = cpu_ticks(Path('/proc/stat').read_text())
        total, idle = current[0] - previous[0], current[1] - previous[1]
        if total > 0:
            result['cpuBusyPeakCores'] = max(result['cpuBusyPeakCores'],
                round((total - idle) / total * (os.cpu_count() or 1), 3))
        previous = current
        result['memoryUsedPeakBytes'] = max(result['memoryUsedPeakBytes'],
            memory_used(Path('/proc/meminfo').read_text()))
        result['diskFreeMinBytes'] = min(result['diskFreeMinBytes'], storage(workspace))
        result['samples'] += 1
        write(folder / 'summary.json', result)
        if (folder / 'stop').exists():
            break
        time.sleep(result['sampleSeconds'])


def main():
    phase = sys.argv[1]
    if phase == 'sample':
        sample(Path(sys.argv[2]), sys.argv[3])
        return
    if phase not in ('start', 'finish'):
        raise SystemExit('phase must be start or finish')
    identity = '-'.join(os.environ.get(k, 'local') for k in
                        ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB'))
    folder = Path(os.environ['RUNNER_TEMP']) / ('ci-resources-' + identity)
    if phase == 'start':
        folder.mkdir(parents=True, exist_ok=True)
        workspace = os.environ['GITHUB_WORKSPACE']
        subprocess.Popen([sys.executable, __file__, 'sample', str(folder), workspace],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        print('CI resources: sampling every 5 seconds; includes database processes')
        return
    if not folder.exists():
        print('CI resources: sampling was not started')
        return
    (folder / 'stop').touch()
    # Give the final sample a bounded opportunity to observe late disk usage.
    time.sleep(5.2)
    summary = folder / 'summary.json'
    if not summary.exists():
        print('::warning::CI resource sampling unavailable; check outcome is unchanged')
        return
    result = json.loads(summary.read_text())
    result['diskConsumedPeakBytes'] = max(0, result['diskFreeStartBytes'] - result['diskFreeMinBytes'])
    print('CI_RESOURCE_SUMMARY=' + json.dumps(result, sort_keys=True))
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as report:
        report.write('\n### CI 资源采样\n\n')
        report.write('5 秒采样，包含 runner、检查进程及临时数据库；不是资源上限，也不改变检查结果。\n\n')
        report.write('| 项目 | 实测值 |\n| --- | ---: |\n')
        report.write(f"| CPU 使用峰值 | {result['cpuBusyPeakCores']:.2f} 核 |\n")
        report.write(f"| 机器已用内存峰值 | {result['memoryUsedPeakBytes'] / 2**30:.2f} GiB |\n")
        report.write(f"| 磁盘剩余最低值 | {result['diskFreeMinBytes'] / 2**30:.2f} GiB |\n")
        report.write(f"| 磁盘增量峰值 | {result['diskConsumedPeakBytes'] / 2**30:.2f} GiB |\n")


if __name__ == '__main__':
    main()
