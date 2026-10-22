# 02 身份与工艺自动修订 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 建立后续绑定、缓存、执行和基线共同消费的精确身份，并复用现有 BOP 不可变修订。

**Architecture:** 公共端口定义闭合引用；craft 在现有事务写内核自动形成技术快照；simulation/digital_model 保存固定配置与集合映射，不把原生句柄持久成工程身份。

**Tech Stack:** Python closed models、现有域 schema/compiler、MySQL 兼容事务、现有 revision kernel。

**Spec:** [01 身份](../../specs/2026-10-22-green-local-cache-architecture/01-identity-data-and-consistency.md)、[09 修订](../../specs/2026-10-22-green-local-cache-architecture/09-process-auto-revision-and-multi-model-binding.md)。

## Global Constraints

继承 [总计划](README.md)。业务标签不代替技术身份；发布后不可原地覆盖；布局／附件不无故改变工艺结构；不新增第二套可写 BOP。

## Review Focus

同名 A版内容不同、重复请求、无效保存产生空修订、布局误触发业务修订、重复实例跨集合混淆。

### T03：固定公共引用和所有权契约

**Files:**
- Create B: `backend/domain_ports/engineering_context.py`、`backend/tests/test_engineering_context_contracts.py`。
- Modify B: `backend/domain_ports/digital_model.py`、`plugins/craft/craft_backend/capabilities/contracts.py`、`plugins/simulation/simulation_backend/capabilities/contracts.py`。
- Schema: 更新所属域真实声明和生成的 ownership/schema 文件；入口先由 G0 清单定位，禁止直接改生成结果代替声明。

**Interfaces:** 新闭合模型：`ProcessSnapshotRef(repository_id, technical_revision_id, content_hash)`；`ConfiguredOccurrenceRef(source_system_id, model_id, model_version_id, model_snapshot_id, occurrence_key)`；`BindingSchemeRef(scheme_id, scheme_revision_id, process_snapshot, target_snapshot_ids)`；`ModelSetRef(model_set_id, model_snapshot_id, workspace_revision_id)`。哈希均为真实 `sha256:` 摘要；身份类型兼容实际持久 ID，不能把 UUID 和已有 GID 正则混用。

另定义`ModelSnapshotRef(model_snapshot_id, configuration_snapshot_id, content_hash, completeness)`，由T05持久化返回；原生生成契约使用同一schema语义，不把C#运行句柄塞进Python业务引用。标准工序/GBOP引用保留来源库、正式编码及版本，库不完善则unresolved，不以临时序号补造身份。

- [ ] 写 `test_same_label_different_revision_not_equal`、`test_occurrence_requires_snapshot_context`、`test_closed_refs_reject_runtime_handle_and_actor`；直接构造相同显示名不同快照的引用，断言不相等；缺少 snapshot／附带 native handle 或伪造 actor 拒绝。
- [ ] `B> python -B -m pytest -p no:cacheprovider backend/tests/test_engineering_context_contracts.py -q`；先见新模型不存在的需求失败。
- [ ] 实现端口模型和域内适配；旧 selector 继续读但 provenance incomplete，不自动生成假 UID。Schema 字段按该契约在所属域 additive 迁移，表所有者与真实主键保持一致。
- [ ] 重跑新测试及 `backend/tests/test_schema_compiler.py`、`backend/tests/test_schema_snapshot_diff.py`，验证字段归属与新旧契约边界，不连接生产。
- [ ] Commit：`feat(context): define versioned engineering references`；保存接口摘要给 T04–T23 消费，不任意改字段名。

### T04：有效保存自动修订，发布标签保持不可变

