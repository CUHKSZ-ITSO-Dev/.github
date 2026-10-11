# Go Test 磁盘不足回退

Chat、UniAuth、open-platform 保留业务仓库现有 Go Test workflow；所有改动集中在共享工作流和 DevPortal，业务入口不需要修改。原 Actions Go Test 是结果与门禁的唯一出口。

## 执行流程

共享工作流先按照集中策略进行范围判断，再在 GitHub runner 执行原来的完整测试。PR checkout 使用最后推送的 head，保留 race、LFS、CGO、生成文件校验和隔离数据库。普通断言失败、生成物漂移、网络错误及数据库初始化错误直接失败。

恢复缓存前按需清理未使用的 SDK，Go 缓存仅恢复编译产物、不恢复模块下载目录，不复用旧大型缓存键。清理后仍未达到编译空间阈值，或受控 shell 命令明确返回 ENOSPC / No space left on device / Disk quota exceeded 时，启动回退。预留少量 handoff 空间，磁盘错误后释放。

Actions 使用现有临时 contents:read token 请求 `POST /dev/api/v1/go-test/fallback`，不要求业务入口添加 OIDC 或写权限。DevPortal 向 GitHub 独立校验仓库读取凭据，并用服务端凭据核对 runID、run attempt、head SHA、运行状态、原业务入口和统一 Go Test workflow 引用。仅接受三个纳管仓库；token 不入库、不写日志。具有仓库读取权限的调用者仅能为正在运行的合法 Go Test run 请求该 run 的固定测试，不能指定其他执行镜像、命令或部署参数。

请求按仓库、runID、attempt 幂等，执行提交固定不变；重复轮询只返回同一 DevBuild 的状态。Actions 等待真实成功或失败，控制面持续不可用、拒绝请求或等待超时都使原检查失败。DevPortal 不额外回写独立 Go Test status，也不自动补测已有开放 PR 或 main。

## DevPortal 执行器

继续复用成熟的 gotestsum 和现有 Argo WorkflowTemplate。每任务使用临时缓存与独立数据库，不恢复大型 Actions 缓存、不使用业务凭据。Go 1.27.2；PostgreSQL 18.6；Chat 使用固定 digest 的 SQL Server 2025。执行镜像固定为集中策略匹配的 digest，数据库版本与策略一致。

最多两个 Go Test 同时执行。排队留在 DevBuild，避免占满 Argo 全局 Workflow 名额。保留现有超时、资源限制、节点调度和日志保留策略。切换时取消旧的尚未开始的自动补测记录；已运行任务正常结束，历史证据保留。

## 验证与回滚

本地验证覆盖磁盘不足与普通测试失败的区分、同一 run 的幂等请求、非法凭据、错误 commit / attempt / workflow、终态结果和旧自动队列停用。上线后用原业务 workflow 验证 Actions 路径，并核对 DevPortal 按需 API、同 commit 的测试回执和原检查结果。

回滚共享工作流和 Portal 时保持配对发布：先保证回退 API 可用，再恢复 Actions 优先入口。仓库 required check 使用原 `Go Test / Go Test`（保留原 Actions integration 绑定）；UniAuth 沿用原有可选检查设置。三个删除业务 Go Test 入口的 PR 不再适用。
