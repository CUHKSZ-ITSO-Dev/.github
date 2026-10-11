# 统一 Go Test 执行器

执行器复用 gotestsum 1.13.0 和原有 `go test` 参数，输出控制台摘要、JUnit 和 Go JSON 报告。Argo Workflows 提供队列、临时数据库和执行生命周期；业务测试无需增加 Docker/Testcontainers 依赖。

唯一策略源是 `../ci-policy/policy.json`。修改后执行：

```sh
python3 actions/go-test-runtime/sync_policy.py ../DevPortal
python3 -m unittest discover -s actions/ci-policy
```

同步生成 DevPortal 的 `cmd/dev-portal/go_test_policy.json`，提交两个仓库的对应改动。镜像构建复制原始集中策略，控制器传入策略 SHA-256；不匹配时执行器返回环境错误，避免控制器与镜像采用不同的数据库或命令。

镜像通过 `go-test-runtime-image.yml` 复用现有镜像发布工作流，以提交 SHA 标记发布。Cluster 的开发环境单元使用不可变 digest 配置 `devPortal.goTest.image`；空值保持停用。

UniAuth 和 open-platform 均使用共享 PostgreSQL 18.6 基线。Chat 保留 SQL Server 2025、CGO 和 LFS；UniAuth 保留 race 和独立迁移库，open-platform 保留绑定集合数据库测试开关。所有数据库均为任务临时库。测试容器不挂载源码读取令牌或 Kubernetes 令牌。

数据库启动或策略版本不一致返回 125；业务准备命令和 Go Test 的退出码原样保留。控制器将环境错误和测试失败分别回传，不能把未完成执行记为通过。
