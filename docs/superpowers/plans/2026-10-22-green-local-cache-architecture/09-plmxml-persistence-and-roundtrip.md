# 09 PLMXML环境持久化与往返验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 将原生环境作为可追溯文件及依赖保存，证明恢复范围，避免结构投影重建丢失扩展内容。

**Architecture:** 保留现有精简Export与语义codec，新增独立原生环境保存profile，复用simulation环境文档/Artifact入口；原始字节与结构投影分离，业务清单绑定原生原件和依赖。

**Tech Stack:** 现有.NET COM适配器、Python环境Provider、Artifact、SQLite/受控本地暂存；采用原生支持的PLMXML/VF/VFZ，不手造私有格式。

**Spec:** [10环境保存](../../specs/2026-10-22-green-local-cache-architecture/10-plmxml-environment-persistence.md)；先读[官方文档调查](../../../architecture/green-local-cache/siemens-14.2-plmxml-research.md)。

## Global Constraints

继承[总计划](README.md)。原生活文档先精确重接；普通保存不复制JT，跨机长期归档需明确动作。保留原生原件，不能以结构codec往返声称完整无损；results.txt不透明保留，不自行解析为正式结果。

## Review Focus

1. 偏好是应用级且异常未恢复：T24串行作用域及finally。
2. 插入集合/默认当前态/延迟视图未保存：T24明确范围，T25逐项核对。
3. 静态冻结重开被动态规则替换：T25拒绝替换，保留精确引用。
4. 原生私有扩展被codec丢弃：T24原字节Artifact与结构投影分离。
5. results.txt缺失、越界引用或包过大：T24/T25不伪造完整性，不清FCC兜底。

### T24：保存能力探测、独立profile及环境版本

**Files:**
- Modify B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`、`PlmxmlExporter.cs`，保留旧接口与行为。
- Create B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/EnvironmentPersistence.cs`、`local-runtime/src/Ai00.Connector.Contracts/EnvironmentPersistenceContracts.cs`；tests `local-runtime/tests/Ai00.Connector.Tests/EnvironmentPersistenceTests.cs`。
- Modify B: `plugins/simulation/simulation_backend/capabilities/plmxml_environments.py`、`environment_documents.py`（同capabilities目录）、`data/workspace_repository.py`；新应用层`application/environment_persistence.py`、domain `environment_revision.py`。
- Test B: create `plugins/simulation/tests/test_environment_persistence.py`，extend`test_plmxml_environment_capabilities.py`、`test_plmxml_environment_codec.py`（同tests目录）。

**Interfaces:** `SaveEnvironmentAsync(DocSessionRef, EnvironmentSaveRequest, lease, CancellationToken) -> StagedEnvironment`；request固定profile、workspace_revision、model_sets、required_features、view_scope、static/configured_mode、late_view_policy和mutation_id。`commit_environment_revision(staged_artifact, dependencies, engineering_refs, expected_revision, mutation_id, context) -> EnvironmentRevisionRef`。原生产物路径仅ConnectorHost可见，云端接收Artifact引用不接收任意本地路径。

