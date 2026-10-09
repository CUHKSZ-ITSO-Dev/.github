import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import picomatch from 'picomatch';
const policy = JSON.parse(readFileSync(new URL('../ci-policy/policy.json', import.meta.url)));
const profiles = policy.repositories;
const matches = (repo, kind, path) => picomatch(
  (profiles[`CUHKSZ-ITSO-Dev/${repo}`][kind]['changed-paths'] ?? policy.defaults[kind]['changed-paths']).trim().split('\n'),
  { dot: true })(path);

test('三仓只改 CI 入口不启动 Go 测试、lint 和迁移数据库', () => {
  for (const repo of ['Chat', 'UniAuth', 'open-platform']) {
    for (const file of ['.github/workflows/go-test.yml', '.github/workflows/test.yml', '.github/workflows/golangci-lint.yml', '.github/workflows/migration-check.yml']) {
      assert.equal(matches(repo, 'go-test', file), false, `${repo}/${file}`);
      assert.equal(matches(repo, 'golangci-lint', file), false, `${repo}/${file}`);
      const migration = profiles[`CUHKSZ-ITSO-Dev/${repo}`]['migration-check'];
      if (migration) assert.equal(new RegExp(migration['migration-path-pattern']).test(file), false);
    }
  }
  assert.equal(matches('UniAuth', 'frontend-check', '.github/workflows/frontend-lint.yml'), false);
});
test('源码、依赖及测试夹具仍执行 Go 测试', () => {
  for (const repo of ['Chat', 'UniAuth', 'open-platform']) {
    const prefix = repo === 'UniAuth' ? 'uniauth-gf/' : '';
    for (const path of ['main.go', 'go.mod', 'go.sum', 'internal/x/testdata/fixture.json']) {
      assert.equal(matches(repo, 'go-test', prefix + path), true, `${repo}/${path}`);
    }
    assert.equal(matches(repo, 'go-test', 'go.work'), true);
  }
});
test('嵌入数据与迁移仍执行检查，普通文档跳过', () => {
  for (const [repo, files] of Object.entries({
    Chat: ['manifest/sql/mssql/000001.up.sql', 'internal/service/tools/widget_guide/contract.json', 'internal/service/video/skill_seedance.md'],
    UniAuth: ['uniauth-gf/manifest/sql/postgres/000001.up.sql', 'uniauth-gf/resource/config/core_rbac.conf', 'uniauth-gf/resource/public/cuhksz-logo-square.png'],
    'open-platform': ['manifest/sql/postgres/000001.up.sql', 'internal/service/tokencount/assets/tokenizer.json'],
  })) {
    for (const file of files) {
      assert.equal(matches(repo, 'go-test', file), true, file);
      assert.equal(matches(repo, 'golangci-lint', file), true, file);
    }
    assert.equal(matches(repo, 'go-test', 'README.md'), false);
    assert.equal(matches(repo, 'golangci-lint', 'README.md'), false);
  }
  assert.equal(matches('UniAuth', 'golangci-lint', 'uniauth-gf/docs/guide.md'), false);
});
test('lint 配置只触发 lint，前端源码和锁文件仍检查', () => {
  for (const repo of ['Chat', 'UniAuth', 'open-platform']) {
    const file = (repo === 'UniAuth' ? 'uniauth-gf/' : '') + '.golangci.yml';
    assert.equal(matches(repo, 'golangci-lint', file), true);
    assert.equal(matches(repo, 'go-test', file), false);
  }
  for (const file of ['uniauth-vite/src/app.tsx', 'uniauth-vite/pnpm-lock.yaml']) {
    assert.equal(matches('UniAuth', 'frontend-check', file), true);
    assert.equal(matches('UniAuth', 'go-test', file), false);
  }
});
