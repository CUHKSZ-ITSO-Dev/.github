# 单开发槽位迁移发布约定

本文定义 Chat 与 UniAuth 的 PR 标签开发服发布约定。实现由服务仓库的标签入口、组织 `.github` 的可复用工作流和 Cluster GitOps 共同完成。

## 状态模型

每个服务维护一个开发槽位状态：

```yaml
service: chat | uniauth
  mode: main | pr
active:
  kind: main | pr
  pr: <PR 编号或 null>
  sha: <镜像对应 commit>
  database: <实际数据库名>
  mainDatabase: <当前开发主库；可由已合并 PR 重分类而来>
  configDatabase: <Secret 中的原始数据库名，用于渲染运行时配置>
  migrationManifest: <按文件名排序的 up 文件+SHA-256 序列>
```

服务级 GitHub Actions 并发组串行化所有槽位操作；GitOps 内的 `prNumber` 是比较并交换条件，过期的关闭事件不会覆盖已激活的新 PR。

## PR 部署

1. 仅组织内 PR 在带 `auto-deploy-to-dev-server` 标签时可执行。
2. 固定服务级并发组串行执行；一个部署在完成数据库准备、迁移校验和应用切换前不得释放槽位。
3. 第一次部署：从当前开发主库创建 `*_pr_<number>`，使用 PR 镜像执行 `migrate up`。
4. 后续部署比较上次成功部署保存的 migration manifest：已执行迁移未变时继续 `migrate up`；已执行迁移被改写或删除时，从 main 基线重建该 PR 库后完整 `migrate up`。
5. 迁移 Job 失败（包括 dirty）会阻断同步；只有 Job 成功后才进入应用 Deployment 的同步波次并切换镜像和数据库连接。

自动化只能使用 `up` 和 `status`。`down`、`goto`、`force` 仅限人工故障处置。

## main 提升

合并后的 main 直接将当前 PR 数据库重分类为开发主库。关闭事件会针对 GitHub 给出的 `merge_commit_sha` 单独构建不可变的开发主镜像，并在构建成功后提升该镜像；因此 squash/rebase 合并也不会把 PR 头提交的镜像误当作 main。迁移 Job 会在同一同步中执行 `migrate up`，避免在 main 镜像尚未发布时回退到静态 Chart 基线。

未合并 PR 关闭或移除标签时，应用镜像和数据库一起切回开发主库。数据库清理采用独立的保留任务；保留窗口为七天，且绝不删除当前 `mainDatabase`。

## 物理约束

Chat 的 SQL Server 使用持久卷，PR 初始化通过 `COPY_ONLY BACKUP` + `RESTORE` 克隆主库。UniAuth 用 `pg_dump`/`pg_restore` 克隆主库。两者都不调用 golang-migrate 的 `down`、`goto` 或 `force`。
