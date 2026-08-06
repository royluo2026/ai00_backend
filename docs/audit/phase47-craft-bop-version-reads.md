# Phase 47：Craft BOP 版本读取 Capability

日期：2026-08-06
实施分支：`codex/capability-wave-a`
前置提交：`1bc26df`

## 目标

落实 Capability 实施计划 Task 3，建立首个真实 Craft 垂直切片：`craft.bop.version.get@1` 与 `craft.bop.version.list@1`。

## 已实施内容

1. `get` 使用精确 `version_gid` 读取 BOP 版本，返回版本身份、版本族/项目引用、生命周期、revision、内容 Hash（存在时）及 EvidenceRef。
2. `list` 支持 `project_gid`、`status`、`query`、`include_archived`、`cursor`、`page_size`；只返回摘要，page size 强制为 1–100。
3. 列表采用 `created_at + gid` keyset cursor，不使用大 offset；cursor 是不透明 URL-safe Base64 JSON。
4. 两个读取能力的 `permissions=()`，因此所有已认证用户可读全部 BOP 版本；没有项目成员或负责人过滤。
5. handler 直接使用 Craft 数据连接与 repository SQL，不调用 Router 函数。
6. SQL 只访问 `workmanship_bop_bop_versions`，使用 `%s` 参数，不包含 PostgreSQL schema qualifier、`RETURNING` 或 `::` cast。
7. Craft provider 开始注册这两个正式 Capability；基座仍不导入 Craft 模块。

## Revision 现状与后续门禁

当前表没有独立的权威整数 revision 列。读取投影按 `meta.revision -> version_no -> version_tag` 的优先级返回现有版本标识，保证不虚构数据库中不存在的值。Task 4 的 `expected_revision` 和后续写入乐观锁不能继续依赖这个兼容投影；进入结构 preview/apply 前必须新增并迁移权威单调 revision，或冻结一个等价且可原子校验的版本令牌契约。

## TDD 与验证证据

- 初始红灯：测试收集因 `capabilities.bop_versions` 不存在而失败。
- 聚焦测试：`6 passed in 0.30s`。
- BOP、OceanBase、provider、Kernel 与领域治理联合回归：`26 passed in 1.20s`。
- 未连接数据库，未执行 SQL、迁移或部署。

## 文件范围

- `plugins/craft/craft_backend/capabilities/bop_versions.py`
- `plugins/craft/craft_backend/capabilities/__init__.py`
- `backend/tests/test_craft_bop_version_capabilities.py`

## 远端状态

- 改动仅位于本地隔离 worktree。
- 未推送 Gitea、GitLab 或其他远端。
