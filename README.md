# CUHKSZ-ITSO-Dev 公共 GitHub 配置

这个仓库集中维护组织内仓库共用的 PR 模板、PR 规范检查和可复用工作流。业务仓库只保留很薄的调用文件，具体规则、工具版本、日志文本和检查逻辑尽量在这里统一调整。

## 公共能力

| 路径 | 用途 | 使用仓库 |
| --- | --- | --- |
| `.github/pull_request_template.md` | 组织统一 PR 模板，要求填写背景、改动、影响、验证、材料。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `actions/check-pr-body/action.yml` | 读取公共 PR 模板中的二级标题，动态检查 PR 描述是否填写对应小节。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/pr-check.yml` | 统一检查 PR 描述、commit 数量、Commit Message，并按集中配置检查迁移文件。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/sync-pr-template.yml` | PR 模板进入 `main` 后，自动发现调用公共 PR 检查的仓库，为模板差异创建同步 PR，并由组织自动化令牌绕过门禁合并。 | 自动发现 |
| `.github/workflows/stale-pr.yml` | 统一标记和关闭不活跃 PR，并维护 `stale` / `no-stale` 标签说明。 | `Chat`、`open-platform`、`UI`、`UniAuth` |
| `.github/workflows/golangci-lint.yml` | 统一 Go 静态检查，支持 LFS、CGO、子目录模块和 glob 变更过滤。 | `Chat`、`open-platform`、`UniAuth` |
| `.github/workflows/go-test.yml` | 原 Actions 执行 Go Test，支持变更闭包定向与分片并发，三个业务仓库仅在磁盘不足时回退 DevPortal。 | `Chat`、`open-platform`、`UniAuth`、`Doubao-Speech-Service` |
| `.github/workflows/frontend-suite.yml` | 组合 Lint 与 Chromium、Firefox、WebKit 四项并行检查，业务入口无需参数。 | `UI` |
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

## 普通 PR 的迁移文件门禁

`actions/check-migration-files` 从共享仓库的 `actions/ci-policy/policy.json` 读取
`migration-files` 配置，检查六位连续编号、up/down 配对、并发索引单语句，以及基线已有 SQL 不可删除、改名或改写。
Chat、UniAuth、open-platform 接在原有 PR 规范检查中；豆包语音服务接在 Go Test 的范围
判断之前，即使只修改 SQL 或 PR 仍是草稿也执行文件门禁。其他仓库不新增这项检查。
候选分支不能通过修改自己的校验脚本绕过规则；真实数据库 up/down 和 SQL 行为仍由数据库
回归及部署前验证负责。RAG 使用 Alembic 版本链，不适用六位 SQL 文件约定。

豆包语音 Go Test 同时准备独立 PostgreSQL 临时库并设置 `DOUBAO_MIGRATION_TEST_DSN`，
使已有迁移往返测试实际执行；SQL 目录纳入集中测试范围。普通 PR 门禁不能依赖开发服部署
标签，DevPortal 的“未触发开发服部署”绿色状态也不代表迁移文件已检查。

Docs CMS 的类型检查与现有 Node 测试、RAG 的单元/契约测试及 Alembic 单 head 校验
由业务仓库的普通 PR 入口调用共享执行器；Gateway 的 Go 测试同样使用共享执行器。
新增调用方时，同时核对 `ready_for_review` 与外层 `on.paths`，共享范围配置无法补救
未被 GitHub 触发的工作流。doc-intelligence 的测试范围包含测试工作流与覆盖率配置。

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

## CI 运行环境与资源

Go、静态检查、前端、迁移和 PR 规范工作流统一维护稳定工具版本，当前为 Go 1.27.2、Node 26.11.1、pnpm 12.10.1、golangci-lint 2.14.0、migrate 4.20.1。检查临时数据库默认使用固定 digest 的 PostgreSQL 18.6 / SQL Server 2025。UniAuth 与 open-platform 的 Go 测试统一使用 PostgreSQL 18.6；旧 UniAuth PostgreSQL 17 例外对应的 GoFrame 驱动问题已在业务主分支升级中修复。版本兼容回归和业务测试失败分别记录，不通过降级数据库掩盖失败。

