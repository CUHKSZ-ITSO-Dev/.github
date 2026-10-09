"""Resolve policy from the trusted action checkout, never the candidate repository."""
import json
import os
from pathlib import Path
from uuid import uuid4


def resolve(repository, kind, legacy, policy):
    defaults = policy['defaults'][kind]
    repositories = {name.casefold(): profiles for name, profiles in policy['repositories'].items()}
    repository = repository.casefold()
    if repository in repositories:
        if kind not in repositories[repository]:
            raise ValueError(f'仓库未配置检查类型：{repository}/{kind}')
        # Ignore every caller override, including empty commands and skip flags.
        return defaults | repositories[repository][kind]
    return defaults | legacy


def main():
    policy = json.loads(Path(__file__).with_name('policy.json').read_text())
    values = resolve(os.environ['GITHUB_REPOSITORY'], os.environ['POLICY_KIND'],
                     json.loads(os.environ['LEGACY_INPUTS']), policy)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for key, value in values.items():
            if isinstance(value, bool):
                value = str(value).lower()
            delimiter = f'policy_{uuid4().hex}'
            output.write(f'{key}<<{delimiter}\n{value}\n{delimiter}\n')
    print(f"已读取集中配置：{os.environ['GITHUB_REPOSITORY']}/{os.environ['POLICY_KIND']}")


if __name__ == '__main__':
    main()
