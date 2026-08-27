# CUHKSZ-ITSO-Dev 公共 GitHub 配置

这个仓库集中维护组织内仓库共用的 PR 模板、PR 规范检查和可复用工作流。业务仓库只保留很薄的调用文件，具体规则、工具版本、日志文本和检查逻辑尽量在这里统一调整。

## 公共能力

| 路径 | 用途 | 使用仓库 |
| --- | --- | --- |
| `.github/pull_request_template.md` | 组织统一 PR 模板，要求填写背景、改动、影响、验证、材料。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `actions/check-pr-body/action.yml` | 读取公共 PR 模板中的二级标题，动态检查 PR 描述是否填写对应小节。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/pr-check.yml` | 统一检查 PR 描述、commit 数量和 Commit Message。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/sync-pr-template.yml` | PR 模板进入 `main` 后，自动发现调用公共 PR 检查的仓库，为模板差异创建同步 PR，并由组织自动化令牌绕过门禁合并。 | 自动发现 |
| `.github/workflows/stale-pr.yml` | 统一标记和关闭不活跃 PR，并维护 `stale` / `no-stale` 标签说明。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/golangci-lint.yml` | 统一 Go 静态检查，支持 LFS、CGO、子目录模块和 glob 变更过滤。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/go-test.yml` | 统一单检查 Go 测试，支持路径跳过、LFS、CGO 和可选测试数据库。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/frontend-check.yml` | 统一前端检查，支持 Node、pnpm/npm、缓存、Playwright、glob 变更过滤和自定义检查命令。 | `UI`、`UniAuth`、`Gateway` |
| `.github/workflows/python-uv-check.yml` | 统一 Python uv 检查，支持 uv 安装依赖、路径过滤、环境变量注入和自定义检查命令。 | `WebSearch`、`doc-intelligence` |
| `.github/workflows/python-uv-redis-rabbitmq-check.yml` | 统一带 Redis / RabbitMQ 服务的 Python uv 集成检查。 | `doc-intelligence` |
| `.github/workflows/migration-check.yml` | 统一 PostgreSQL / SQL Server 迁移检查，默认保护历史迁移不可修改或删除。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/docker-build-push.yml` | 统一 Docker 镜像构建与推送流程，由业务仓库传入镜像名、上下文和 Dockerfile；支持按需 checkout 指定 ref，并可在 Git LFS 默认拉取后追加指定 include。 | `Chat`、`UniAuth`、`Gateway`、`open-platform`、`Doubao-Speech-Service`、`WebSearch`、`doc-intelligence`、`rag` |
| `.github/workflows/ghcr-cleanup-container-versions.yml` | 统一清理 GHCR 容器包旧版本，默认保留最新 5 个版本。 | `doc-intelligence`、`rag` |
| `.github/workflows/frontend-docker-build-push.yml` | 统一前端构建后再构建 Docker 镜像的流程，用于 Dockerfile 依赖预构建静态目录的项目；支持按需生成同源 `version-data.json`，字段包含版本、完整提交 SHA、提交链接、构建时间、拉取请求和拉取请求链接。版本页状态由 Gateway 聚合时统一判断。 | `UniAuth` |
| `.github/workflows/frontend-release-assets.yml` | 统一前端静态制品构建、打包和 GitHub Release 发布流程；支持按需生成同源 `version-data.json`，字段包含版本、完整提交 SHA、提交链接、构建时间、拉取请求和拉取请求链接。版本页状态由 Gateway 聚合时统一判断。 | `UI` |
| `.github/workflows/gitops-yq-bump.yml` | 统一 GitOps 仓库 checkout、yq 更新、提交和重试推送流程。具体仓库、路径和字段由业务仓库传入。 | `UI`、`UniAuth` |
| `.github/workflows/gitops-yq-script-bump.yml` | 统一 GitOps 仓库 checkout、yq 安装、脚本式多文件更新、提交和重试推送流程。适用于一次发布需要同时更新 values、Chart.yaml 等多个 YAML 文件的仓库。 | `Docs` |

业务仓库只保留触发入口、仓库路径、数据库类型、测试命令等必要参数；公共检查逻辑、工具版本和中文提示文本集中在这里维护。发布、部署、制品构建的通用机械步骤可以复用本仓库工作流；具体部署仓库、环境路径、集群字段、对象存储端点、Secret 名称映射和内部架构说明仍由各业务仓库自行维护。

## PR 模板自动同步

`.github/pull_request_template.md` 合入 `main` 后，`sync-pr-template.yml` 会通过
GitHub 代码搜索发现所有调用
`CUHKSZ-ITSO-Dev/.github/.github/workflows/pr-check.yml@main` 的非归档、非 fork
仓库。目标模板不一致时，流程会重建 `automation/sync-pr-template` 分支、创建
同步 PR，并用目标仓库启用的合并方式执行管理员合并。手动运行工作流时可启用
`dry-run`，只列出需要同步的仓库。同步工作流或脚本本身进入 `main` 时也会执行
一次幂等同步，用于首次启用和逻辑升级。

自动化使用组织级 Actions secret `ITSO_AUTOMATION_TOKEN`。该令牌必须能够读取
组织代码搜索结果，在目标仓库创建分支和 PR，并具备通过 `gh pr merge --admin`
绕过默认分支规则的仓库管理员权限。若令牌缺失、不可见目标仓库或无法管理员
合并，流程会失败并保留已创建的同步 PR，不会退化为直接推送默认分支。新增仓库
只需向该令牌开放仓库、调用公共 `pr-check.yml@main`，无需维护静态仓库清单。

## 开发服标签发布协议

开发服发布已经迁入 `gpt-dev` 集群，由 Dev Portal Controller 统一轮询
`auto-deploy-to-dev-server` 标签、构建镜像、推送 GHCR、提交开发服 GitOps
目标并等待 Argo 与工作负载健康。业务仓库不再运行开发部署工作流；GitHub
Actions 仅保留代码检查，以及标签/正式版本所需的镜像发布。

每个服务同时只有一个有效目标。同一仓库误标记多个 PR 时，以最近更新的
开放 PR 为准；标签移除、PR 关闭或合并后，Controller 自动构建并恢复最新
main。构建工具版本、yq、git-lfs、镜像仓库凭据、GitOps 写入凭据及前端依赖
缓存均由集群统一维护，业务仓库无需重复安装。

`Chat` 与 `UniAuth` 继续使用 Cluster 中的数据库槽位协议：镜像构建完成后才
提交槽位票据，集群负责迁移清单校验、PR 独立数据库、队列切换、失败回滚和
main 恢复。其他普通服务由 Dev Portal 创建持久发布记录并串行提交 GitOps，
发布过程和错误统一在 `/dev/` 查询。