**Files:**
- Modify B: `plugins/craft/craft_backend/data/bop_repository_mysql_writes.py`、`bop_repository_mysql.py`、`plugins/craft/craft_backend/capabilities/bop_writes.py`、`bop_repositories.py`。
- Create B: `plugins/craft/craft_backend/application/process_revisions.py`、`plugins/craft/tests/test_process_auto_revision.py`；必要受治理 schema 声明。
- Modify F: `packages/craft-plugin/web/lineage_view/lineage_projection_store.js`，新增 `process_revision_badge.js` 和 `.test.js`。

**Interfaces:** `save_process_change(*, context, space_id, expected_revision, mutation_id, commands) -> {technical_revision_id, parent_revision_id, content_hash, changed, release_ref, commit_sequence}`。复用已有 node/member revisions 与 `save_space_version` 语义，在一次写事务内形成可固定快照；legacy 写能力适配到同一内核，不能桌面支持而网页仍覆盖旧内容。

- [ ] 写 `test_save_without_manual_release_creates_revision`、`test_replay_and_noop_do_not_create_revision`、`test_published_a_remains_r8`、`test_layout_and_attachment_not_process_structure_change`、`test_legacy_and_managed_writes_share_revision_semantics`。
- [ ] `B> python -B -m pytest -p no:cacheprovider plugins/craft/tests/test_process_auto_revision.py -q`；预期现有保存未自动形成快照／适配不完整而失败。
- [ ] 在 existing transaction/CAS/idempotency 内实现；发布 A/r8 后下一内容修改派生草稿 r9，返回“基于 A版 · 未发布修订”，不重指发布记录。无语义变化返回 changed=false。保留传统 BOP 的显式来源适配和风险标记。
- [ ] 重跑新测试及 `plugins/craft/tests/test_bop_repository_data.py`、`test_bop_collaboration.py`；在测试库做重复请求、两个连接并发 CAS、事务中途失败验证，不以 mock 代替事务证据。
- [ ] `F> node --test packages/craft-plugin/web/lineage_view/process_revision_badge.test.js`；断言草稿不能显示为已发布 A版。
- [ ] Commit B/F：`feat(craft): persist automatic technical revisions`，记录成对提交及 API 兼容结果。

### T05：配置快照与模型集合持久化

**Files:**
- Create B: `plugins/simulation/simulation_backend/domain/configuration_snapshot.py`、`application/configuration_snapshots.py`、`data/configuration_repository.py`；tests `plugins/simulation/tests/test_configuration_snapshots.py`。
- Modify B: `application/cache_preparation.py`、`capabilities/environment_documents.py`、`data/workspace_repository.py`。
- Modify B: `plugins/digital_model/digital_model_backend/capabilities/models.py` 的公共引用适配，保留不可变模型版本。

**Interfaces:** `resolve_configuration_snapshot(spec, context) -> ModelSnapshotRef`；`add_model_set(workspace_id, expected_revision, snapshot_ref, mutation_id, context) -> ModelSetRef`。条件包括规则身份／可得定义摘要、变量顺序、日期、布局、来源；快照记录完整性与一致性证据。模型集合可同快照插入两次。

- [ ] 写 `test_same_rule_name_new_definition_new_snapshot`、`test_two_sets_of_same_snapshot_are_distinct`、`test_missing_matrix_not_repaired_as_identity`、`test_aux_geometry_not_business_occurrence`、`test_cache_eviction_preserves_snapshot`。
- [ ] 跑新 pytest 文件观察需求失败；实现不可变快照、集合命名空间和局部/来源/场景变换分离。算法标识参与内容规范化；不按 JT 内容哈希扫描整车来生成身份。
- [ ] 重跑配置测试及既有 alternate hierarchy／workspace cache revision 测试。T01 一致性探测未通过时只允许带 unverified 的工作快照，不开放正式一致性声明。
- [ ] 用 T01 的同一配置验证结构读与原生打开来源一致；数据库清理缓存记录后，业务 snapshot/set 仍在且绑定引用不变。
- [ ] Commit：`feat(simulation): persist configured snapshots and model sets`。T06 只能消费端口引用，不能跨库直接读新表。
