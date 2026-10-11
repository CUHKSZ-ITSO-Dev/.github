"""Publish the same resolved policy to DevPortal; candidate code cannot override it."""
import hashlib
import json
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[1] / 'ci-policy/policy.json'
policy = json.loads(source.read_text())
resolved = {repository: policy['defaults']['go-test'] | policy['repositories'][repository]['go-test']
            for repository in ('CUHKSZ-ITSO-Dev/Chat', 'CUHKSZ-ITSO-Dev/UniAuth',
                               'CUHKSZ-ITSO-Dev/open-platform')}
destination = Path(sys.argv[1]) / 'cmd/dev-portal/go_test_policy.json'
destination.write_text(json.dumps({'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'repositories': resolved}, ensure_ascii=False, indent=2) + '\n')
