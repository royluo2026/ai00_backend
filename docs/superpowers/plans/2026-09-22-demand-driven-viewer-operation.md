# Demand-Driven Viewer Operation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户切换仿真环境后直接点击显隐/高亮；系统复用精确的现有 VisMockup 运行文档，缺失时只打开一次，并在完成关联和内嵌后自动执行原操作。

**Architecture:** Connector 用活动文档双读和 `WM_MDIGETACTIVE` 建立、激活精确文档窗口，不再修改窗口标题。Electron 持有按工作区/文档划分的运行槽及授权会话；页面提交绝对状态操作意图，先尝试激活槽，槽不存在才复用现有 launch@2 → bind@3 → attach 流程。热操作继续走本地命名管道。

**Tech Stack:** .NET 8/C# COM STA + Win32 MDI, Electron/CommonJS + N-API, browser JavaScript/JSDOM, Python Capability Provider/PyMySQL, existing Node/.NET/pytest harnesses.

**Spec:** `docs/superpowers/specs/2026-09-22-demand-driven-viewer-operation-design.md`

## Global Constraints

- 选择环境不打开模型；第一次模型操作才允许隐式打开。
- 不按 PID、文件名、显示名称或历史绑定猜测窗口；目标必须由本次受控运行证据建立。
- 页面不得接收或提供授权、PID、HWND、window token、COM handle。
- 复用 `simulation.teamcenter.visualization.launch.request@2`、`simulation.environment.online_source.live_document.bind@3`、`simulation.viewer.interaction.authorize@1`；本期不新增 Capability、不改 schema、不迁移数据库。
- 已派发写操作出现未知结果时不自动重放，不切换旧云路径重发。
- 不预扫整车；节点仅按目标 occurrence path 有界解析。
- 不关闭其他 VisMockup 文档，不打开整车；真实验证仅用诊断螺栓和用户明确允许的局部装配。
- 当前 B/F worktree 都在 `test`，保留既有未提交修改。提交或推送仍需用户在执行阶段明确授权。
- 正式 `machine_passed`、`human_approved`、`runtime_verified` 独立报告；AI 结论仅 advisory。

## File Structure

- B `local-runtime/src/Ai00.Connector.Adapters.VisMockup/NativeDocumentWindow.cs`: Win32 活动 MDI 捕获、marker 校验和激活。
- B `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`: 文档通过应用活动句柄回读建立/激活窗口。
- B `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`: 多文档 prepared-target 缓存及激活入口。
- B `local-runtime/src/Ai00.Connector.AppHost/ViewerInteractionProtocol.cs`、`ViewerInteractionPipeHost.cs`: 关闭的 `activate_document` 本地协议。
- F `packages/core/electron/viewer_runtime_slots.js`: 每个工作区文档的 Main-owned 运行槽与活动槽切换；新建，避免继续膨胀 client。
- F `packages/core/electron/viewer_interaction_client.js`: 复用授权/prepare/attach/execute，并把会话交给槽管理器。
- F `packages/sim-plugin/web/cad_sim/viewer_interaction.js`: 页面 single-flight ensure、绝对状态意图合并。
- F `packages/sim-plugin/web/cad_sim/live_document_bootstrap.js`、`live_document_adoption.js`、`cad_sim.js`: 模型树点击接入按需流程和状态展示。
- B/F 既有测试与 native MDI harness：覆盖窗口竞争、槽复用、首次点击、未知结果及治理边界。

## Review Focus

1. VisMockup 打开期间用户手动切换文档：活动句柄 A/B 不一致必须拒绝，不能绑定切换后的窗口（Task 1）。
2. 同一文档首次显隐并发，或打开响应丢失：只允许一个 launch 幂等键，不能产生重复窗口（Task 3、4）。
3. 环境 A/B 快速切换且窗口同名：必须激活各自 marker/HWND，操作不能落到另一个文档（Task 1、3）。
4. 页面刷新或 renderer 崩溃而 Main/Connector 仍活着：旧页面会话失效，新页面只能重新授权后复用本地目标（Task 3）。
5. COM 写已派发后管道超时：槽进入 `outcome_unknown`，后续点击和旧云路径都不得重发（Task 3、4）。

