# 04 外置原生协同与租约 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 用户自由使用外置 VisMockup，AI00 保留精确自动化，并能观察原生变化、暂停冲突。

**Architecture:** 显式文档会话＋集合映射＋变化水位＋唯一的本机原生调度；普通界面无长期占有，原生共享线程约束单独处理。

**Tech Stack:** .NET STA/Connector、现有 C++ window bridge、Electron trusted IPC。

**Spec:** [03 原生协同](../../specs/2026-10-22-green-local-cache-architecture/03-teamcenter-fcc-native-collaboration.md)、[04 自动化](../../specs/2026-10-22-green-local-cache-architecture/04-automation-capture-and-delivery.md)。

## Global Constraints

继承 [总计划](README.md)。依赖 T02 支持矩阵；精确接入不支持时不能退回 ActiveDocument、关闭其他实例或把测试结论标通过。

## Review Focus

PID 重用、两个集合相同节点键、事件丢失、多个 Connector 竞争、原生长调用阻塞另一文档，分别在 T09–T11 测试并保留运行证据。

### T09：外置会话和精确目标调用

**Files:**
- Create B: `local-runtime/src/Ai00.Connector.Contracts/DocSessionRef.cs`、`local-runtime/src/Ai00.Connector.Adapters.VisMockup/ExternalDocumentSession.cs`；tests `ExternalDocumentSessionTests.cs`。
- Modify B: `VisMockupConnection.cs`、`IVisMockupCom.cs`、`VisMockupAdapter.cs`、`NativeDocumentWindow.cs`（同 adapters 目录）。
- Modify F: `packages/core/electron/native/job_object/job_object.cc`、`packages/sim-plugin/electron/document_session_coordinator.js`、`vismockup_controller.js`、`packages/core/electron/viewer_interaction_client.js`。

**Interfaces:** `DocSessionRef` 包含设备、runtime、PID、启动身份、document identity、session generation；`ExternalDocumentSession.AttachAsync(DocSessionRef, CancellationToken)` 只连接该目标；`ExecuteAsync(DocSessionRef, ModelSetRef, operationId, JsonElement payload, fence, CancellationToken)` 先验证闭合操作 schema。不把此函数直接暴露为任意 COM 调用。

- [ ] 写 `WrongPidOrStartRefused`、`WindowReuseInvalidatesSession`、`SameSnapshotTwoSetsRemainSeparate`、`ExternalModeNeverHidesOrReparents`、`AppExitDoesNotCloseUserDocument`；Node 测外置模式不调用 native embed。
- [ ] `B> dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~ExternalDocumentSessionTests`；`F> node --test packages/sim-plugin/electron/document_session_coordinator.test.js packages/sim-plugin/electron/vismockup_controller.test.js`；先见预期需求失败。
- [ ] 增加显式模式 `external`，停止该模式下 HideOwnedWindows/SetParent 路径；保留现有内嵌回退但不能两模式同时操作同 view。明确 process ownership 与 document association 不同。
- [ ] 重跑新测试和既有 native embed 边界测试。真实原生测自由旋转、切页、App 重启、多文档定位；记录 UI 线程卡顿，不能仅凭窗口可见判断可交互。
- [ ] Commit B/F：`feat(native): support explicit external document sessions`。

### T10：双向变化、集合映射和事件缺口恢复

**Files:**
- Create B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/NativeDocumentChanges.cs`、`NativeModelSetMap.cs`；tests `NativeDocumentChangesTests.cs`、`NativeModelSetMapTests.cs`。
- Modify B: `application/live_document_identity.py`、`domain/live_hierarchy_sync.py`（位于 simulation_backend）、相关 read-only observation 契约。
- Modify F: `packages/sim-plugin/web/cad_sim/viewer_document_manager.js`、`model_document_collection.js`。

**Interfaces:** `ObserveChanges(DocSessionRef, afterSequence) -> ChangeBatch`，含 generation、sequence、origin、operation_id、kind、affected_sets、completeness；`ResolveMembers(session, set, occurrenceRefs) -> NativeTarget[]` 只返回该集合成员。Python `apply_native_observation(workspace_ref, observation, context)` 只生成工作差异。

- [ ] 测事件重复／缺口、own operation 回声不循环、未知来源插入不归 TG0、用户移动不改来源矩阵、几何辅助节点与业务实例分离；同 native key 不同集合不能合并。
- [ ] 跑两组新 .NET 测试及 `plugins/simulation/tests/test_live_hierarchy_sync.py`，观察预期失败后实现。
- [ ] 使用 T02 已验证事件；缺口标 stale 并限定范围对账，不能每次事件全树扫描。无事件 API 则按矩阵采用有预算的差异检查并明确能力状态。SQLite 候选映射必须带完整会话 fence。
- [ ] 重跑并真实插入、删除、移动、切换文档；核对 App 树变化和精确云端工作差异。原生变化不自动发布 craft 正式关系，不修改冻结模型。
- [ ] Commit B/F：`feat(native): synchronize scoped model changes without feedback loops`。

### T11：本机唯一调度、短期租约和控制语义

**Files:**
- Create B: `local-runtime/src/Ai00.Connector.AppHost/NativeDocumentScheduler.cs`；tests `NativeDocumentSchedulerTests.cs`。
- Modify B: `PlanExecutionWorker.cs`、`RuntimeSessionWorker.cs`、`plugins/simulation/simulation_backend/application/connector_runtime_sessions.py`、`data/connector_repository.py`。
- Modify F: `packages/sim-plugin/web/cad_sim/capture_workflow.js`。

**Interfaces:** `Acquire(session,set,task,permissions,expiresAt) -> lease(fence)`；`Submit(command,lease)`；`Pause(task)`；`Release(task,fence)`。原生进程级调用串行与文档级业务租约分离，多个本机 runtime 不能各自声称独占同一文档。

- [ ] 测旧 fence、租约到期、双 Connector、目标关闭、用户相关结构修改、暂停请求未生效、恢复不覆盖用户后来视角；另测另一文档不被业务全局锁禁用。
- [ ] 跑新 scheduler .NET 测试以及既有 `backend/tests/test_connector_execution_budget.py`、`capture_workflow.test.js`；先看到新增需求失败。
- [ ] 接入现有签名计划／runtime expiry，不无依据拉长预算；原生结果不明独立状态，暂停只阻止新步骤。UI 不把取消请求成功当原生已停。
- [ ] 故障注入心跳丢失、旧 worker 延迟回报、进程共享线程长调用，验证 fencing 和正确 UI 提示；若原生无法中断，明确等待边界，不强杀未知用户文档。
- [ ] Commit B/F：`feat(runtime): fence document automation and user handover`。这是 T18/T19 执行前置门。
