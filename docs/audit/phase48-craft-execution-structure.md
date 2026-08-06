# Phase 48：Craft 执行结构、关联零件与工作包 Capability

日期：2026-08-06
实施分支：`codex/capability-wave-a`
前置提交：`3355b2f`

## 目标

落实 Capability 实施计划 Task 4：以同一个确定性结构服务提供正式执行结构、草稿预览、BOP 已关联零件和限定范围工作包，并保持现有 Simulation v1 消费兼容。

## 已实施 Capability

- `craft.bop.execution_structure.get@1`
- `craft.bop.execution_structure.preview@1`
- `craft.bop.linked_parts.get@1`
- `craft.bop.work_package.get@1`

四个 Capability 的用途、禁用场景、本体概念、effects 和 tags 分别声明；`linked_parts` 不再错误继承 `execution_structure` 的语义元数据。

## 结构服务

1. 从 Craft 自有的 BOP version、entry、entry link 与 PBOM part 表加载聚合，不调用 Router，不跨领域 JOIN。
2. 按父子层级、`sort_order`、GID 进行稳定排序；从同一父节点下的操作顺序生成显式 predecessor，规范化资源、零件、知识与规则引用。
3. 统一生成 nodes、operations、dependencies、conditions，并计算 canonical SHA-256；相同输入不受数据库返回顺序影响。
4. 正式 `get` 必须有 `published_at`，草稿调用会返回 `version_not_published`。
5. `preview` 强制 `expected_revision`，不匹配返回稳定 `revision_conflict`。
6. `work_package` 只接受 `line|station|role`，输出 bounded work items、parts、tools、fixtures、equipment requirements、knowledge refs 和 rule refs。
7. `linked_parts` 只报告 BOP 已显式关联的 PBOM part 及使用位置，不承担 PBOM 候选搜索。

## Simulation 兼容策略

新增公开语义类型 `CraftExecutionStructureV1`，但 v1 wire ID 暂时保持 `craft.execution-plan`。现有 `validate_execution_plan`、`seal_execution_plan` 和 Simulation pin/verify 逻辑继续可用；新输出增加 `official` 与结构字段，Hash 覆盖全部内容。Simulation 迁移后才能考虑升级 wire ID。

## Revision 基础与限制

新增 OceanBase MySQL 可重放迁移 `202608060001_craft_bop_revision.sql`，为 BOP version 增加 `revision BIGINT NOT NULL DEFAULT 1`；schema bootstrap 与 BOP version 读取投影同步更新。

该列目前只建立权威字段和读取门禁，既有 Router 的历史写路径尚未统一递增 revision。因此：

- 本阶段正式结构仍由 canonical content Hash 精确固定；
- 本阶段没有新增写 Capability，不会依靠未递增 revision 提交变更；
- Task 13 的 Capability 写事务必须原子递增 revision；
- Task 14 迁移完成前，legacy 写入口必须补 revision bump 或退役，否则不能宣称全系统乐观锁闭环完成。

## TDD 与验证证据

- 初始红灯：测试收集因 `bop_structure` 尚不存在而失败。
- 语义边界红灯：`linked_parts` 曾错误继承 `craft.execution_structure`，测试精确失败后已拆分元数据。
- Structure + Simulation：`11 passed in 0.35s`。
- Migration + OceanBase + BOP + Structure + Simulation + provider：`30 passed in 0.60s`。
- 未连接数据库，未执行迁移或部署。

## 文件范围

- `plugins/craft/craft_backend/services/execution_structure.py`
- `plugins/craft/craft_backend/capabilities/bop_structure.py`
- `plugins/craft/craft_backend/capabilities/__init__.py`
- `backend/contracts/craft_execution_plan_v1.py`
- `backend/contracts/__init__.py`
- `backend/db/migrations/202608060001_craft_bop_revision.sql`
- `backend/db/mysql_schema.sql`
- `plugins/craft/craft_backend/capabilities/bop_versions.py`
- `backend/tests/test_craft_execution_structure_capabilities.py`

## 远端状态

- 改动仅位于本地隔离 worktree。
- 未推送 Gitea、GitLab 或其他远端。
