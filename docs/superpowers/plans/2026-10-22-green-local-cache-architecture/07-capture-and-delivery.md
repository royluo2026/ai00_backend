# 07 本地连续截图与云端交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task; subagents only when explicitly selected. Steps use checkbox (`- [ ]`) tracking.

**Goal:** 固定一次截图计划，在本地连续产出可靠PNG，并行完成可恢复上传与条件回填。

**Architecture:** 云端固定业务依赖，本机调度原生步骤，现有SQLite CaptureDeliveryQueue承接可靠结果；craft权威挂图，UI仅显示真实回执，不阻塞流水。

**Tech Stack:** 现有Python能力、.NET Connector/STA、Microsoft.Data.Sqlite、Artifact上传、Electron事件。

**Spec:** [04截图](../../specs/2026-10-22-green-local-cache-architecture/04-automation-capture-and-delivery.md)、[08绑定](../../specs/2026-10-22-green-local-cache-architecture/08-alternate-hierarchy-binding-and-cloud-sync.md)、[10环境](../../specs/2026-10-22-green-local-cache-architecture/10-plmxml-environment-persistence.md)。

## Global Constraints

继承[总计划](README.md)。保留正式权限、版本、幂等与审计；不逐工序重新查询“下一动作”，不逐工序导出PLMXML，不重复准备已就绪环境。主指标是原生到可靠落盘p95≤5秒目标，云端交付另报；不以跳过/减少采样冒充性能。

## Review Focus

同件多次工艺使用、重复插入集合、原生超时但PNG已经落盘、磁盘满/网络慢、需求改变后旧图片到达。分别由T18–T20锁定行为；热路径必须保留相关fence检查。

### T18：一次编译稳定顺序与精确依赖

**Files:**
- Create B: `plugins/simulation/simulation_backend/application/capture_plan_compiler.py`、`plugins/simulation/tests/test_capture_plan_compiler.py`。
- Modify B: `plugins/simulation/simulation_backend/application/capture_worker.py`、`connector_plans.py`（同application目录）；C#闭合计划契约位于`local-runtime/src/Ai00.Connector.Contracts/`，由G0核实现有签名版本并兼容扩展，不发明未经登记的operation ID。

**Interfaces:** `compile_capture_plan(process_snapshot, scheme_ref, model_set_ref, policy, context) -> CapturePlan`；计划固定run_id、输入版本/摘要、顺序、per-step process/requirement/occurrence refs、目标实例、跳过原因、预算和capture_policy_version。运行顺序号仅本轮有效。

- [ ] 写`test_reverse_order_ignores_ui_layout`、`test_missing_geometry_skips_once`、`test_repeated_part_uses_explicit_policy`、`test_scheme_requires_exact_process_and_model`、`test_same_snapshot_two_sets_no_cross_target`；分别断言固定倒序、一次跳过不循环、重复绑定由策略处理而非误隐藏、错方案拒绝、集合隔离。
- [ ] `B> python -B -m pytest -p no:cacheprovider plugins/simulation/tests/test_capture_plan_compiler.py -q`；预期新增需求失败。
- [ ] 通过craft/digital_model公开端口读取一次固定快照，复用T03引用与T06正式方案；不跨域读私表。签名计划承载完整顺序，批量权限仍依据真实契约，不迁入演示绕过项。
- [ ] 重跑新测试及现有Connector计划测试；对测试库工艺真实编译并核对每步所属工位/工序/实例，源变化派生新计划，不修改已开始计划。
- [ ] Commit：`feat(capture): compile immutable ordered capture plans`。

### T19：本机连续原生循环和控制

