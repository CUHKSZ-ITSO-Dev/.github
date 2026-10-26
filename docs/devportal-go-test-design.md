# Go Test 磁盘不足回退

Chat、UniAuth、open-platform 保留业务仓库现有 Go Test workflow；所有改动集中在共享工作流和 DevPortal，业务入口不需要修改。原 Actions Go Test 是结果与门禁的唯一出口。

## 执行流程

共享工作流先按照集中策略进行范围判断，再在 GitHub runner 执行原来的完整测试。PR checkout 使用最后推送的 head，保留 race、LFS、CGO、生成文件校验和隔离数据库。普通断言失败、生成物漂移、网络错误及数据库初始化错误直接失败。

恢复缓存前按需清理未使用的 SDK，空间不足时执行深度清理（完整 SDK 清单、`/opt/hostedtoolcache` 保留 Go 工具链、无关预装 Docker 镜像），并在缓存恢复后、编译空间检查前再次执行；Go 缓存仅恢复编译产物、不恢复模块下载目录，不复用旧大型缓存键。清理后仍未达到编译空间阈值，或受控 shell 命令明确返回 ENOSPC / No space left on device / Disk quota exceeded 时，启动回退。预留少量 handoff 空间，磁盘错误后释放。

回退请求经 GitHub commit status 中转：GitHub-hosted runner 无法直连内网 DevPortal（公网 DNS 不解析内网域名，2026-10 从 runner 实测确认），GitHub API 是双方唯一共同可达的通道。Actions 在 run head SHA 上写 context `devportal/go-test-fallback` 的 pending 状态，description 前缀 `run <id> attempt <n>` 与 target_url 的 run/attempt 链接承载请求身份；DevPortal 在既有 30 秒 GitHub 轮询回路里扫描开放 PR head 与 main 上的最新状态，发现 pending 后沿用与原 HTTP 端点相同的校验（runID、run attempt、head SHA、运行状态、原业务入口和统一 Go Test workflow 引用），登记幂等 DevBuild，再把进度与终态写回同一 context。Actions 轮询同一 status 直到终态。该通道要求业务入口与共享 workflow 授予 `statuses: write`；写权限仅用于发出回退请求，DevPortal 的写回使用自身服务端凭据。内网 HTTP 端点保留给手动触发与诊断。

仅接受三个纳管仓库。DevPortal 只为正在运行的合法 Go Test run 执行该 run 的固定测试，不能指定其他执行镜像、命令或部署参数；伪造 status 需要仓库写权限，且仍须通过 run 校验，信任面与原方案等价。token 不入库、不写日志。

请求按仓库、runID、attempt 幂等，执行提交固定不变；重复轮询只返回同一 DevBuild 的状态。Actions 等待真实成功或失败，API 持续不可读、写入被拒或等待超时都使原检查失败；旧 attempt 迟到的回写不覆盖本 attempt 的判断，被更新 attempt 接管时本侧直接收敛。`Stale` / `Bypassed` 终态不回写，由 Actions 按「被新 attempt 取代」自行处理。也不自动补测已有开放 PR 或 main。

## DevPortal 执行器

继续复用成熟的 gotestsum 和现有 Argo WorkflowTemplate。每任务使用临时缓存与独立数据库，不恢复大型 Actions 缓存、不使用业务凭据。Go 1.27.2；PostgreSQL 18.6；Chat 使用固定 digest 的 SQL Server 2025。执行镜像固定为集中策略匹配的 digest，数据库版本与策略一致。

最多两个 Go Test 同时执行。排队留在 DevBuild，避免占满 Argo 全局 Workflow 名额。保留现有超时、资源限制、节点调度和日志保留策略。切换时取消旧的尚未开始的自动补测记录；已运行任务正常结束，历史证据保留。

## 验证与回滚

本地验证覆盖磁盘不足与普通测试失败的区分、同一 run 的幂等请求、非法凭据、错误 commit / attempt / workflow、终态结果和旧自动队列停用。上线后用原业务 workflow 验证 Actions 路径，并核对 DevPortal 按需 API、同 commit 的测试回执和原检查结果。

回滚共享工作流和 Portal 时保持配对发布：先部署带 status 轮询与写回的 Portal（旧 runner 直连请求对它无副作用，Portal 可先行），再合入带 `statuses: write` 的共享工作流与业务入口（发现侧先于请求侧上线即可工作；顺序颠倒则回退请求无人消费，Actions 等待超时失败）。仓库 required check 使用原 `Go Test / Go Test`（保留原 Actions integration 绑定）；UniAuth 沿用原有可选检查设置。三个删除业务 Go Test 入口的 PR 不再适用。
