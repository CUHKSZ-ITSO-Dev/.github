# Go Test 迁移到 DevPortal 的设计

本文记录迁移实现与切换条件；现网切换状态见文末。范围为 Chat、UniAuth、open-platform 的业务仓库同步与 Go Test 执行迁移；其他 GitHub CI 检查沿用现有执行方式。Go Test 结果用于业务仓库的代码检查，不增加或适配 UniAuth 专用发布准入，也不扩展测试服维护发布流程。

## 问题与目标

截图中的 Chat Go Test 在恢复约 2 GiB 的压缩缓存时出现 `No space left on device`，尚未开始测试。共享工作流目前先恢复 Go 缓存，再执行按余量释放编译空间的步骤；释放步骤无法补救缓存解压阶段的失败。

将测试执行迁到 DevPortal 管理的开发命名空间，由 DevPortal 回传独立 GitHub 提交状态。保留现有仓库测试契约，控制测试资源与缓存容量，避免每次下载和解压 GitHub 缓存。

## 执行链路

```text
DevPortal 观察开放 PR 和 main
  -> 固定源码身份并读取完整变更范围
  -> 登记独立 Go Test 检查记录
  -> Argo 测试队列
  -> 获取源码及所需 LFS 对象
  -> 创建隔离测试环境并执行准备命令
  -> gotestsum 调用 go test（保留各仓库原参数）
  -> 持久化结果与关键诊断
  -> GitHub commit status + DevPortal 详情链接
```

DevPortal 直接观察源码变化，不新增只负责触发或等待的 GitHub Actions job。普通 PR 的测试不依赖部署标签，也不依赖是否请求开发服部署。草稿 PR 沿用跳过策略；转为可审查后重新判定。main 检查独立于当前开发服部署版本，不因已有 PR 占用开发槽位而停测。

第一阶段只接入同仓库 PR；fork PR 必须保留可用的 GitHub CI 路径，直到独立的无凭据执行能力完成验证。DevPortal 转述同一完整 head SHA 的 GitHub Actions Go Test 结果，校验应用来源与检查名，不接受候选自行写入的 commit status；这样切换必需 context 后 fork PR 仍有完成路径。

## 源码身份与状态

PR 执行当前 GitHub 合并预览，记录 repository、PR、head、base、执行 SHA 和测试配置版本。回传绑定 PR head；main 执行完整 main SHA。结果复用必须核对全部输入；base、源码或测试配置变化均使旧结果失效。不能仅用短 SHA 或成功状态判断可复用。

PR 变更范围复用集中 `changed-paths` 与已有 doublestar 组件，保留重命名的旧、新路径。未命中时明确回传“无需测试”；差异列表不完整、获取失败或匹配语法未知时执行全量测试。普通部署仍只观察既定目标分支，独立 Go Test 观察所有开放、非草稿 PR，包括堆叠 PR。

同一 PR 新提交取代旧请求，停止未完成测试并回收其临时环境；旧执行不得回写覆盖新身份的结果。PR 关闭、变为草稿或源码身份改变时收敛旧任务。控制器重启通过持久记录和 Workflow 状态恢复，不依赖进程内任务表。合并预览暂缺时保持等待，存在冲突时明确失败，不退回测试原始 head。

新增独立 context `Dev Portal / Go Test`，与现有 `Dev Portal / 开发服部署` 分开维护：

| 状态 | GitHub 回传 | 证据 |
| --- | --- | --- |
| 排队或执行中 | `pending` | 当前请求与执行阶段 |
| 实际测试通过 | `success` | 同一身份的完整准备及测试均成功 |
| 测试或准备命令失败 | `failure` | 持久化失败阶段、退出码和诊断 |
| 环境故障或重试耗尽 | `error` | 明确未完成验证，不伪装成测试通过 |
| 范围无需执行 | `success` | 明确标记“无需测试”，与实际通过分开记录 |

现有部署状态出口强制写 `success`，不能直接用于 Go Test。Go Test 使用独立状态出口、去重键与过期身份校验。回写失败保留待发送结果，重试；平台故障不放行为测试成功。

## 测试契约与隔离

集中配置继续来自 `.github/actions/ci-policy/policy.json`。可信发布过程把 Go Test 配置固化到执行器或受管配置，记录版本；测试不能从 PR 自带策略文件读取或覆盖命令、镜像、权限及结果语义。避免在 Cluster、DevPortal 和业务仓库各复制一份测试准备命令。

| 仓库 | 保留的测试契约 |
| --- | --- |
| Chat | race、SQL Server 测试库、CGO、真实 LFS 资产、生成文件验证及现有准备命令 |
| UniAuth | `uniauth-gf` 工作目录、race、共享 PostgreSQL 18.6、业务和迁移独立测试库、现有全部数据库测试开关 |
| open-platform | PostgreSQL 测试库、CGO、真实 LFS 资产、绑定集合数据库测试开关 |

每次执行使用独立 Pod 网络和临时数据库存储，允许测试继续连接 localhost。数据库与测试一起结束回收，不使用开发服或测试服业务数据库，不克隆业务数据，不挂载业务配置 Secret。并发任务不得复用固定数据库实例、端口或可写源码目录。

源码获取阶段只使用受限读取凭据，不运行候选脚本；测试阶段不挂载 GitHub、registry、GitOps 或 Kubernetes 写凭据，不挂载 Docker socket。源码交接清除 Git 授权配置，禁止候选修改跨任务可信脚本或缓存。GitHub 结果由控制器读取执行状态后回传，候选代码不持有回传令牌。