各检查按路径和草稿策略选择执行，race、迁移契约及检查命令保留。Go 编译并发对应托管 runner 实际 CPU 数量；`clean-unused-sdks` 默认开启，但仅在缓存恢复后磁盘不足时，依次清理不使用的 .NET、GHC、Android SDK，达到目标余量立即停止。Chat、open-platform 与未纳管仓库保留 20 GiB 目标；UniAuth 按已完成检查的实测峰值使用 8 GiB。需要这些 SDK 的未纳管调用方可显式传入 false。

`actions/ci-resources` 每 5 秒采样机器 CPU、内存及磁盘余量，在步骤日志输出 `CI_RESOURCE_SUMMARY` 并写入运行摘要，用于依据实际消耗选择执行环境。采样包含 runner 和临时数据库，不能当成单一检查进程的峰值。GitHub 原生检查各自保留结果，DevPortal 部署状态只反映开发服交付。

### 集中管理检查配置

Chat、UniAuth、open-platform、UI 的 Go 测试、lint、前端与迁移检查配置统一放在 `actions/ci-policy/policy.json`。共享工作流从自身 action 的可信 checkout 读取配置，按 `github.repository` 和检查类型选择；上述仓库传入的旧 `with` 参数不覆盖集中配置。其余调用仓库保持原有参数行为，逐仓迁移时再加入清单。

UI 的前端入口无 `with` 参数，仅调用 `frontend-suite.yml`；组合层在公共仓库选择四个固定配置，通用 `frontend-check.yml` 执行器从集中配置读取细则。分别提供 Lint（静态检查、i18n、单测、构建）和三个引擎的 E2E；Node 24、pnpm 12.2.1、路径过滤和执行命令均由集中配置管理。旧 UI 入口按原有浏览器字段映射到固定兼容配置：Chromium 保留原先完整前端检查，Firefox / WebKit 保留各自 E2E；旧命令与版本参数不覆盖集中配置。`CI / Lint / 前端检查`、`CI / Chromium E2E / 前端检查`、`CI / Firefox E2E / 前端检查`、`CI / WebKit E2E / 前端检查` 与 PR 规范检查均为 UI main 的必需检查，旧分支需合入新的薄入口才能提供新检查名称。

业务仓库保留 GitHub 所需的事件触发入口及共享工作流引用，删除工具版本、检查命令、数据库参数和路径过滤等 `with` 配置。仓库差异、集成测试环境变量、race 检测和迁移回滚验证均在集中配置中保留。此次收口不批量升级版本；兼容性升级应先通过真实检查再更新集中配置。

UI 的三个浏览器在 PR 上按下文的已核验映射选择用例，其他变更和事件保持全量。UniAuth 复用同一范围识别与用例选择器，在原有单个前端检查中执行 Chromium、Firefox；可靠 PR 文件列表传给 manifest 的 `check:ci`，按输入及依赖链选择完整阶段。普通文档只跑命中的静态门禁，不构建或安装浏览器；CI 入口由专用策略与 actionlint 检查承担。源码运行完整静态与构建，自动配额列表的已核验页面映射运行真实页面、刷新周期回归和设计系统冒烟；独立 spec 可定向选择。未知源码、共享组件/夹具、依赖、证据不足、旧分支缺少 CI 模式或选中用例不存在均保留完整命令。旧分支仍安装两引擎，避免其混合浏览器命令缺依赖。

浏览器环境由集中配置的 `playwright-image` 指定带 digest 的官方 Playwright noble 镜像，预装浏览器和系统依赖；Lint 及其他仓库默认保持 runner 原生执行。容器复用 runner 已安装的 Node、pnpm 和工作区依赖，不另装一套工具，不挂载凭据，使用独立 HOME；镜像与项目实际 `@playwright/test` 版本不匹配时直接失败，升级依赖时同步更新本仓库的镜像版本和 digest。通过 CLI 固定两个 worker，并禁止 focused tests；不启用分片，不改变已有重试设置；用例选择不改变浏览器覆盖。测试 JSON、失败 trace 和环境耗时保留七天。

