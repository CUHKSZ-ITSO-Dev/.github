# CUHKSZ-ITSO-Dev 公共 GitHub 配置

这个仓库集中维护组织内仓库共用的 PR 模板、PR 规范检查和 reusable workflows。业务仓库只保留很薄的调用文件，具体规则、工具版本、日志文本和检查逻辑尽量在这里统一调整。

## 公共能力

| 路径 | 用途 | 使用仓库 |
| --- | --- | --- |
| `.github/pull_request_template.md` | 组织统一 PR 模板，要求填写背景、改动、影响、截图 / 验证材料。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `actions/check-pr-body/action.yml` | 检查 PR 描述是否满足组织模板必要小节。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/pr-check.yml` | 统一检查 PR 描述、commit 数量和 Commit Message。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/auto-assign-pr-author.yml` | PR 无负责人时自动把 PR 作者设为 assignee。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/stale-pr.yml` | 统一标记和关闭不活跃 PR，并维护 `stale` / `no-stale` 标签说明。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/golangci-lint.yml` | 统一 Go 静态检查，支持 LFS、CGO、子目录模块和 glob 变更过滤。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/go-test.yml` | 统一 Go 测试，支持自动分片、LFS、CGO 和可选测试数据库。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/frontend-check.yml` | 统一前端检查，支持 Node/pnpm、缓存、Playwright、glob 变更过滤和自定义检查命令。 | `UI`、`UniAuth` |
| `.github/workflows/migration-check.yml` | 统一 PostgreSQL / SQL Server 迁移检查，默认保护历史迁移不可修改或删除。 | `Chat`、`open-platform`、`UniAuth` |

业务仓库只保留触发入口、仓库路径、数据库类型、测试命令等必要参数；公共检查逻辑、工具版本和中文提示文本集中在这里维护。发布、部署、制品构建等不属于 PR 基线的流程仍由各业务仓库自行维护。
