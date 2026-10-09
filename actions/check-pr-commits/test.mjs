import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { checkCommits } from './check.mjs';
const commit = (message) => ({ sha: 'abc123', commit: { message } });

test('保留中文 conventional commits、merge 和 revert 的原规则', async () => {
  await checkCommits([commit('fix(ci): 收紧检查范围'), commit("Merge branch 'main' into fix/ci"),
    commit('Revert "fix(ci): 收紧检查范围"\n\nThis reverts commit abc123.')], process.cwd());
});
test('拒绝缺少类型、空描述、未知类型及过长正文', async () => {
  for (const message of ['update ci', 'fix(ci): ', 'unknown(ci): change', 'fix(ci): change\n\n' + 'x'.repeat(101)]) {
    await assert.rejects(checkCommits([commit(message)], process.cwd()));
  }
});
test('检查全部提交并保留数量限制', async () => {
  await assert.rejects(checkCommits([commit('fix(ci): 正常'), commit('bad')], process.cwd()));
  await assert.rejects(checkCommits(Array(31).fill(commit('fix(ci): 正常')), process.cwd()));
  await assert.rejects(checkCommits([], process.cwd()));
});
test('仓库自定义 commitlint.config.mjs 仍生效', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'pr-config-'));
  try {
    writeFileSync(join(dir, 'commitlint.config.mjs'), "export default {rules: {'type-enum': [2, 'always', ['custom']]}};\n");
    await checkCommits([commit('custom: change')], dir);
    await assert.rejects(checkCommits([commit('fix: change')], dir));
  } finally { rmSync(dir, { recursive: true }); }
});