`前端浏览器基准` 工作流在本仓库手动运行，对同一个 UI 提交 SHA 比较三浏览器的一、两个 worker，关闭重试并核对完整用例身份、预期结果、跳过状态和首次执行结果；缺失报告、空执行、失败、flaky 或覆盖差异均失败。业务代码只检出到临时 runner，不写入业务仓库。工作流使用现有 `ITSO_AUTOMATION_TOKEN` 只读检出私有 UI 仓库，检出后移除 Git 凭据；运行前确保该 token 仍有读取权限。调整镜像或并行度前执行此基准，不用耗时改善替代覆盖核对。共享组件、页面和浏览器行为仍按各业务仓库自己的 E2E 契约验证，不能只凭文件路径推断所有使用方都已覆盖；新增定向映射须核对实际调用方和运行时断言。

业务入口与集中配置沿用现有代码审查规则，不额外配置 CODEOWNERS。集中配置按仓库分别维护测试目录、数据库版本、准备命令、路径过滤、LFS/CGO 和前端工具要求；共享执行器只负责通用步骤。业务新增测试环境、模块或依赖时同步更新对应仓库配置，不能把所有仓库强行套用同一组参数。未纳入集中配置的仓库继续使用原有调用参数。Chat、UniAuth、open-platform 保留原 Go Test 入口；GitHub runner 明确磁盘不足时，统一工作流按相同 commit 请求 DevPortal 测试并等待结果，最终仍由原 Actions Go Test job 给出结论。普通测试失败不触发回退，DevPortal 不扫描开放 PR 自动补测。PR 测试直接执行最后推送的 head，不依赖合并预览或合并冲突判定。

### 检查范围与等待时间

- Chat、UniAuth、open-platform、UI 仅修改业务 CI 调用入口时，不再启动 Go 测试、lint、前端依赖安装或迁移数据库；PR 规范检查通过 actionlint 验证改动的工作流。检查名称保持不变，无相关改动的检查成功返回，避免 required check 一直等待。集中配置或共享执行器修改在本仓库运行配置、路径选择、提交规范、磁盘策略测试和 actionlint；修改实际测试行为后还须按受影响仓库验证完整测试。
- Go 测试关注源码、模块依赖、工作区、迁移 SQL、测试夹具及仓库使用的嵌入资源；linter 配置仅触发 lint。UniAuth lint 不再因普通后端文档变化而运行。开启 `test-selection` 的仓库按 `go list` 依赖闭包（含 TestImports / XTestImports / go:embed / testdata 归属）选择受影响包执行测试；无法归属包目录的变更文件先在全部 Go 源码中查找带引号的路径字面量（`os.ReadFile` 等运行时读取），命中后以引用方包为种子；仍无归属的嵌套模块文件和 `selection-ignored-paths` 列出的无证据路径（文档、CI 配置等集中配置项）跳过，其余未映射文件一律回退全量。依赖、工作区、vendor、证据不足或非 PR 事件同样回退全量，不按单个修改文件猜测依赖范围。
- PR 规范检查和本仓库配置检查使用 `ubuntu-slim`。提交消息沿用 commitlint 19 的 conventional 规则及仓库 `commitlint.config.mjs`，使用锁定的 npm 依赖缓存，去掉 Docker 镜像下载、完整 Git 历史和短任务资源采样。提交数量仍限制在 1–30 个，描述小节要求不变。
- Go 测试在 PR 无相关改动时不 checkout 业务代码；执行测试时使用浅 checkout。Go 缓存按工具链版本区分，编译缓存允许同键前缀回退以覆盖依赖升级场景，模块下载缓存按依赖锁定文件为键。数据库镜像在 checkout 后后台预拉取，就绪等待隐藏在 Go 安装与编译期间。Python 检查开启 uv 缓存。前端、Python 与未纳管仓库原有自定义命令和路径参数保留；Redis/RabbitMQ 集成测试继续需要完整 runner 和服务，不能改用 slim。
- 各检查只取消同一 PR、同一调用工作流和模块的过期任务，前端检查另按检查配置（旧入口按 Playwright 浏览器集合）区分，避免并行引擎互相取消；push 不自动取消。Go Test 计划与分片按各自并发组取消，聚合 job 使用独立并发组；被取代运行的聚合不再写回失败结论，结果以最新运行为准。GitHub 托管 runner 的排队仍由 GitHub 分配；`ubuntu-slim` 同样受账户并发限制，轻量化不能保证零等待。

