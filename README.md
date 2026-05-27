# CUHKSZ-ITSO-Dev 公共 GitHub 配置

这个仓库集中维护组织内仓库共用的 PR 模板、PR 规范检查和 reusable workflows。业务仓库只保留很薄的调用文件，具体规则、工具版本、日志文本和检查逻辑尽量在这里统一调整。

## 公共内容

| 路径 | 用途 |
| --- | --- |
| `.github/pull_request_template.md` | 组织统一 PR 模板，要求填写背景、改动、影响、截图 / 验证材料。 |
| `actions/check-pr-body/action.yml` | 检查 PR 描述是否满足组织模板必要小节。 |
| `.github/workflows/pr-check.yml` | 统一检查 PR 描述、commit 数量和 Commit Message。 |
| `.github/workflows/auto-assign-pr-author.yml` | PR 无负责人时自动把 PR 作者设为 assignee。 |
| `.github/workflows/stale-pr.yml` | 统一标记和关闭不活跃 PR，并维护 `stale` / `no-stale` 标签说明。 |
| `.github/workflows/golangci-lint.yml` | 统一 Go 代码检查，支持 LFS、CGO、子目录模块和 glob 变更过滤。 |
| `.github/workflows/go-test.yml` | 统一 Go 自动化回归测试，支持自动分片、LFS、CGO 和可选测试数据库。 |
| `.github/workflows/frontend-check.yml` | 统一前端检查，支持 Node/pnpm、缓存、Playwright、glob 变更过滤和自定义检查命令。 |
| `.github/workflows/migration-check.yml` | 统一 PostgreSQL / SQL Server 迁移检查，默认保护历史迁移不可修改或删除。 |

## 仓库接入关系

| 仓库 | 接入的公共能力 | 仓库保留的差异 |
| --- | --- | --- |
| `Chat` | PR 检查、自动负责人、不活跃 PR、SQL Server 迁移检查、Go 代码检查、Go 测试 | 使用 SQL Server；Go 检查和测试需要 LFS / CGO；没有前端检查。 |
| `UniAuth` | PR 检查、自动负责人、不活跃 PR、PostgreSQL 迁移检查、`uniauth-gf` Go 检查和测试、`uniauth-vite` 前端检查 | 同仓库包含 Go 后端和 Vite 前端；发布和 dev 自动部署仍在仓库内维护。 |
| `open-platform` | PR 检查、自动负责人、不活跃 PR、PostgreSQL 迁移检查、Go 代码检查、Go 测试 | 保留 schema contract、完整回滚、Git 属性和二进制迁移入口等项目参数；没有前端检查。 |
| `UI` | PR 检查、自动负责人、不活跃 PR、前端构建检查 | 只接入前端检查；release assets 和 ui-builder 部署流程仍在仓库内维护。 |

## 设计边界

- 业务仓库必须保留 `on:` 触发条件；reusable workflow 不能反向统一调用方触发事件。
- PR required check 相关 workflow 不使用 PR 级 `paths-ignore` 跳过；无关改动在 workflow 内部成功跳过，避免 required check 长期 Pending。
- 普通 Go / 前端变更过滤使用 `dorny/paths-filter` 和 glob 列表，调用侧避免维护正则。
- 数据库迁移检查保留 Git diff / pathspec 逻辑，因为它需要识别删除、修改历史迁移、回滚范围和 schema contract。
- 外部 GitHub Actions 使用明确 major 版本；组织内部 reusable workflows 由业务仓库引用 `CUHKSZ-ITSO-Dev/.github/...@main`。

## 接入示例

```yaml
name: PR 检查

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review, edited]

permissions:
  contents: read
  pull-requests: read

jobs:
  pr-check:
    name: PR 检查
    uses: CUHKSZ-ITSO-Dev/.github/.github/workflows/pr-check.yml@main
```
