"""Run trusted repository test policy in an isolated, credential-free Pod."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time


def configuration(repository, policy):
    allowed = {'CUHKSZ-ITSO-Dev/Chat', 'CUHKSZ-ITSO-Dev/UniAuth',
               'CUHKSZ-ITSO-Dev/open-platform'}
    if repository not in allowed:
        raise ValueError('unsupported test repository')
    return policy['defaults']['go-test'] | policy['repositories'][repository]['go-test']


def exported_environment(path):
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            raise ValueError('unsupported test environment entry')
        values[key] = value
    return values


def prepare_database(config):
    deadline = time.monotonic() + 180
    while True:
        try:
            if config['database-kind'] == 'postgres':
                subprocess.run(['psql', '-h', 'localhost', '-U', 'postgres',
                                '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', 'SELECT 1'],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import pymssql
                with pymssql.connect('localhost', 'sa', 'DevPass123!', login_timeout=5,
                                     timeout=5, autocommit=True) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT 1')
                        for name in (config['database-name'], config['app-database-name']):
                            if name:
                                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                                    raise ValueError('invalid test database name')
                                cursor.execute("IF DB_ID('" + name + "') IS NULL CREATE DATABASE [" + name + "]")
            break
        except (subprocess.CalledProcessError, OSError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError('test database did not become ready') from error
            time.sleep(2)
        except Exception:
            if config['database-kind'] != 'sqlserver' or time.monotonic() >= deadline:
                raise
            time.sleep(2)
    if config['database-kind'] == 'postgres' and config['app-database-name']:
        subprocess.run(['createdb', '-h', 'localhost', '-U', 'postgres',
                        config['app-database-name']], check=True)


def main():
    policy_path = Path('/opt/go-test/policy.json')
    expected = os.environ.get('TEST_POLICY_SHA256')
    if expected and hashlib.sha256(policy_path.read_bytes()).hexdigest() != expected:
        print('Runner and controller test policy versions differ', file=sys.stderr)
        sys.exit(125)
    config = configuration(os.environ['TEST_REPOSITORY'], json.loads(policy_path.read_text()))
    workspace = Path('/workspace/source')
    directory = workspace / config['working-directory']
    environment = os.environ.copy()
    environment.update({'CI': 'true', 'GITHUB_WORKSPACE': str(workspace),
                        'GITHUB_REPOSITORY': os.environ['TEST_REPOSITORY'],
                        'GITHUB_ENV': '/workspace/test.env', 'PGPASSWORD': 'postgres',
                        'GOCACHE': '/workspace/cache/build', 'GOMODCACHE': '/workspace/cache/mod',
                        'GOPATH': '/workspace/go', 'HOME': '/workspace/home'})
    environment['PATH'] = '/workspace/go/bin:' + environment['PATH']
    for key, policy_key in [('CGO_ENABLED', 'cgo-enabled'), ('CGO_LDFLAGS', 'cgo-ldflags')]:
        if config[policy_key]:
            environment[key] = config[policy_key]
    if not config['cgo-ldflags'] and config['cgo-library-dir']:
        environment['CGO_LDFLAGS'] = '-L' + str(workspace / config['cgo-library-dir'])
    os.environ.update(environment)
    Path(environment['HOME']).mkdir(exist_ok=True)
    env_file = Path(environment['GITHUB_ENV'])
    env_file.write_text('')
    print('Preparing isolated test database', flush=True)
    try:
        prepare_database(config)
    except Exception as error:
        print('Isolated database setup failed: ' + str(error), file=sys.stderr)
        sys.exit(125)
    print('Running repository preparation', flush=True)
    if config['prepare-command']:
        subprocess.run(['bash', '-euo', 'pipefail', '-c', config['prepare-command']],
                       cwd=directory, env=environment, check=True)
    environment.update(exported_environment(env_file))
    print('Running Go Test', flush=True)
    Path('/workspace/results').mkdir(exist_ok=True)
    subprocess.run(['gotestsum', '--junitfile', '/workspace/results/junit.xml',
                    '--jsonfile', '/workspace/results/tests.json', '--',
                    *shlex.split(config['test-flags']), './...'],
                   cwd=directory, env=environment, check=True)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode or 1)