- [ ] 写`StructureExportOptionsRemainUnchanged`、`PreferenceRestoreOnCancelAndFailure`、`TwoDocumentSavesSharePreferenceLock`、`ModelSetScopeMustIncludeSelectedInsertions`、`GenerationChangeMarksSaveStale`、`UnknownSaveOutcomeNeedsReconciliation`。
- [ ] 写Python `test_native_bytes_not_regenerated_by_projection_codec`（含相机/切面/未知扩展fixture，存取字节摘要相同）、`test_partial_late_views_not_complete`、`test_clearance_dependency_is_opaque`、`test_path_escape_and_xxe_rejected`、`test_environment_commit_replay_and_cas`。
- [ ] `B> dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~EnvironmentPersistenceTests`；`B> python -B -m pytest -p no:cacheprovider plugins/simulation/tests/test_environment_persistence.py -q`；确认新增需求失败。
- [ ] 先做V7接口探测：查当前安装TypeLib/官方API，证明SaveAs/Export/options/enum和许可证；不凭现有`export(2, hierarchyIndex)`猜参数。保存偏好应用级则与T11进程调用锁协调；finally恢复。未获支持接口，标unsupported并限制范围，不改成任意GUI点击兜底。
- [ ] 实现structure_projection/environment/portable_archive三个显式档位；environment默认引用模型，保留当前/指定视图和选定插入集合，required feature不支持则拒绝或明确partial。ProductView-only固定base_structure_hash；迟载策略不隐式Ignore。ASCII生成文件名，业务显示名分开。
- [ ] 复用既有Artifact/环境Provider，不扩展结构codec去重建全部原生内容。原件、结构投影、业务manifest分开关联；新格式/媒体类型与大包限额通过真实契约升级，不把现有64MiB导出/读取上限一律放大。
- [ ] dependencies记录角色/原生引用/精确来源/Artifact/尺寸/摘要/状态；越界路径、未授权URL、XML外部实体拒绝；原生/VVI受支持解析与通用包相对路径解析不混用。未支持扩展的依赖扫描标unverified，不能宣称完整。
- [ ] 重跑新测试、既有`VisMockupExportPlmxmlTests`及三个环境Python测试文件。保存后上传成功但业务CAS失败保留暂存；请求重放返回同EnvironmentRevision，不覆盖旧环境。
- [ ] Commit：`feat(simulation): persist native scene originals and scoped dependencies`。文档来源/探测结果进证据，真实模型不进Git。

### T25：原生往返、优先重接及跨机依赖验证

**Files:**
- Create B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/EnvironmentRestoration.cs`、`local-runtime/tests/Ai00.Connector.Tests/EnvironmentRestorationTests.cs`。
- Modify B: `plugins/simulation/simulation_backend/application/live_document_identity.py`、`environment_materialization.py`（同application目录），复用T10映射；输出供T21引用的恢复证据，本任务不依赖T21实现。
- Modify F: `packages/sim-plugin/electron/document_session_coordinator.js`、`packages/sim-plugin/web/cad_sim/viewer_document_manager.js`；新增各自restore测试。
- Evidence B: `docs/superpowers/reports/green-cache-release-evidence/plmxml-roundtrip.json`及脱敏截图索引，原始模型/日志在隔离运行目录。

**Interfaces:** `RestoreEnvironmentAsync(EnvironmentRevisionRef, expectedTarget, mode, CancellationToken) -> RestoreReceipt`；`TryReconnect(expectedSession, expectedEngineeringRefs) -> ReconnectResult`。receipt区分业务manifest、依赖获取、native恢复、mapping四个状态；返回新的运行generation，不改变业务绑定身份。

- [ ] 写`LiveDocumentReconnectDoesNotOpenOrFetch`、`LostDocumentRebuildsHandlesNotBindings`、`StaticRestoreNeverSubstitutesLatest`、`MissingClearanceFileReportsPartial`、`DuplicateModelSetsRemainDistinct`、`OldHandlesRefusedAfterReopen`。
- [ ] `B> dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~EnvironmentRestorationTests`，先红；对应Node测试断言App重启先重连，未满足身份不默默接活动文档。
- [ ] 按精确业务引用检查活文档并重接；缺失才打开原生场景。几何来源通过T02已验证FCC/TC接口解析，不扫描/复制整个缓存，不通过重新绑定修复本机句柄变化。
- [ ] 在授权隔离原生副本准备两套模型（含重复件），保存/关闭该副本/重开；逐项核对结构、局部/全局变换、显隐、材质、当前相机、命名切面、标注、活动备选树；碰撞结果通过原生保存及重载验证，不外部解析results.txt。未覆盖特性逐项unverified。
- [ ] 测失去results文件、FCC已淘汰/TC离线、同名新文件、移动包目录、缺少模型和大小限制；普通场景不得变成latest或偷偷全量下载。明确归档测试才生成VFZ/依赖包，记录字节增长及容量限制。
- [ ] 测App/Connector分别重启保活文档无OpenDocument/下载，原生重开后旧handle拒绝且方案不变；测重置起始快照不会覆盖用户后来变化。记录save/native reopen/dependency fetch/map/upload/commit的独立耗时。
- [ ] 完成PE01–PE08逐项证据及必要VF回退测试；更新T21/T22的环境支持边界。未验证不能宣称完整环境恢复。
- [ ] Commit B/F：`test(simulation): verify scene roundtrip and warm document reconnection`。