现有准备命令通过 `GITHUB_ENV` 传递的变量需要由执行器显式传递到后续测试进程，不能因为离开 Actions 就丢失数据库集成测试开关。实际 Go 版本、CGO 链接库、数据库版本和完整测试参数写入执行记录。

## 资源、缓存与详情

测试使用独立且有上限的队列，同时执行最多两个任务，保留 Argo 全局三个名额中的一个供其他任务使用。该容量已结合开发节点 8 CPU / 32 GiB 和真实测试资源消耗核对。控制器在创建 Workflow 前执行准入，排队请求不提前占用 Argo 名额；重启从 API 恢复容量状态。

第一阶段使用有容量限制的任务独立缓存，先验证冷运行正确性和峰值。后续持久缓存必须按 Go 版本、架构、依赖与可信范围隔离，并具备配额、淘汰和清理责任；不同 PR 不共享可写缓存。恢复或初始化缓存前检查空间，不能把当前磁盘不足问题原样搬到 PVC。缓存失败不得被记录为测试断言失败。

DevPortal 详情显示源码身份、排队和实际步骤、耗时、退出码、失败分类及有界诊断。执行结果持久化到检查记录，完整日志使用既有日志系统；Workflow 清理后仍能查询关键结果。保留沿用开发服执行现场与检查历史各自的生命周期，不能用延长 Pod 留存代替归档。

## 实施范围与切换

1. DevPortal 增加独立 Go Test 计划、队列、执行协调、结果回写及详情；覆盖重启、取消、旧结果竞争、超时和失败收敛。
2. Cluster 的唯一 Helm 声明增加开发环境测试执行模板、隔离资源和网络边界，并验证所有 scope 的渲染差异。跨命名空间读取测试结果或共享控制器容量调整必须单独列明影响。
3. 共享 `.github` 为集中策略提供受信任的执行适配，保留三个仓库现有参数和准备步骤。
4. 用三个仓库的真实候选并行对照旧 CI，验证通过、故意失败、数据库集成测试实际执行、CGO/LFS、配置变化、控制器重启和源码过期场景。
5. 在新结果稳定回传后，逐仓更新必需检查规则并停用旧 Go Test 入口：Chat 的 `.github/workflows/test.yml`，UniAuth 与 open-platform 的 `.github/workflows/go-test.yml`。先核对实际 ruleset 和来源绑定，不能把 Actions 必需检查直接改名当作迁移。
6. 回滚时先恢复旧 GitHub Go Test 入口与必需检查规则，确认重新产生有效结果，再停止新执行器。其他 GitHub 检查与业务部署路径沿用既有契约。

执行器、DevPortal 独立协调及 Cluster 开发环境模板已上线并完成真实执行验收。三个仓库复用工作流的 `@main` 入口，集中停用同仓库 PR/main 的旧 Go Test job；fork PR 保留 Actions 路径并由 DevPortal 验证转述。Chat 和 open-platform 的必需检查改为 `Dev Portal / Go Test`，移除原 Actions 来源绑定；UniAuth 原本未要求 Go Test 必需检查，保持其现有门禁。其他检查、签名及评审规则保持原样。现存 UniAuth 专用发布校验不作为本次迁移的契约或依赖。

## 数据库版本核对

UniAuth 和 open-platform 都使用 PostgreSQL，并有真实数据库集成测试。旧 UniAuth PostgreSQL 17.11 例外源于 GoFrame pgsql v2.9.1 与 PostgreSQL 18 主键元数据的兼容问题；主分支已经升级到 v2.10.3，open-platform 主分支为 v2.10.0。集中策略统一到固定 digest 的 PostgreSQL 18.6。

两个仓库当前驱动包含同一主键元数据合并修复，无需再次升级业务依赖。UniAuth 本地 PostgreSQL 17/18 对照均曾出现 watcher 回调空指针（`psqlwatcher/watcher.go:655`），原生集群完整执行未复现；数据库降级不能解决该偶发问题。

## 原生执行验收（2026-10-11）

| 仓库 / 源码 | gotestsum 汇总 | 结果 |
| --- | --- | --- |
| Chat main `c01db210635ff156dfb1f5881529d7a566fee242` | 3030 tests，5 existing skips | exit 0，GitHub success |
| UniAuth main `837b0ed48b65932243b4abd710c2dd14e31655a1` | 714 tests，3 existing skips | exit 0，GitHub success |
| open-platform main `a23514fc301561209c5a2001d72717abe490e74f` | 213 tests，1 existing skip | exit 0，GitHub success |
| Chat PR #432 merge `6a0afe16f2929c02c7bfc86afac529b6f5725758` | 3018 tests，5 existing skips | exit 0，回传绑定完整 PR head |

跳过来自原有测试自身的环境守卫，沿用原 CI 开关，没有删减断言。另行完成 PostgreSQL 18 真实迁移 up/down 与版本恢复验证。成功出口要求预期数据库 Pod 实际完成、phase Succeeded 且 exit 0；没有实际执行、步骤全跳过或环境错误均不能记为完整通过。测试阶段已现场确认不挂载 GitHub 或 Kubernetes 令牌。

统一执行采用 [gotestsum 1.13.0](https://github.com/gotestyourself/gotestsum)，保留各仓库原有 go test 参数及准备步骤。DevPortal 全量 Go 测试与 CGO=0 生产构建通过，集中策略测试和 actionlint 通过。
