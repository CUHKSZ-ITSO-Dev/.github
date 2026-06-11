# CUHKSZ-ITSO-Dev 公共 GitHub 配置

这个仓库集中维护组织内仓库共用的 PR 模板、PR 规范检查和可复用工作流。业务仓库只保留很薄的调用文件，具体规则、工具版本、日志文本和检查逻辑尽量在这里统一调整。

## 公共能力

| 路径 | 用途 | 使用仓库 |
| --- | --- | --- |
| `.github/pull_request_template.md` | 组织统一 PR 模板，要求填写背景、改动、影响、验证、材料。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `actions/check-pr-body/action.yml` | 读取公共 PR 模板中的二级标题，动态检查 PR 描述是否填写对应小节。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/pr-check.yml` | 统一检查 PR 描述、commit 数量和 Commit Message。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/auto-assign-pr-author.yml` | PR 无负责人时自动把 PR 作者设为 assignee。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/stale-pr.yml` | 统一标记和关闭不活跃 PR，并维护 `stale` / `no-stale` 标签说明。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/golangci-lint.yml` | 统一 Go 静态检查，支持 LFS、CGO、子目录模块和 glob 变更过滤。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/go-test.yml` | 统一 Go 测试，支持自动分片、LFS、CGO 和可选测试数据库。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/frontend-check.yml` | 统一前端检查，支持 Node、pnpm/npm、缓存、Playwright、glob 变更过滤和自定义检查命令。 | `UI`、`UniAuth`、`Gateway` |
| `.github/workflows/python-uv-check.yml` | 统一 Python uv 检查，支持 uv 安装依赖、路径过滤、环境变量注入和自定义检查命令。 | `WebSearch`、`doc-intelligence` |
| `.github/workflows/python-uv-redis-rabbitmq-check.yml` | 统一带 Redis / RabbitMQ 服务的 Python uv 集成检查。 | `doc-intelligence` |
| `.github/workflows/migration-check.yml` | 统一 PostgreSQL / SQL Server 迁移检查，默认保护历史迁移不可修改或删除。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/pr-dev-version.yml` | 统一生成 PR 开发服发布版本标签，不包含具体部署目标；默认从调用仓库名自动生成小写 slug，格式为 `dev-uniauth-pr-371-49afc8f`，使用环境、仓库 slug、PR 号和 7 位短 SHA。仓库名和服务名不一致时可传入 `repository-slug` 覆盖；保留可选 run 后缀仅用于明确需要绕过缓存或强制重发同一源码版本的特殊场景。 | `UI`、`UniAuth` |
| `.github/workflows/docker-build-push.yml` | 统一 Docker 镜像构建与推送流程，由业务仓库传入镜像名、上下文和 Dockerfile；支持按需 checkout 指定 ref，并可在 Git LFS 默认拉取后追加指定 include。 | `Chat`、`UniAuth`、`Gateway`、`open-platform`、`Doubao-Speech-Service`、`WebSearch`、`doc-intelligence`、`rag` |
| `.github/workflows/ghcr-cleanup-container-versions.yml` | 统一清理 GHCR 容器包旧版本，默认保留最新 5 个版本。 | `doc-intelligence`、`rag` |
| `.github/workflows/frontend-docker-build-push.yml` | 统一前端构建后再构建 Docker 镜像的流程，用于 Dockerfile 依赖预构建静态目录的项目；支持按需生成同源 `version-data.json`，字段包含版本、完整提交 SHA、提交链接、构建时间、拉取请求和拉取请求链接。版本页状态由 Gateway 聚合时统一判断。 | `UniAuth` |
| `.github/workflows/frontend-release-assets.yml` | 统一前端静态制品构建、打包和 GitHub Release 发布流程；支持按需生成同源 `version-data.json`，字段包含版本、完整提交 SHA、提交链接、构建时间、拉取请求和拉取请求链接。版本页状态由 Gateway 聚合时统一判断。 | `UI` |
| `.github/workflows/gitops-yq-bump.yml` | 统一 GitOps 仓库 checkout、yq 更新、提交和重试推送流程。具体仓库、路径和字段由业务仓库传入。 | `UI`、`UniAuth` |

业务仓库只保留触发入口、仓库路径、数据库类型、测试命令等必要参数；公共检查逻辑、工具版本和中文提示文本集中在这里维护。发布、部署、制品构建的通用机械步骤可以复用本仓库工作流；具体部署仓库、环境路径、集群字段、对象存储端点、Secret 名称映射和内部架构说明仍由各业务仓库自行维护。
