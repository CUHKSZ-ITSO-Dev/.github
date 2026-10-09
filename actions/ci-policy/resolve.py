"""Resolve policy from the trusted action checkout, never the candidate repository."""
import json
import os
from pathlib import Path
from uuid import uuid4


def resolve(repository, kind, legacy, policy, profile=""):
    defaults = policy['defaults'][kind]
    repositories = {name.casefold(): profiles for name, profiles in policy['repositories'].items()}
    repository = repository.casefold()
    if repository in repositories:
        if kind not in repositories[repository]:
            raise ValueError(f'仓库未配置检查类型：{repository}/{kind}')
        config = repositories[repository][kind].copy()
        profiles = config.pop('profiles', {})
        legacy_profiles = config.pop('legacy-profiles', {})
        if profiles:
            # Old UI entries select a fixed migration profile by browser only;
            # their commands, versions and skip flags still cannot override policy.
            selected = profile or legacy_profiles.get(legacy.get('playwright-browsers', ''))
            if selected not in profiles or (profile and selected == 'legacy-chromium'):
                raise ValueError(f'仓库未配置检查配置：{repository}/{kind}/{selected}')
            config |= profiles[selected]
        elif profile:
            raise ValueError(f'仓库不支持检查配置：{repository}/{kind}/{profile}')
        # Ignore every caller override, including empty commands and skip flags.
        return defaults | config
    if profile:
        raise ValueError(f'未纳管仓库不支持检查配置：{repository}/{profile}')
    return defaults | legacy


def main():
    policy = json.loads(Path(__file__).with_name('policy.json').read_text())
    values = resolve(os.environ['GITHUB_REPOSITORY'], os.environ['POLICY_KIND'],
                     json.loads(os.environ['LEGACY_INPUTS']), policy, os.environ.get('POLICY_PROFILE', ''))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for key, value in values.items():
            if isinstance(value, bool):
                value = str(value).lower()
            delimiter = f'policy_{uuid4().hex}'
            output.write(f'{key}<<{delimiter}\n{value}\n{delimiter}\n')
    print(f"已读取集中配置：{os.environ['GITHUB_REPOSITORY']}/{os.environ['POLICY_KIND']}")


if __name__ == '__main__':
    main()
