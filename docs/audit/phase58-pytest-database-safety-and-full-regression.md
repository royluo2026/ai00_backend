# Phase 58 — pytest 数据库安全与完整后端回归收口

日期：2026-08-06
分支：`codex/capability-wave-a`

## 目标

本阶段处理 Phase 57 完整回归暴露的测试基础设施风险和契约漂移，不扩大 Capability 范围，不启动 Task 13，不连接真实数据库。

## 实现

- 新增全局 pytest 安全默认值：测试收集阶段设置 `AI00_PYTEST_OFFLINE=1`。
- 未显式设置 `AI00_ALLOW_LIVE_DB_TESTS=1` 时，移除 Craft、Agent、Simulation、Device 和 DDL 领域数据库 URL，避免继承桌面保存凭据。
- Base 连接池在 pytest 离线模式下于读取应用数据库配置前直接停用；只有显式 live opt-in 才允许构造连接池。
- 新增安全契约测试，覆盖默认离线、离线时绝不构造连接池、显式 opt-in 才允许构造连接池。
- 修正 display-id 序列测试，使其与 OceanBase MySQL 的 `workmanship_display_id_counters.val` 权威列一致。
- 修正 BOP 线体历史响应测试，使其覆盖批次、状态、版本、线体、受影响条目和操作日志。
- 修正本体关系测试导入，使其指向 Craft 实际路由所有者，而非兼容模块。
- 修正 Schema mock，使 Base、Craft、Agent 插件加载器实际注册的连接别名全部被离线 mock。
- 将旧 PostgreSQL 多 schema 全文扫描替换为 AST 级 SQL 调用检查：扫描 Base 与插件路由真实 `execute/executemany` 参数，拒绝旧 `schema.table` 资格名。
- 将 VPPS 测试切换到 Craft 自有 `MySqlVppsOperationRepository`、`workmanship_bop_vpps_operations` 和当前 dist 插件资产路径；撤销测试按 MySQL 的 UPDATE + SELECT 两阶段行为验证。
- BOP 创建字段测试显式隔离权限检查，只验证该测试声明的字段默认值，不再依赖旧权限副作用顺序。

## 验证证据

- pytest 数据库安全：`3 passed`。
- Schema migration static + mock：`200 passed, 1 warning`。
- VPPS + Craft 所有权边界：`61 passed, 1 warning`。
- 完整后端离线套件：`575 passed, 3 warnings in 13.20s`。
- 完整套件运行期间未提供任何数据库 URL，Base 连接池由离线门槛停用；没有部署、Migration、push 或远端变更。

剩余 3 个 warning 均为既有测试维护项：

1. `backend/routers/ext_datasource.py` 使用即将在 Python 3.14 移除的 `ast.Num`。
2. `test_mysql_migration.py` 两个类级 fixture 使用 pytest 10 将移除的实例方法写法。

## 显式真实数据库测试协议

真实数据库测试必须在 pytest 启动前同时设置：

- `AI00_ALLOW_LIVE_DB_TESTS=1`
- 对应领域的 `AI00_*_DB_URL`
- 独立测试租户/数据库和可追踪执行授权

本阶段没有执行该协议。真实 OceanBase/OIS/JWT 验收仍属于 `SYS-001`，不得把离线回归当作生产验收。

## Task 13 门槛保持不变

以下四项检查仍只做库存，不注册正式校验或发布 Capability：

- `vpps.master_data`
- `vpps.parent`
- `vpps.hierarchy_prefix`
- `vpps.fastener_main_part`

必须先取得业务 Owner 批准的 source_ref、唯一 Owner、阈值、算法版本、Policy 版本及正例/反例/边界/历史回放证据。现有 rule4 ignore 仍不视为正式让步政策。

## 范围与安全声明

- 本阶段仅修改测试安全门槛、测试契约和 Base 测试启动保护。
- 没有新增或开放插件可调用 Capability。
- 没有移除 Knowledge 文档 ACL。
- 没有 push、部署或访问真实数据库。
