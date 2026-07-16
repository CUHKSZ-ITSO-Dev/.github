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
| `.github/workflows/dev-slot-metadata.yml` | 为单 PR 开发槽位生成稳定数据库名与按文件名排序的迁移清单，用于识别追加迁移与改写历史迁移。 | `Chat`、`UniAuth` |
| `.github/workflows/dev-release-ticket.yml` | 在构建前持久化 generic 服务发布票据，并在制品就绪或准备失败时原子更新队列。 | `open-platform`、`Doubao-Speech-Service`、`WebSearch`、`rag`、`doc-intelligence`、`ui-cdn` |
| `.github/workflows/dev-release-turn.yml` | 按服务独立 FIFO 队列等待前一操作健康收敛，原子激活 PR、main 或 restore 发布，并为失败回滚保留 previous 快照。 | 同上六个 generic 服务 |
| `.github/workflows/dev-slot-wait.yml` | 等待服务独立 Argo 发布单元写回精确 receipts，只在镜像、迁移、Deployment 和必要回滚全部收敛后返回。 | 全部 9 个开发服标签仓库 |
| `.github/workflows/pr-deploy-eligibility.yml` | 在写入 GitOps 前再次确认 PR 仍开放、SHA 未变化且开发发布标签仍存在，阻止过期构建覆盖开发服。 | 使用开发服标签发布的仓库 |
| `.github/workflows/docker-build-push.yml` | 统一 Docker 镜像构建与推送流程，由业务仓库传入镜像名、上下文和 Dockerfile；支持按需 checkout 指定 ref，并可在 Git LFS 默认拉取后追加指定 include。 | `Chat`、`UniAuth`、`Gateway`、`open-platform`、`Doubao-Speech-Service`、`WebSearch`、`doc-intelligence`、`rag` |
| `.github/workflows/ghcr-cleanup-container-versions.yml` | 统一清理 GHCR 容器包旧版本，默认保留最新 5 个版本。 | `doc-intelligence`、`rag` |
| `.github/workflows/frontend-docker-build-push.yml` | 统一前端构建后再构建 Docker 镜像的流程，用于 Dockerfile 依赖预构建静态目录的项目；支持按需生成同源 `version-data.json`，字段包含版本、完整提交 SHA、提交链接、构建时间、拉取请求和拉取请求链接。版本页状态由 Gateway 聚合时统一判断。 | `UniAuth` |
| `.github/workflows/frontend-release-assets.yml` | 统一前端静态制品构建、打包和 GitHub Release 发布流程；支持按需生成同源 `version-data.json`，字段包含版本、完整提交 SHA、提交链接、构建时间、拉取请求和拉取请求链接。版本页状态由 Gateway 聚合时统一判断。 | `UI` |
| `.github/workflows/gitops-yq-bump.yml` | 统一 GitOps 仓库 checkout、yq 更新、提交和重试推送流程。具体仓库、路径和字段由业务仓库传入。 | `UI`、`UniAuth` |
| `.github/workflows/gitops-yq-script-bump.yml` | 统一 GitOps 仓库 checkout、yq 安装、脚本式多文件更新、提交和重试推送流程。适用于一次发布需要同时更新 values、Chart.yaml 等多个 YAML 文件的仓库。 | `Docs` |

业务仓库只保留触发入口、仓库路径、数据库类型、测试命令等必要参数；公共检查逻辑、工具版本和中文提示文本集中在这里维护。发布、部署、制品构建的通用机械步骤可以复用本仓库工作流；具体部署仓库、环境路径、集群字段、对象存储端点、Secret 名称映射和内部架构说明仍由各业务仓库自行维护。

## 开发服标签发布协议

9 个纳入 `auto-deploy-to-dev-server` 的仓库各自持有独立发布队列和终态 receipt。`Chat`、`UniAuth`、`UI` 以及六个 generic 服务分别写入 Cluster 的独立 unit overlay；`UI` 另走 `.uiBuilder.devRelease`，不使用 generic 镜像切换工作流。唯一的跨队列互斥是 `UI` 与 `ui-cdn` 实际由同一 Argo Application 同步，因此 `ui-cdn` 的真实激活必须先取得 `.uiCdn.releaseLock`，健康完成或回滚后再由集群侧 fenced 清锁；该锁不合并两者的队列、receipt 或镜像状态。`Chat` 与 `UniAuth` 还在各自独立队列之上管理 golang-migrate 迁移清单、PR 数据库和开发主库提升；其他仓库不会读写这两个数据库状态。

generic ticket 写在 `<serviceRoot>.devRelease.queue[]`，固定字段为 `id`、单调的 GitHub Actions `run_id` 数字 `sequence`、`kind` (`pr|main|restore`)、字符串 `prNumber`、Unix 秒 `createdAt`、`ready` 和 `imageTag`。并发 reserve 后按 `sequence/createdAt/id` 排序，不能把抢到 Git push 的先后当作 FIFO。所有事件都必须在构建前 reserve，只有制品就绪后才置 `ready=true`；构建、ready 或 turn 失败会立即移除未激活票据并写 failed receipt，不等 4 小时过期。turn 只在票据到达队首、前一 `operationID == completedID` 且不在 rollback 时激活；激活前写入 `previous` 镜像 tag/digest 存在性与槽位状态，Argo SyncFail 时按该快照回滚。

未激活 ticket 保留 4 小时，receipts 保留 7 天；`previous` 保留最近一次真实切换的回滚快照，并在下一次激活时更新。调用方只以 receipts 的 `succeeded|failed|stale|expired` 为终态，不把 GitOps 提交成功或单独 `completedID` 变化当作部署成功。