DevPortal Go Test 使用每任务独立、有容量限制的临时缓存，避免恢复大型 Actions 缓存导致磁盘耗尽。Actions 在恢复缓存前释放不使用的 SDK；恢复编译缓存与模块下载缓存，不恢复体积更大的模块解压目录——下载缓存按内容寻址，解压仍在本地完成。Go Test 缓存以操作系统、架构、Go 版本和依赖锁定文件为键，不再为每个提交 SHA 上传一份相同依赖及编译缓存；分片场景按分片编号区分后缀并允许同键前缀回退。依赖未变且缓存命中时不重复保存；Go 仍根据源码及编译参数判断哪些包需要重新编译。新缓存键不回退到旧的大型缓存。Git LFS 缓存按所需文件的对象 OID 集合生成键，Go Test 与 lint 复用相同二进制对象，普通代码变更不再制造重复 LFS 缓存。PR 缓存仍受 GitHub 分支作用域限制，无法在不同 PR 之间任意共享；不通过增加工作流、付费 runner 或提高缓存上限绕过这个限制。

### 变更识别与检查范围

`actions/ci-scope` 统一 Go、前端、Python 和只构建不发布的 Docker PR 检查的范围判断，沿用 dorny/paths-filter 的 glob 与调用方匹配语义。PR 获取全部变更路径，包括重命名前后的路径；检测失败、结果缺失或达到 API 的 3000 文件上限时执行完整检查，不返回空执行成功。`always-run-paths` 独立使用 OR，不受主过滤器的 AND/排除策略影响。手动、定时和合并队列事件执行完整检查；push 沿用相关路径判断。

| 检查 | 范围控制 | 保留的验证 |
| --- | --- | --- |
| Go Test | 源码、模块依赖、工作区、嵌入资源和测试夹具；仓库差异仍由集中配置管理。 | 纳管仓库按 `go list` 依赖闭包定向到受影响包并按 `test-shards` 分片并发；无法证明覆盖范围时回退全量。保留 race、数据库集成与生成物验证。 |
| golangci-lint | 源码、模块依赖、工作区、嵌入资源和测试夹具；仓库差异仍由集中配置管理。 | 命中后检查整个相关模块，不按单文件裁剪包。 |
| 前端 Lint | 前端相关路径。 | 静态检查、i18n、单测、构建保持全量。 |
| UI 三浏览器 E2E | `actions/ci-e2e/ui.json` 的已核验源码映射，或直接修改的独立 `.spec.ts`，加固定应用壳冒烟。 | 三引擎、focused-test 防护、原重试和证据上传；非 PR、未知源码、共享夹具、缺失/删除的用例均回退全量。 |
| Python uv | 未纳管调用方沿用原参数；doc-intelligence 关注 Python、协议、测试及运行/检查配置，WebSearch 仅排除已知文档和 CI 入口。 | 保留调用方的版本、环境变量、依赖安装和完整检查命令，不猜测 Python 动态依赖来裁剪单测。 |
| Redis / RabbitMQ 集成检查 | 单独的轻量范围 job 先判断，再决定是否启动服务；只需 contents read。 | 只有范围 job 成功且显式返回 false 才跳过；范围 job 故障继续完整检查，不让 skipped 掩盖失败。 |
| 迁移检查 | 保留迁移及启动/依赖路径，并用不合并重命名的 diff 检查旧、新路径。 | 历史 SQL 不可修改/删除，数据库、schema 契约和回滚完整执行。 |
| Docker 构建检查 | 仅 PR、`push: false` 且未指定其他 checkout ref 时允许路径判断；默认所有文件相关，调用方可按真实构建 context 设置路径。 | 构建上下文、Dockerfile、COPY 输入和参数依赖未核清时保持全量；发布、标签、显式 ref 构建不因 PR 路径跳过。 |
| PR 规范与配置检查 | 描述、提交及工作流内容；不因没有业务源码变化跳过。 | 保留原规范检查及 actionlint。 |
| 制品发布、GitOps、清理、不活跃 PR 与模板同步 | 保留各自的事件与目标状态策略，不套用业务源码过滤。 | 避免跳过必须交付的版本、部署或维护动作。 |