---

### Task 1: Replace title challenge with exact active-MDI capture

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/NativeDocumentWindow.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/ViewerDocumentPreparationTests.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/FakeVisMockupCom.cs`
- Modify: `scripts/mdi_selector_native_test.cc`

**Interfaces:**
- Consumes: exact process ID/start ticks and COM document handle already used to compute `document_session`.
- Produces: `NativeDocumentWindow.CaptureActive(int pid, string expectedDocumentId, Func<string> activeDocumentId, NativeDocumentWindow? previous)` and `NativeDocumentWindow.Activate(int pid, string expectedDocumentId, Func<string> activeDocumentId, NativeDocumentWindow target)`.

- [ ] **Step 1: Replace title-mutation tests with failing active-document sandwich tests**

Add separate tests proving stable A/MDI-A/A succeeds and A/MDI-B/B, A/MDI-A/B, multiple active MDI containers, foreign PID, missing/replaced marker, and HWND reuse reject. Expose only narrow internal decision seams for tests; do not add a public abstraction solely for mocks.

```csharp
var target = Capture(pid:123, before:"doc-A", mdiActive:windowA, after:"doc-A");
Assert.Equal(windowA.ToInt64().ToString(), target.DocumentWindow);
Assert.Throws<ConnectorNoEffectException>(() =>
    Capture(pid:123, before:"doc-A", mdiActive:windowB, after:"doc-B"));
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~ViewerDocumentPreparationTests --no-restore --verbosity quiet -p:UseSharedCompilation=false -m:1
```

Expected: failures because `CaptureActive`/`Activate` do not exist and title-challenge assertions describe the obsolete behavior.

- [ ] **Step 3: Implement the minimal active-MDI capture**

Enumerate top-level windows for the exact PID, then direct `MDIClient` children. Read one active child with `SendMessageTimeout(WM_MDIGETACTIVE)` and enforce the sandwich:

```csharp
var before = activeDocumentId();
var candidate = UniqueActiveMdiChild(pid);
var after = activeDocumentId();
if (before != expectedDocumentId || after != expectedDocumentId)
    throw new ConnectorNoEffectException("document_session_changed");
if (!OwnedDocument(candidate, pid))
    throw new ConnectorException("vismockup_document_window_unavailable");
return Mark(candidate);
```

If `previous` still has exact PID/MDI parent/property token, return it only after the same active-document sandwich. Remove production dependency on `View.Title` get/set. Keep marker generation cryptographically random and positive.

- [ ] **Step 4: Implement exact activation and native isolated-window regression**

`Activate` validates target ownership/token, sends `WM_MDIACTIVATE` to its exact parent, reads back the active child, then repeats active document A/B reads. On any mismatch return `document_session_changed` or `vismockup_document_window_changed`; never search by title. Extend the C++ harness with duplicate-name A/B, two MDI parents, blocked activation, marker replacement and HWND reuse.

- [ ] **Step 5: Run focused, native and full Connector tests**

Run:

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~ViewerDocumentPreparationTests --no-restore --verbosity quiet -p:UseSharedCompilation=false -m:1
$env:ELECTRON_RUN_AS_NODE='1'; node scripts/test_mdi_selector_native.js --runtime; Remove-Item Env:ELECTRON_RUN_AS_NODE
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore --verbosity quiet -p:UseSharedCompilation=false -m:1
```

Expected: focused and native harness pass; full suite reports exact pass/fail/skip counts.

- [ ] **Step 6: Create an execution checkpoint**

If commits are authorized during execution:

```powershell
git add local-runtime/src/Ai00.Connector.Adapters.VisMockup/NativeDocumentWindow.cs local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs local-runtime/tests/Ai00.Connector.Tests/ViewerDocumentPreparationTests.cs local-runtime/tests/Ai00.Connector.Tests/FakeVisMockupCom.cs
git commit -m "fix: bind viewer documents to active MDI windows"
```

Otherwise record `git diff --check` and leave the checkpoint uncommitted.

