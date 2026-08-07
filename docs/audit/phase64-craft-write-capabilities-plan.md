# Phase 64 — Task 13A 安全写入实施计划

日期：2026-08-07
分支：`codex/capability-wave-a`
范围：CRAFT-004/005；不包含 validate、publish、VPPS、waiver、物理删除。

## 决策

本批将把 BOP 写入收敛为类型化 Craft Capability，不直接暴露旧 router 的通用 CRUD、字段路径、JSON Patch 或 SQL。旧 router 保留兼容，不作为新 Capability 的实现边界。

## 能力清单

| Capability | 语义 | 副作用 |
| --- | --- | --- |
| `craft.bop.draft.change.preview` | 校验并生成绑定精确版本/修订/Hash/过期时间的变更预览 | 无 |
| `craft.bop.draft.change.apply` | 消费一次性预览并在单事务内应用类型化变更 | 写入 entry/link/version 元数据并递增 revision |
| `craft.bop.version.create` | 从 empty、bop_version、template 或 import_preview 创建草稿 | 创建版本；来源快照不变 |
| `craft.bop.version.archive` | 非破坏归档指定版本 | 仅更新归档状态，不删除内容 |
| `craft.bop.import.preview` | 解析并校验受限导入文档，返回稳定 Hash/摘要 | 无 |

## 不变量

- 身份、tenant、权限只来自 `CapabilityContext`；payload 不能覆盖。
- 变更仅允许显式操作：`entry.create`、`entry.update`、`entry.archive`、`link.attach`、`link.detach`、`version.metadata.update`；拒绝任意 JSON Patch、SQL、字段路径和模糊 command。
- Preview 绑定 `version_gid`、当前 revision、canonical payload Hash、before Hash、after Hash 和 TTL；apply 必须检查 expected revision、preview 未过期、幂等键和一次性确认。
- Apply 在一个数据库事务中完成；失败回滚，不产生半成品 revision。成功时 revision 原子递增，并写入不可变审计记录。
- Archive 只允许非发布草稿/基线按明确状态机转换为 archived；不提供物理删除，内容 Hash 和引用保持不变。
- Create 的 source 只能是 `empty|bop_version|template|import_preview`；clone/fork 不另建 Capability。`import_preview` 只能消费同一调用链产生且未过期的预览。
- Import preview 不写业务表，不执行领域发布校验；VPPS 规则仍为候选待办。

## 实施顺序

1. 先写纯函数/内存仓储契约测试，观察 RED。
2. 实现 canonical JSON、Hash、预览 TTL、类型化命令解析与冲突错误。
3. 接入 Craft Repository；补充 OceanBase MySQL migration（仅 Craft 表/列），不在运行时 DDL。
4. 注册能力，保持 `plugin_callable=false`，加入 agreed catalog 和审计矩阵。
5. 执行聚合离线回归、OceanBase 静态审计和领域边界守卫；不连接数据库。

## 验收证据

- RED/GREEN 测试记录在 `backend/tests/test_craft_write_capabilities.py`。
- 代码审查可看到 no-op preview、expected revision、Hash/TTL、幂等、一次性确认、事务 rollback、before/after Hash、archive 非破坏和 import 无副作用。
- 本文与 `SYSTEM_OPTIMIZATION_BACKLOG.md`/Phase 63 保持一致。

## 2026-08-07 实施进展

Phase 64 已完成离线安全写入代码与契约测试首轮：

- 新增 `craft.bop.draft.change.preview/apply`、`craft.bop.version.create/archive`、`craft.bop.import.preview`。
- 变更只接受类型化命令：`entry.create/update/archive`、`link.attach/detach`、`version.metadata.update`；拒绝 JSON Patch、SQL 和模糊 command。
- Preview 绑定版本、expected revision、canonical payload Hash、before/after Hash 和 5 分钟 TTL；Apply 检查一次性确认、修订冲突和幂等键。
- Create 只接受 `empty|bop_version|template|import_preview` 来源；不另建 clone/fork Capability。
- Archive 仅改变状态并递增 revision，保留 entry/link 内容 Hash；不提供物理删除。
- Import preview 不修改业务版本表；应用必须通过受治理 create/change 能力完成。
- 新增 Craft migration `202608070001_craft_bop_write_governance.sql`，用于预览、幂等和导入预览持久化；运行时不执行 DDL。
- 新增能力保持 `plugin_callable=false`，暂缓的 validate/publish/VPPS 能力未注册。

离线证据：

- `backend/tests/test_craft_write_capabilities.py`：7 passed。
- 写能力 + Kernel + Catalog + migration 相关聚合：247 passed in 6.17s。
- `backend/scripts/oceanbase_compatibility_audit.py`：通过。
- 未连接 OceanBase/OIS/JWT，未部署，未 push。

尚未宣称生产完成：真实数据库事务实现、预览/幂等/审计持久化烟测、真实 JWT/权限和 E2E 仍待授权测试环境；因此 CRAFT-004/005 保持实施中/待验证。