目前 UI 源码定向映射仅覆盖公告预览页自身及其单测；独立 E2E 文件变更还会执行产品路由、校园入口和主题冒烟。公告共享组件同时用于生产弹窗和历史页，现有冒烟将公告状态置为无新公告，不能证明激活后的生产行为，因此修改这些共享组件仍执行全量。路由、store、全局样式、依赖、构建配置和未映射模块也执行全量。新增映射先核验用例确实激活相关行为，不能以 import 图、URL 或文件名相似替代证据。选中用例在旧分支上不存在时回退全量，不使用 `--pass-with-no-tests`。

新机制不改已有 workflow/job 的名称和 ID，`workflow-identities.json` 及测试保护这些身份。跳过发生在 job/step 内，保留既有必需检查结果。Go Test 拆分为计划、分片与聚合 job：计划在单个 job 内完成路径过滤与包级分片计算，分片 job 按 matrix 并发执行且各自保留磁盘不足回退，聚合 job 沿用原 `Go Test` 名称汇总必需检查结果。

仓库可把 `go-test` 的 `single-runner` 置为 true，将全部分片合并为一个 matrix 项（检查显示为「Go Test 全部」，检查列表由 N+2 条收敛为 3 条），由 `go-test-hosted/shards.py` 在同一 job 内并行执行各组：每组检出独立 `git worktree` 并以 `GO_TEST_GROUP_INDEX` 区分，prepare-command 逐组执行且其写入的 `$GITHUB_ENV` 仅作用于本组。需要数据库隔离的仓库应在 prepare-command 中按该变量派生库名（UniAuth 以 `_g<index>` 为后缀）；未派生且组间存在共享外部状态的仓库不得开启。使用 Git LFS 的仓库暂不适用，worktree 不携带 LFS 内容。非磁盘失败的回退步如实报告 `--- FAIL` 测试名而非笼统提示；磁盘不足但仓库未启用 DevPortal 回退时单独报错。公共仓库只能控制调用后的执行范围：业务入口若在 `on.paths` 中漏列文件，共享流程无法补启动该 workflow；doc-intelligence 的现有入口仍存在这一上游限制，需在业务仓库单独维护。Docker 的调用方若要缩小范围，也须按自己的 context 明确传参；本次不推测私有业务构建输入。

维护范围策略时运行 `ci-scope`、`ci-e2e`、`ci-policy`、`go-test-plan` 的测试以及现有配置检查和 actionlint，并回放真实 PR 文件列表与 Playwright `--list` 核对选择结果；改变运行时测试行为须补相关浏览器执行。所有范围判断和选择的用例写入 Actions summary，便于区分定向执行、完整回退和跳过原因。

### Cluster Helm 检查

Cluster 的 `Helm Check` 调用 `helm-check.yml`，Helm/Python 版本、检查命令和路径范围由
`actions/ci-policy/policy.json` 的 `CUHKSZ-ITSO-Dev/Cluster` 配置统一维护。Cluster 保留
Chart、环境契约检查脚本、测试和锁定的 `requirements-ci.txt`，公共流程不访问集群或发布制品。
PR 入口始终创建检查，范围判断在 job 内执行；保守覆盖所有顶层目录的改动，避免新 Chart 的模板、配置或脚本漏检。
检查枚举候选代码实际存在的顶层 `*/Chart.yaml`；平台三环境与交付五 scope 保留原矩阵，其他 Chart 逐一执行 `helm lint`，不预先要求尚未合并的 Chart。
草稿 PR 仍检查，手动运行执行全量；仅取消同一 PR 的过期检查，main push 不取消。
执行前固定 Ubuntu 24.04、Helm 和 Python、缓存 pip 下载，设置 20 分钟超时并记录 runner 资源消耗。
遥测和三环境探针由发布契约脚本复用已有渲染验证，Python 语法检查覆盖整个 scripts 目录。
共享工作流新增或执行行为调整时，先验证公共配置与 actionlint，再对 Cluster 精确提交执行完整检查。
