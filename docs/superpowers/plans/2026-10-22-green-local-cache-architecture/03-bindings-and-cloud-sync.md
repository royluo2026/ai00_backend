# 03 正式绑定与云端同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 从备选树编辑到 craft 正式关系、digital_model 反向查询和跨端可见形成可靠闭环，支持同工艺多配置方案。

**Architecture:** simulation 管编排／草稿，craft 在单事务保存方案关系与发件记录，digital_model 幂等维护反向投影；不前端连续三次保存、不复制绑定主表。

**Tech Stack:** 既有 Capability/Gateway、craft space/binding revisions、MySQL、轻量后台 outbox、Electron Renderer。

**Spec:** [08 绑定回传](../../specs/2026-10-22-green-local-cache-architecture/08-alternate-hierarchy-binding-and-cloud-sync.md)、[09 多方案](../../specs/2026-10-22-green-local-cache-architecture/09-process-auto-revision-and-multi-model-binding.md)。

## Global Constraints

继承 [总计划](README.md)。typed 资源身份与可选几何分开；原生句柄不能作正式端点；跨域消费经公共端口；未知来源留草稿；正式关系只有 craft 权威可写。

## Review Focus

工序 Fork 后误写源 BOP、无 JT 工具需求、重复提交及乱序撤销、权限撤回、同 A版多个方案被最近一次覆盖。T06/T07/T08 都必须有对应测试。

### T06：方案／绑定原子提交及工艺来源映射

**Files:**
- Create B: `plugins/craft/craft_backend/application/binding_schemes.py`、`data/binding_schemes.py`、`capabilities/binding_schemes.py`、`plugins/craft/tests/test_binding_scheme_commit.py`。
- Modify B: `plugins/craft/craft_backend/capabilities/__init__.py`、`data/bop_collaboration_mysql.py`、所属域 schema 声明；`plugins/simulation/simulation_backend/application/publish_plans.py` 只构造受治理提交，不直接写 craft。
- Extend B: `backend/domain_ports/engineering_context.py`，增加 typed binding mutation/result。

**Interfaces:** `commit_binding_scheme(*, context, process_snapshot: ProcessSnapshotRef, scheme_id: str|None, expected_revision: str|None, mutation_id: str, changes: list[dict]) -> {scheme_id, scheme_revision_id, process_snapshot, binding_refs, commit_sequence, projection_state}`。change 明确 `create/update/remove`、工艺／需求身份、`model_occurrence|resource` typed target、角色和证据；resource target 不强制有几何。真重复和合法多对象按业务约束区分。

- [ ] 写 `test_same_process_two_model_schemes_coexist`、`test_fork_source_maps_to_working_node_not_original`、`test_resource_without_geometry_is_valid`、`test_commit_and_outbox_are_atomic`、`test_stale_head_does_not_overwrite`、`test_same_mutation_replays_same_revision`。
- [ ] 加`test_gbop_reference_pins_library_and_version`、`test_temporary_code_not_authoritative_join`：同名/同临时编码不可自动连；标准库不足保留未解析草稿，不阻止无依赖的场景工作，不创建假标准编码。
- [ ] 跑新 pytest 文件看到预期需求失败；将 A/r8→M0/S1、A/r8→M1/S2 作为固定测试，断言 S1 不变、S2 新建，错误 scope 无写入。
- [ ] 复用现有 BOP binding/member revisions 和幂等账本；新 scheme 元数据引用固定技术快照；同事务记录关系、方案、变更序号、审计和 outbox。正式能力独立评审注册，前端不伪造 actor。
- [ ] 重跑新测试、既有 collaboration/fork 测试；在测试库注入 outbox 写失败，断言绑定事务未部分提交。不可变模型端点校验经公共查询契约；当前权限由所属服务核验。
- [ ] Commit：`feat(craft): commit versioned binding schemes atomically`。产出闭合 payload 和正式 receipt，供 T07/T08/T18 使用。

### T07：可靠传播、数模反向查询与读水位

