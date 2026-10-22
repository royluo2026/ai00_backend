# 08 冻结、联合比较与灰度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 形成可重现TG0/TG1工程上下文，联合比较工艺与模型，并提供有证据的迁移和回退。

**Architecture:** 复用既有workspace freeze saga，用不可变各域引用封存；ComparisonRevision隔离两套模型与对齐状态，原生环境由T24/T25保存恢复。

**Tech Stack:** 现有Python revision/freeze、Artifact、Connector和Electron；additive schema。

**Spec:** [05基线](../../specs/2026-10-22-green-local-cache-architecture/05-baselines-and-comparison.md)、[07验收](../../specs/2026-10-22-green-local-cache-architecture/07-migration-acceptance-and-governance.md)、[09多方案](../../specs/2026-10-22-green-local-cache-architecture/09-process-auto-revision-and-multi-model-binding.md)、[10环境](../../specs/2026-10-22-green-local-cache-architecture/10-plmxml-environment-persistence.md)。

## Global Constraints

继承[总计划](README.md)。基线冻结不覆盖；技术修订不以发布名代替；模型字节归档另立显式选择。冻结使用实际静态结构，不能重开成同名最新配置。

## Review Focus

跨域准备期间更新、同标签多次冻结、历史文件丢失、两个相同快照对比、老记录来源不足。T21–T23覆盖；允许带问题冻结必须保留问题与策略决定，不能客户端自己把unverified升为可信。

### T21：跨域引用准备与不可变基线提交

**Files:**
- Modify B: `plugins/simulation/simulation_backend/application/workspace_freeze.py`、`plugins/simulation/tests/test_workspace_freeze_saga.py`、`test_workspace_version_export.py`（同tests目录）。
- Create B: `plugins/simulation/simulation_backend/domain/baseline_manifest.py`、`plugins/simulation/tests/test_baseline_manifest.py`。

**Interfaces:** `prepare_baseline(request, context) -> PreparedBaseline`；`commit_baseline(prepared, expected_workspace_revision, mutation_id, context) -> BaselineRef`。manifest固定T03 process/scheme/modelsets、流程图布局版本、配置条件及实际解析、T24 EnvironmentRevision、知识/规则版本、completeness和parent。

- [ ] 写`test_published_label_does_not_follow_new_draft`、`test_same_label_cannot_overwrite_baseline`、`test_prepare_dependency_changes_prevent_commit`、`test_static_structure_required_for_reproducible_freeze`、`test_geometry_unavailable_distinct_from_manifest_missing`。
- [ ] `B> python -B -m pytest -p no:cacheprovider plugins/simulation/tests/test_baseline_manifest.py plugins/simulation/tests/test_workspace_freeze_saga.py -q`；新增行为先失败。
- [ ] 复用freeze saga和Artifact公共端口，各域分别准备/确认，不声称跨库原子事务。重复mutation返回同基线；同标签新冻结生成新身份。原生未保存改动明确保存或排除，不能假装已包含。
- [ ] 真实测试库注入准备后变更、Artifact上传后提交失败、提交响应丢失；验证旧TG0不可变、可靠结果保留可重试。T24/T25未过的环境完整性标unverified，不能宣称精确可复现。
- [ ] Commit：`feat(baseline): freeze exact process model binding and scene references`。

### T22：同文档多阶段对比及联合差异

**Files:**
- Create B: `plugins/simulation/simulation_backend/application/baseline_comparison.py`、`domain/comparison_revision.py`、`plugins/simulation/tests/test_baseline_comparison.py`。
- Modify B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/NativeModelSetMap.cs`（T10创建）和对应测试。
- Create F: `packages/sim-plugin/web/cad_sim/baseline_comparison.js`、`baseline_comparison.test.js`；接入`model_document_collection.js`及craft现有流程图投影。

**Interfaces:** `compare_baselines(left_ref, right_ref, correspondence_revision, alignment, algorithm_version, context) -> ComparisonRevision`，输出新增/删除/工程换版/表示/结构/位置/工艺/绑定/显示变化。对齐矩阵只属于比较场景，不能写回来源矩阵。

- [ ] 写`test_same_snapshot_two_sets_independent`、`test_alignment_does_not_change_baseline`、`test_same_name_not_identity_match`、`test_aux_geometry_not_engineering_addition`、`test_unconfirmed_mapping_stays_candidate`、`test_old_file_missing_does_not_substitute_latest`。
- [ ] `B> python -B -m pytest -p no:cacheprovider plugins/simulation/tests/test_baseline_comparison.py -q`；`F> node --test packages/sim-plugin/web/cad_sim/baseline_comparison.test.js`，先红再实现。
- [ ] 通过T09/T10打开精确左右集合；点击工序/原生实例按集合双向联动，重复关系显示候选集合。未知来源插入不纳入基线；旧工艺配新产品派生分析场景。
- [ ] 实机同文档TG0/TG1，用户旋转/插入/对齐，保存再重开（T25），核对两套实例、差异及业务绑定；不得默认走TC ProductView回存，因为混合装配有官方限制。
- [ ] Commit B/F：`feat(comparison): compare frozen process and model sets together`。

### T23：迁移、全链路验收及分阶段发布

**Files:**
- Create B: `backend/scripts/plan_green_cache_migration.py`、`backend/tests/test_green_cache_migration_plan.py`；`docs/superpowers/reports/green-cache-release-evidence/README.md`及脱敏结果清单。
- Modify B/F: 所属能力/消费者开关、所属域受治理迁移声明及指南；不在计划阶段创建假的注册快照。

**Interfaces:** `plan_migration(inventory, target_schema_version) -> MigrationPlan` 只读；输出分类、来源证据、不可迁移项与幂等标记。执行单独受治理，不能只读命令中暗写。

- [ ] 写`test_incomplete_provenance_not_invented`、`test_existing_attachments_and_original_bop_preserved`、`test_migration_replay_no_duplicates`、`test_rollback_keeps_new_results_and_baselines`。
- [ ] `B> python -B -m pytest -p no:cacheprovider backend/tests/test_green_cache_migration_plan.py -q`；先红。实现additive迁移计划，保留legacy投影兼容，旧运行任务按旧契约结束。
- [ ] 在已验证测试库副本完成备份/恢复演练、迁移两次/中断恢复；来源不足分类为待确认，不批量改生产。回退关闭消费者/新写路径，不破坏性降库或删除可靠结果。
- [ ] 按规格逐项记录AC01–AC18、AB01–AB08、PR01–PR08、PE01–PE08，映射实际测试、源commit、数据版本、原始输出；每项区分passed/failed/skipped/unverified。源码标签不移动。
- [ ] 实测两条耗时线：环境准备/重接/恢复（含TC/FCC与PLMXML分段）和逐工序原生/落盘/云端交付；流程图冷/热首屏另报。真实权限撤回、多人冲突、重启、磁盘满、离线均留证。
- [ ] 跑`backend/scripts/check_domain_change_governance.py`和`backend/scripts/audit_domain_boundaries.py`的仓库现有CLI（先读`--help`按实际参数执行），核对真实Catalog/Descriptor/Provider/消费者与签名。机器通过、人工批准、运行验证分列，不用文档审查代替批准。
- [ ] Commit B/F：`test(release): record cache architecture migration and acceptance`；先内部灰度再扩范围，未达标项明确阻止相应功能发布。
