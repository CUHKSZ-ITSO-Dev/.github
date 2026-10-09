import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import lint from '@commitlint/lint';
import load from '@commitlint/load';

export async function checkCommits(commits, workspace) {
  if (!commits.length || commits.length > 30) {
    throw new Error(`PR 包含 ${commits.length} 个 commit，要求 1–30 个。`);
  }
  const configFile = resolve(workspace, 'commitlint.config.mjs');
  // Same default and optional config file as wagoid/commitlint-github-action v6.2.1.
  const config = await load(
    existsSync(configFile) ? {} : { extends: ['@commitlint/config-conventional'] },
    { cwd: workspace, ...(existsSync(configFile) ? { file: configFile } : {}) },
  );
  const results = await Promise.all(commits.map(async (commit) => ({
    sha: commit.sha,
    result: await lint(commit.commit.message, config.rules, {
      parserOpts: config.parserPreset?.parserOpts ?? {},
      plugins: config.plugins ?? {},
      ignores: config.ignores ?? [],
      defaultIgnores: config.defaultIgnores ?? true,
    }),
  })));
  const errors = results.flatMap(({ sha, result }) =>
    result.errors.map((error) => `${sha}: ${error.message} [${error.name}]`));
  if (errors.length) throw new Error(errors.join('\n'));
  return results;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const commits = JSON.parse(readFileSync(process.argv[2], 'utf8'));
    await checkCommits(commits, process.env.GITHUB_WORKSPACE);
    console.log(`${commits.length} 个 commit 的提交信息检查通过。`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