**Files:**
- Create B: `plugins/craft/craft_backend/application/binding_outbox.py`、`data/binding_outbox.py`；`plugins/digital_model/digital_model_backend/application/binding_projection.py`、`data/binding_projection.py`；相应 `capabilities/binding_usage.py`。
- Tests B: `plugins/craft/tests/test_binding_outbox.py`、`plugins/digital_model/tests/test_binding_usage_projection.py`。
- Read-only reuse reference: `plugins/knowledge/knowledge_backend/infrastructure/domain_outbox.py`（复用模式，不跨域导入内部库）。

**Interfaces:** `dispatch_binding_events(limit:int) -> DispatchSummary`；`apply_binding_event(event, consumer_context) -> {event_id, aggregate_revision, watermark, duplicate}`；`get_binding_usage(target_ref, minimum_revision=None, context=...) -> {items, watermark, completeness}`。事件带 scheme／binding 修订、权威摘要和墓碑，不含票据。

- [ ] 写 `test_duplicate_event_no_duplicate_usage`、`test_older_event_cannot_revive_removed_binding`、`test_gap_requires_scoped_rebuild`、`test_same_revision_different_hash_rejected`、`test_minimum_revision_reads_authority_or_pending`、`test_usage_respects_current_craft_permissions`。
- [ ] 跑两组新 pytest 预期失败；实现 outbox 发件确认与消费投影事务，按事件 ID 去重、按 aggregate revision 更新，丢失时按 scope 重建。没有即时追平时返回 pending，不能空列表假装无绑定。
- [ ] 在测试库验证提交成功、consumer 宕掉、恢复重放、重复 ACK 和墓碑；断言 craft 关系不丢、digital_model 不创建新的几何版本。进程内缓存不能承担可靠账本。
- [ ] 重跑新测试和 `plugins/digital_model/tests/test_domain_completion.py`，检查反查授权、错误和审计契约。
- [ ] Commit：`feat(bindings): synchronize authoritative usage projections`。后台任务使用既有承载设施，不部署未经需要的消息系统。

### T08：备选树编辑、状态和明确方案选择

**Files:**
- Modify F: `packages/sim-plugin/web/cad_sim/cad_sim.js`、`model_document_collection.js`、相关页面 HTML。
- Create F: `binding_scheme_controller.js`、`binding_scheme_controller.test.js`、`binding_sync_status.js`、`binding_sync_status.test.js`（均在同 cad_sim 目录）。
- Modify F: `packages/core/electron/capability_client.js` 仅接入真实登记的新版本契约；原有确认规则保留。
- Modify B: `plugins/simulation/simulation_backend/capabilities/alternate_hierarchies.py`、`application/publish_plans.py` 的来源／草稿适配。

**Interfaces:** `createBindingSchemeController({readContext, invoke, persistDraft, readReceipt})` 提供 `stage(change) / submit() / refresh() / selectScheme(ref)`；状态区分 `local_draft, submitting, cloud_committed, projections_pending, synchronized, conflict, unresolved, outcome_unknown`。mutation_id 在首次提交前持久生成，超时不变。

- [ ] 写 Node 测试：placement 不冒充正式绑定；树改名不丢 process ref；未知模型保持 unresolved；多方案必须显式选择；提交超时查旧 mutation；切换 UI 不改运行任务；网页重开可读正式关系。
- [ ] `F> node --test packages/sim-plugin/web/cad_sim/binding_scheme_controller.test.js packages/sim-plugin/web/cad_sim/binding_sync_status.test.js`；先观察预期失败。
- [ ] 实现 controller 与最小 UI，复杂状态从 cad_sim.js 拆出；绑定角色明确，资源／零件 typed，云端 receipt 驱动成功状态。草稿本地可保存但不计为已同步。
- [ ] 重跑新测试、`model_document_collection.test.js`、`tree_cache_integration.test.js`；用两个测试客户端演练 AB01–AB08、PR01/PR06，读取相同 scheme revision 和反向关系，不用前端内存证明云端同步。
- [ ] Commit B/F：`feat(simulation): expose binding schemes and synchronization states`。回退保留草稿与正式关系，旧 placement 仍可浏览但不显示已发布绑定。