**Files:**
- Create B: `local-runtime/src/Ai00.Connector.AppHost/CaptureRunExecutor.cs`、`local-runtime/tests/Ai00.Connector.Tests/CaptureRunExecutorTests.cs`。
- Modify B: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/ReverseCaptureRenderer.cs`、`SceneController.cs`（同目录）；`local-runtime/src/Ai00.Connector.AppHost/PlanExecutionWorker.cs`。
- Modify F: `packages/sim-plugin/web/cad_sim/capture_workflow.js`、`capture_workflow.test.js`。

**Interfaces:** `ExecuteRunAsync(CapturePlan, DocSessionRef, lease, CancellationToken) -> RunReceipt`，使用T11调度入口；发送run/step/phase/sequence事件。每步可执行前仅验证相关会话与依赖fence，初始化底色/范围一次；image durable后按明确策略隐藏并进入下一步。

- [ ] 写`NextStepNeedsNoCloudRoundTrip`、`BaseColorAppliedOncePerRun`、`PauseStopsNewNativeSteps`、`ExpiredFenceCannotContinue`、`UnknownOutcomeIsNotRecapturedBlindly`、`ResetDoesNotOverwriteLaterUserView`。模拟上传阻塞时断言允许在队列预算内继续原生截图。
- [ ] `B> dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~CaptureRunExecutorTests`；先观察行为失败。
- [ ] 复用已有renderer，不重建全套截图器。状态区分native_running/image_durable/skipped/outcome_unknown；暂停在原生步骤边界生效，停止保留结果。重置仅条件恢复本轮状态，不能删除整线历史附件。
- [ ] 重跑`ReverseCaptureRendererTests`和`CaptureRunExecutorTests`；`F> node --test packages/sim-plugin/web/cad_sim/capture_workflow.test.js`。真实原生精确文档测试同快照两集合、用户操作冲突及重启重接，保持外置窗口可用；不借外部未知文档测试。
- [ ] 在稳定准备后至少30个可执行工序样本（不足则明确样本不足，不能假报p95），记录本地排队/展示/原生截图/可靠落盘p50/p95、失败和跳过率；环境冷准备另列。目标未达给分段证据。
- [ ] Commit B/F：`feat(capture): execute continuous fenced native capture runs`。

### T20：可靠PNG、上传队列与craft条件回填

**Files:**
- Modify B: `local-runtime/src/Ai00.Connector.AppHost/CaptureDeliveryQueue.cs`、`AppCaptureUploader.cs`；tests `local-runtime/tests/Ai00.Connector.Tests/CaptureDeliveryQueueTests.cs`。
- Create B: `plugins/craft/craft_backend/application/capture_attachments.py`、`plugins/craft/tests/test_capture_attachment_delivery.py`，适配所属既有挂图Provider和事务；具体登记走G0，不新建第二份附件库。
- Modify F: `packages/craft-plugin/web/lineage_view/lineage_projection_store.js`和相应图片投影测试，仅消费真实回执。

**Interfaces:** 队列扩展保存T03精确工艺/方案/模型引用，兼容旧CaptureDeliveryScope记录。`attach_capture_result(artifact_ref, process_ref, slot_id, dependency_fingerprint, expected_attachment_revision, mutation_id, context) -> AttachmentReceipt`；receipt固定关系身份与实际修订。`RecordAttached`只记录真实craft回执，不能本机自授成功。

- [ ] 测PNG原子重命名后崩溃但队列未写、上传/挂接成功响应丢失、同请求不同摘要拒绝、权限撤回、工序/绑定变更冲突、冻结版拒绝原地修改、同文件两队列不重复挂接、磁盘满时不删待交付/历史图片。
- [ ] `B> dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~CaptureDeliveryQueueTests`；`B> python -B -m pytest -p no:cacheprovider plugins/craft/tests/test_capture_attachment_delivery.py -q`；新需求先红。
- [ ] 复用现有WAL/FULL SQLite和512MiB缺省pending byte预算，不为重构复制第二队列；增加条数上限配置、启动文件对账、重试查询和有界上传并发。测试用小预算触发背压；实际上限经设备测量记录后调整，不无界提速。
- [ ] craft事务校验精确工序/槽/相关依赖和CAS，保留原始BOP图片，写审计/幂等结果；冲突保留PNG。上传短期凭据不入SQLite、日志和环境包。
- [ ] 真实测试闭环：原生PNG→核对PNG内容与尺寸→Artifact可读→craft关系与版本→前端卡片按真实回执加载→中断恢复→有条件撤回本轮关联。AC05/06/12/14有证据，不能仅看UI缩略图判定成功。
- [ ] Commit B/F：`feat(capture): resume durable delivery and conditional craft attachments`。