### Task 2: Add bounded document activation to the local interaction protocol

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/src/Ai00.Connector.AppHost/ViewerInteractionProtocol.cs`
- Modify: `local-runtime/src/Ai00.Connector.AppHost/ViewerInteractionPipeHost.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/ViewerDocumentPreparationTests.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/ViewerInteractionPipeTests.cs`

**Interfaces:**
- Consumes: Task 1 `CaptureActive`/`Activate`, installed interaction grant, exact `document_session`.
- Produces: `ActivateViewerDocumentAsync(string expectedDocumentSession, CancellationToken ct)` and closed pipe request `{type:"activate_document",request_id,interaction_id}` returning the same `ViewerDocumentTarget` shape as `prepare_document`.

- [ ] **Step 1: Add failing multi-document cache and protocol tests**

Use two fake documents in one process. Prepare A, make B active, activate A, then assert A becomes active without `OpenDocument`. Add errors for unknown session, process incarnation change, closed document, busy gate, cancellation and grant/runtime invalidation.

```csharp
var activated = await adapter.ActivateViewerDocumentAsync(sessionA, CancellationToken.None);
Assert.Equal("A", activated.DocumentId);
Assert.Equal(0, application.OpenCalls);
Assert.Equal("completed", response.GetProperty("status").GetString());
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~ViewerDocumentPreparationTests|FullyQualifiedName~ViewerInteractionPipeTests" --no-restore --verbosity quiet -p:UseSharedCompilation=false -m:1
```

Expected: missing activation method/message failures.

- [ ] **Step 3: Store multiple prepared targets by session**

Replace the single `_preparedWindow` tuple with a bounded dictionary keyed by document session. Cache process start ticks, document ID and window token. Remove stale entries on process incarnation change and cap the dictionary at the number of currently open documents plus a small fixed margin; do not persist it to disk.

```csharp
private sealed record PreparedTarget(long ProcessStartTicks, ViewerDocumentTarget Target);
private readonly Dictionary<string,PreparedTarget> _preparedTargets = [];
```

`PrepareViewerDocumentAsync` captures only the currently active signed-open document. `ActivateViewerDocumentAsync` requires a cached session, finds the same document in `OpenDocuments`, activates its marked HWND, then recomputes and compares the active `document_session`.

- [ ] **Step 4: Add the closed protocol operation**

Allow only `interaction_id` for `activate_document`. Route through the existing session validation, shared execution gate and five-second timeout. Return no HWND supplied by the caller; the Connector returns its own prepared target.

```csharp
if (request.Type is "prepare_document" or "activate_document") {
    var target = request.Type == "prepare_document"
        ? await adapter.PrepareViewerDocumentAsync(current.DocumentSession, ct)
        : await adapter.ActivateViewerDocumentAsync(current.DocumentSession, ct);
    return Completed(target);
}
```

- [ ] **Step 5: Run the focused and full suites**

Run the Step 2 command, then the full Connector command from Task 1. Expected: all new protocol, grant, gate and document lifecycle cases pass.

- [ ] **Step 6: Create an execution checkpoint**

If authorized, commit only Task 2 files with message `feat: activate prepared viewer documents`; otherwise record `git diff --check`.

### Task 3: Introduce Main-owned runtime slots and exact switching

**Files:**
- Create: `packages/core/electron/viewer_runtime_slots.js`
- Create: `packages/core/electron/viewer_runtime_slots.test.js`
- Modify: `packages/core/electron/capability_client.js`
- Modify: `packages/core/electron/capability_client.test.js`
- Modify: `packages/core/electron/viewer_interaction_client.js`
- Modify: `packages/core/electron/viewer_interaction_client.test.js`
- Modify: `packages/core/electron/preload.js`
- Modify: `packages/core/electron/main.js`
- Modify: `packages/sim-plugin/electron/vismockup_controller.js`
- Modify: `packages/sim-plugin/electron/vismockup_controller.test.js`

**Interfaces:**
- Consumes: Task 2 `activate_document`, existing bind@3 completion, grant installation, native `attachPrepared`/`completePrepared`.
- Produces: `ViewerRuntimeSlots`, `CapabilityClient.openViewerSource`, IPC `viewer-interaction:ensureReady` / `viewer-interaction:executeIntent`, and browser results without native identifiers.

- [ ] **Step 1: Write failing slot lifecycle tests**

Create a real unit harness around `ViewerRuntimeSlots` with keys `${workspace_gid}:${document_gid}`. Test A→B→A switching, same-name windows with distinct tokens, expired grant renewal on activation, page navigation releasing ownership without deleting prepared target, logout/runtime change deleting all targets, and a failed activation leaving the previous viewport hidden rather than switching by PID.

```javascript
await slots.store(scopeA, sessionA, preparedA);
await slots.store(scopeB, sessionB, preparedB);
assert.equal((await slots.activate(scopeA)).document_session, 'session-A');
assert.deepEqual(pipe.types, ['activate_document']);
assert.equal(native.attachCalls.at(-1).windowToken, preparedA.window_token);
```

- [ ] **Step 2: Run Electron unit tests and confirm RED**

Run:

```powershell
node --test packages/core/electron/viewer_runtime_slots.test.js packages/core/electron/viewer_interaction_client.test.js packages/sim-plugin/electron/vismockup_controller.test.js
```

Expected: module/API missing failures.

- [ ] **Step 3: Implement the smallest slot manager**

`ViewerRuntimeSlots` owns only runtime data and callbacks; it does not invoke cloud Capabilities itself.

```javascript
class ViewerRuntimeSlots {
  constructor(deps) { this.deps=deps; this.slots=new Map(); this.activeByOwner=new Map(); }
  key(scope) { return `${scope.workspace_gid}:${scope.document_gid}`; }
  store(scope, session, target, completion) {
    this.slots.set(this.key(scope), {scope:{...scope},session,target:{...target},completion});
  }
  async activate(scope, owner) {
    const slot=this.slots.get(this.key(scope));
    if(!slot) throw Error('runtime_slot_missing');
    const result=await this.deps.activatePrepared(slot,owner);
    this.activeByOwner.set(owner,this.key(scope)); return result;
  }
  releaseOwner(owner) { this.activeByOwner.delete(owner); }
  invalidateRuntime() { this.activeByOwner.clear(); this.slots.clear(); }
}
```

Do not persist slots. Bound size to current in-memory sessions; remove entries when Connector runtime changes or exact target validation fails.

- [ ] **Step 4: Move the exact governed launch/poll sequence behind Main**

Add a narrowly allowlisted `CapabilityClient.openViewerSource` that accepts only the closed Teamcenter source selector fields `endpoint_id`, `object_uid`, `item_revision_uid`, `bom_view_uid`, `revision_rule`, `configuration_date` and invokes `simulation.teamcenter.visualization.launch.request@2`, then polls only `simulation.vismockup.command.get@1` for that returned operation ID. Use one Main-generated idempotency key retained in the slot attempt. Return `{launch_operation_id, receipt}` where `receipt.protocol === 'ai00.viewer.opened-source.v1'`. Do not add a generic command executor.

```javascript
const {launch_operation_id,receipt} = await capabilityClient.openViewerSource({
  source_selector, expected_visdoc_uid:'', idempotency_key:attempt.openKey,
}, confirmOnce, assertCurrent);
if(receipt.protocol!=='ai00.viewer.opened-source.v1')throw Error('opened_source_receipt_invalid');
```

The first tree click may produce at most one combined desktop confirmation describing “open, associate and execute”. Cache that actual user decision only for the same in-flight intent so launch and bind challenges do not show duplicate dialogs; never reuse it for another intent, document or later operation. Cancellation stops before the next side effect.

- [ ] **Step 5: Add `ensureReady` and `executeIntent` to ViewerInteractionClient and IPC**

Validate a closed intent containing `workspace_gid`, `document_gid`, `expected_workspace_row_version`, the existing closed `source_selector`, and optional `{source_nodes,action}`. Existing owner/session with the same scope reuses the grant and activates its slot. A retained target after renderer navigation obtains a fresh authorized interaction through existing `scope.get`/`authorize`, then calls `activate_document`. A missing slot starts one Main-owned single-flight attempt: open source, bind@3, install grant, prepare/attach/recheck, then execute the original action.

```javascript
await client.executeIntent(event, {
  workspace_gid:'1', document_gid:'2', expected_workspace_row_version:7,
  source_selector:selector,
  source_nodes:[descriptor], action:'hide',
});
```

The page never supplies a launch operation ID, interaction ID, PID, document session, document handle, HWND or token. `ensureReady` uses the same path without `source_nodes/action` for the optional right-click command.

After local activation, call `native.attachPrepared` offscreen, call `prepare_document` again, compare process/document/window/token, then `completePrepared`. Never expose target fields to the page.

- [ ] **Step 6: Make one in-flight attempt survive response loss and preserve recovery**

On successful bind@3/install/prepare/attach, store the exact target and completion. If launch succeeded but its response is lost, retry with the same Main-owned idempotency key and accept only the immutable known result. On `opened_binding_pending`, retain the launch operation/completion; on native association failure retain the signed completion but do not mark the slot ready. Same intent retry resumes bind/attach and does not create a new launch key. `outcome_unknown` marks only that slot unwritable.

- [ ] **Step 7: Wire preload/Main and native controller**

Expose only `ensureReady(input)` and `executeIntent(input)` alongside existing compatibility methods. `VisMockupController` accepts prepared targets only, keeps them offscreen until Main calls `completePrepared`, and never falls back to process-wide discovery when a target was supplied.

- [ ] **Step 8: Run unit and Electron security suites**

Run:

```powershell
node --test packages/core/electron/viewer_runtime_slots.test.js packages/core/electron/capability_client.test.js packages/core/electron/viewer_interaction_client.test.js packages/sim-plugin/electron/vismockup_controller.test.js
npm run test:electron-security
```

Expected: unit suites pass. Any existing unrelated security regex failure must be named, not relabeled as pass.

- [ ] **Step 9: Create an execution checkpoint**

If authorized, commit Task 3 files with message `feat: retain exact viewer runtime slots`; otherwise record diff-check evidence.

### Task 4: Make model operations open on demand and continue automatically

**Files:**
- Modify: `packages/sim-plugin/web/cad_sim/viewer_interaction.js`
- Modify: `packages/sim-plugin/web/cad_sim/viewer_interaction.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/live_document_bootstrap.js`
- Modify: `packages/sim-plugin/web/cad_sim/live_document_bootstrap.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/live_document_adoption.js`
- Modify: `packages/sim-plugin/web/cad_sim/live_document_adoption.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim_native_view.test.js`

**Interfaces:**
- Consumes: Task 3 API `ensureReady` / `executeIntent`.
- Produces: `controller.executeIntent({scope,source_selector,source_nodes,action})` and `controller.ensureReady({scope,source_selector})`.

- [ ] **Step 1: Write failing demand-driven behavior tests**

Cover: valid slot executes without launch/bind; missing slot sends one Main intent; two simultaneous clicks share one Main open; hide→show for the same target while opening sends only final show; different targets preserve order; open succeeded/binding pending retries completion only; outcome unknown blocks later writes. Assert selecting the environment alone performs zero launch calls.

```javascript
const first=controller.executeIntent(intent('hide'));
const second=controller.executeIntent(intent('show'));
await Promise.all([first,second]);
assert.equal(mainIntentCalls,1);
assert.deepEqual(executedActions,['show']);
```

- [ ] **Step 2: Run the focused browser tests and confirm RED**

Run:

```powershell
node --test --test-isolation=none packages/sim-plugin/web/cad_sim/viewer_interaction.test.js packages/sim-plugin/web/cad_sim/live_document_bootstrap.test.js packages/sim-plugin/web/cad_sim/live_document_adoption.test.js packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js packages/sim-plugin/web/cad_sim/cad_sim_native_view.test.js
```

Expected: missing `ensureReady`/`executeIntent` and current “interaction not ready” behavior fail.

- [ ] **Step 3: Implement single-flight ensure and absolute-state coalescing**

In `viewer_interaction.js`, keep one pending intent per exact scope while Main performs `executeIntent`. Store one queued absolute intent per `{source descriptor, visibility|selection}` and keep its last action. The page does not decide whether a slot exists and does not launch the document itself.

```javascript
async function ensureReady(scope, source_selector) {
  if (sameReadyScope(scope)) return;
  await api.ensureReady({...scope,source_selector});
}
```

Do not coalesce across targets or between visibility and selection. Never optimistically change the model-tree state before a completed response.

- [ ] **Step 4: Route model-tree actions through `executeIntent`**

`live_document_adoption.actOnProductNode` must no longer require an already-open local scope. It constructs the existing source descriptor and sends one `executeIntent` to Main. In `cad_sim.js`, enable controls for a valid TC online document even when `document_session` is absent; render `opening/associating/attaching/mapping_pending/busy/outcome_unknown` without blanking the model tree.

- [ ] **Step 5: Make right-click open reuse the same ensure path**

The context action calls `ensureReady({scope,source_selector})` without a model command. Remove the right-click-only opening implementation. Keep legacy `_openTeamcenterOnlineDocument` only for nonlocal/compatibility paths; demand-driven local operation never calls it directly.

- [ ] **Step 6: Update frame transport allowlists and cache revisions**

Add `ensureReady` and `executeIntent` to the fixed preload/frame method lists. Recompute the exact owned transport source hash through the existing scanner; update only the matching allowlist entry with a reason describing the governed local interaction. Increment `?rev=` values for changed non-module scripts and update exact asset tests.

- [ ] **Step 7: Run focused and full cad_sim tests**

Run the Step 2 command, then:

```powershell
node --test --test-isolation=none packages/sim-plugin/web/cad_sim/*.test.js
```

Expected: focused suites pass; full suite failures, including known unrelated baseline failures, are reported individually.

- [ ] **Step 8: Create an execution checkpoint**

If authorized, commit Task 4 files with message `feat: open viewer documents on first model action`; otherwise record diff-check evidence.

### Task 5: Prove Capability compatibility and failure semantics

**Files:**
- Modify: `plugins/simulation/tests/test_viewer_open_completion.py`
- Modify: `packages/core/electron/viewer_interaction_client.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js`
- Modify: `scripts/desktop_runtime_allowlist.json`
- Create: `docs/verification/2026-09-22-demand-driven-viewer-operation.md`

**Interfaces:**
- Consumes: unchanged launch@2, bind@3 and authorize@1 contracts plus Tasks 1–4.
- Produces: traceable evidence that the new consumer sequence neither changes Capability contracts nor introduces an ungoverned desktop path.

- [ ] **Step 1: Add compatibility tests before any Descriptor edit**

Assert the local Catalog still resolves exact GIDs:

```text
launch@2 = cv2_cce43b004671f2f8e0b4edfd
bind@3 = cv2_1f92da28d1c518cd7ca6b230
authorize@1 = cv2_59f6ec1e05ca6e2b8fdef576
```

Assert bind@3 retains exact confirmation, expected row version, idempotency and immutable replay semantics. Existing-slot heat path must show zero Capability calls; fresh-slot path shows one launch and one bind completion; renewal alone may call authorize.

- [ ] **Step 2: Run Provider and contract suites**

Run:

```powershell
python -m pytest plugins/simulation/tests/test_viewer_open_completion.py plugins/simulation/tests/test_viewer_opened_source_binding.py plugins/simulation/tests/test_viewer_interaction_provider.py backend/tests/test_viewer_interaction_repository.py backend/tests/test_viewer_interaction_audit.py -q
```

Expected: no Provider production edit is needed. Native MySQL skips remain separately identified.

- [ ] **Step 3: Pin all recovery semantics in integration tests**

Add explicit tests for `open_not_started`, `open_outcome_unknown`, `opened_binding_pending`, `window_association_unavailable`, `mapping_pending`, `busy`, `outcome_unknown`, and `runtime_invalid`. Each test asserts whether launch may be retried. Only `open_not_started` permits retrying launch; binding/association failures reuse the same launch operation.

- [ ] **Step 4: Run transport and bypass scanners**

Run the repository’s existing desktop runtime scanner, no-desktop-business-bypass test, Electron IPC tests and `git diff --check`. Do not delete assertions or broaden a generic transport exception to make the scanner pass.

- [ ] **Step 5: Write the verification record**

Record exact commands and raw counts; separate static/native-isolated/live evidence. Governance state stays `human_approved: unverified` until the trusted server workflow supplies it. No generated Catalog or official release manifest may be treated as approval.

- [ ] **Step 6: Create an execution checkpoint**

If authorized, commit Task 5 test/evidence files with message `test: verify demand-driven viewer operations`; otherwise leave a reviewable uncommitted checkpoint.

### Task 6: Build, deploy, and measure the real diagnostic workflow

**Files:**
- Update generated frontend output through `npm run build:web:test-governance`.
- Build a new isolated Connector package under root `.runtime`; do not overwrite the previous package.
- Update the root unpublished local test manifest and rollback bundle only after hash verification.
- Append real results to `docs/verification/2026-09-22-demand-driven-viewer-operation.md`.

**Interfaces:**
- Consumes: reviewed outputs of Tasks 1–5.
- Produces: running test-branch application and reproducible real latency/correctness evidence.

- [ ] **Step 1: Request an independent whole-change review**

Review all Task 1–5 files, with special attention to the five Review Focus cases. Resolve every Critical/Important finding with a failing test followed by a passing test. Record reviewer scope and unresolved findings.

- [ ] **Step 2: Build isolated artifacts and verify hashes**

Build Connector and native N-API from the reviewed tree. Build `dist-test-governance`. Compare source and served bytes for `viewer_interaction.js`, `live_document_bootstrap.js`, and changed scripts. Verify actual Electron/Connector process paths and module hashes before testing.

- [ ] **Step 3: Deploy with rollback and preserve user scope**

Create a timestamped rollback folder containing old Connector package, native module, local manifest and served frontend dist. Restart only AI00 backend/Electron/Connector components. Do not terminate VisMockup or close models. If Connector restart clears TC login, ask the user to log in once, then keep the session untouched.

- [ ] **Step 4: Validate the exact user flow on the diagnostic bolt**

Use workspace `227728039260360704`, document `227728051386093569` only:

1. Select the environment; assert no VisMockup launch.
2. Click hide on the model-tree root; assert one open, one bind completion and automatic hide.
3. Click show/highlight/unhighlight; assert no launch/bind/scope.get in the hot path.
4. Switch away and back; assert exact window activation and no new window.
5. Reload the page while Main/Connector stay alive; assert fresh authorization plus target reuse, no model reopen.

Stop immediately on unknown outcome; never rerun the same write automatically.

- [ ] **Step 5: Measure and report**

Record cold first-action stages, existing-window switch, first mapping, and at least 100 hot operations. Report P50/P95/max/error count for response and observable screen change. Confirm zero cross-document/occurrence errors. If first open remains above target, attribute time by TC source, FMS, VisMockup load, bind, attach and mapping rather than increasing generic timeouts.

- [ ] **Step 6: Evaluate gates and rollback readiness**

Report `machine_passed`, `human_approved`, `runtime_verified` independently. Keep the previous package runnable. Do not publish, push or mark formal approval without the authorized workflow.

## Self-Review and Handoff

- Spec coverage: UX and state model Task 3–4; exact window association Task 1–2; Capability reuse/governance Task 5; deployment/performance/rollback Task 6.
- No new business Capability, transport service or database table is introduced.
- Interface names are consistent: `CaptureActive`, `Activate`, `ActivateViewerDocumentAsync`, pipe `activate_document`, Main/browser `activate`, page `ensureReady`/`executeIntent`.
- Every Review Focus item has an explicit test in Task 1, 3 or 4.
- Main owns TC launch, immutable launch retry identity, reusable runtime slots and exact activation. The page sends source and operation intent only; Main never trusts page-native identity.
- No product code, process or runtime state is changed by this plan.
