# Viewer Open Short Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate redundant cloud identity/scope reads and blocking workspace refresh after a TC open, retaining exact local document targeting and audited authorization.

**Architecture:** Introduce bind major3 as the single completion transaction, reusing major2 source association and interaction authorization. Electron owns nonce/grant and prepares the exact native target through Connector. The page receives only presentation state and an opaque interaction identifier.

**Tech Stack:** Python/PyMySQL Capability Provider, .NET8 Connector, Siemens COM/STA, Electron/CommonJS and existing Node/JSDOM tests.

**Spec:** `docs/superpowers/specs/2026-09-22-viewer-open-short-path-design.md` (user approved with go).

## Global Constraints

- 不以历史运行身份作为新打开的前提。
- 授权由 Electron 主进程保管，不向 iframe 交付。
- 旧接口保留供重连等既有消费者使用。
- 失效不自动重放打开；提示重连或重新选择目标。
- 不关闭其他模型、不打开整车。
- 不新增提交或推送，除非用户要求。
- 3–5秒是验收目标，不是保证。Cached-JT/warm-renderer measurements must not be called cold startup.
- Existing worktrees B=`E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`, F=`E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`, both test. Preserve all earlier warm-worker/recovery edits. Verify branch/worktree before execution; no extra worktree needed.

## Review Focus

1. External VisMockup UI switches documents between preparation and embedding: never expose another document as ready (Task2/3).
2. Server completion commits but HTTP response is lost: retry completion, not model launch; same nonce must not create duplicate grants (Task1/3).
3. Idempotent completion response contains an expired grant: use bounded renewal, never extend/reinstall the stale signature (Task1/3).
4. A background refresh returns after another environment was selected: no stale row version or session overwrite (Task4).
5. Finalization proof is audited under a different descriptor than authorize@1: validate exact actual descriptor, not fabricated context or downgraded checks (Task1/5).

## Shared wire decisions

Capability: `simulation.environment.online_source.live_document.bind@3`.
Input (closed): workspace_gid, document_gid, launch_operation_id, expected_workspace_row_version, idempotency_key, session_nonce. Nonce is Main-generated lowercase64hex. No renderer-provided PID, document identity or grant.
Output (closed): binding (existing v2 binding result), grant (existing signed viewer grant). The current document identity is derived from signed launch evidence and grant.document_session; it is not a new browser claim.

Electron method: `ViewerInteractionClient.openFromLaunch(event,input)`; browser input is the above without session_nonce. Return `completed` with `{interaction_id,workspace_row_version,document_gid,document_session}` only. Grant/source proof remain Main-owned.
Private Connector request: `prepare_document {interaction_id}`. Uses installed grant and returns `{process_id,document_session,document_id}` derived on STA, not passed by browser. Invalid/currently changed document returns explicit rejection, no launch.
Page state: `_pendingTeamcenterOnlineBinding` retains launchOperationId and expected row version until completion; same-open retry never calls launch again.

### Task 1: Atomic completion and authorization

**Files (B):** modify `plugins/simulation/simulation_backend/data/workspace_repository.py`, `data/viewer_interaction_repository.py`, `application/viewer_interaction.py`, `capabilities/live_documents.py`, `capabilities/provider.py`, `capabilities/connector_runtime.py`; create `backend/contracts/viewer_open_completion_v1.py`, `plugins/simulation/tests/test_viewer_open_completion.py`. Extend existing `test_viewer_opened_source_binding.py` and `test_viewer_interaction_authorization.py` fixtures, not a second mock repository.

**Interfaces:** consumes signed launch@2, existing binder, grant signer and Catalog. Produces `LiveDocumentProvider.bind_online_v3(payload,context)` and a transaction-aware `ViewerInteractionRepository.authorize_scope(...,transaction=None)`. Existing callers omit transaction; supplied transaction is neither committed nor closed by the helper.

- [ ] Read full binder and authorization transactions, lock order and existing idempotency behavior. Map workspace→document→runtime locks against all sibling paths; preserve a consistent order. Reuse existing idempotency table, no new table unless evidence proves existing storage cannot represent the closed result.
- [ ] Define closed input/output models and failing SQL tests using the existing `opened` fixture. Required test assertions:

```python
# Each is a separate test using the real SQL fixture and signer.
assert result['grant']['document_session'] == verified_session
assert result['binding']['workspace_row_version'] == previous_version + 1
assert replay == result  # same business key and same Main nonce
assert after_sign_failure == before_transaction
assert different_nonce_error == 'idempotency_conflict'
assert proof_descriptor_id == 'simulation.environment.online_source.live_document.bind'
assert proof_descriptor_major == 3
```

Use explicit fixture literals for verified_session/row version. Add failures for wrong actor/tenant/source/runtime, stale row version, altered signature, frozen workspace, expired receipt, and proof persistence failure. Cover concurrent completion and nonce differences using existing SQL concurrency harness.
- [ ] Run `python -m pytest plugins/simulation/tests/test_viewer_open_completion.py -q`; Expected: failing missing major3 behavior, not fixture/import failure.
- [ ] Extract the existing binder's transaction body so major2 and major3 share source authorization. Execute binding, association, grant generation, signing, evidence persistence and cached completion result within one outer transaction:

```python
with transaction() as tx:
    # Invoke shared locked binding body with launch@2 evidence.
    # Allocate/sign/persist grant using authorize_scope(transaction=tx).
    # Store the closed completion result under key plus exact normalized input.
    # Return only after successful commit; never nest a new connection here.
    return completion_result
```

The comments specify insertion points in existing bodies, not permission to replace their validation. Factor catalog_binding to receive an explicit allowed descriptor key: authorize@1 or bind@3; default stays authorize@1. Verify the actual context version GID/business hash/Provider and operation contracts against that key. Audit verification must accept these two exact issuers, never arbitrary descriptors. Missing exact-hash evidence fails closed.
- [ ] Expired replay: return immutable result; Main renews via existing authorize with the committed grant_id/nonce before installation. New nonce uses a new interaction, not the old result; conflict is explicit. Do not repeat binding or launch to refresh a grant.
- [ ] Run new tests plus `python -m pytest plugins/simulation/tests/test_viewer_opened_source_binding.py plugins/simulation/tests/test_viewer_interaction_authorization.py plugins/simulation/tests/test_viewer_interaction_provider.py backend/tests/test_simulation_connector_runtime_v2_sql.py -q`. Expected: pass; native MySQL skips reported separately. No commit.

### Task 2: Exact local target preparation

**Files (B):** modify `local-runtime/src/Ai00.Connector.AppHost/ViewerInteractionProtocol.cs`, `ViewerInteractionPipeHost.cs`, `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`; create `local-runtime/tests/Ai00.Connector.Tests/ViewerDocumentPreparationTests.cs`.

**Interfaces:** installed signed grant → prepare_document → actual native identity. Reuse `DocumentSession` calculation and existing identity read/STA logic. No new public Capability or unsigned identity authority.

- [ ] Add tests for same PID/different document, PID reuse, expired/revoked grant, runtime generation change, gate busy/quarantined, cancellation, and valid session. Assert preparation does not open/activate a new document or call cloud transport.

```csharp
// Tests use the existing fake native runtime/pipe harness.
Assert.Equal("document_session_changed", changed.ErrorCode);
Assert.Equal(0, native.OpenCalls);
Assert.Equal(expectedPid, prepared.ProcessId);
```

- [ ] Run `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~ViewerDocumentPreparation --no-restore --verbosity quiet -p:UseSharedCompilation=false -m:1`; Expected: missing prepare behavior fails.
- [ ] Add closed protocol case, normal owner/grant validation and shared execution gate. Adapter method `PrepareViewerDocumentAsync(string expectedDocumentSession,CancellationToken ct)` returns an internal record `ViewerDocumentTarget(int ProcessId,string DocumentSession,string DocumentId)` from current native identity only. It rejects mismatch before returning; never searches historical results.
- [ ] Run full .NET suite. Expected: existing443 plus new tests pass. No commit.

### Task 3: Main owns completion and target, browser owns neither

**Files (F):** modify `packages/core/electron/viewer_interaction_client.js`, its `.test.js`, and its existing frame IPC registration; inspect and extend the existing native-view host/binding only if needed for exact-document attachment. Keep all original native recovery entrypoints intact.

**Interfaces:** browser openFromLaunch→bind@3 once→install_grant→prepare_document→native attach→prepare_document recheck. Return safe presentation result only after post-attach match. Source association and nonce feed existing renewal path; no scope.get call.

- [ ] Extend existing `rig()` with distinct completion and prepare responses. Test the real client dispatcher:

```javascript
const opened = await r.client.openFromLaunch(r.event, input);
assert.equal(opened.status, 'completed');
assert.deepEqual(r.calls.map(x=>x.id), ['simulation.environment.online_source.live_document.bind']);
assert.equal('grant' in opened.result, false);
assert.equal('process_id' in opened.result, false);
```

Add binding major3 assertion, window-owner/navigation fencing during every await, and response-lost replay with the same pending nonce. Simulate changed native identity after attach: hide/detach the view, close the new interaction, return rejection, never ready. Invalid grant must not call native attach. Expired replay uses existing renewal and does not repeat launch/bind effect.
- [ ] Run `node --test packages/core/electron/viewer_interaction_client.test.js`; Expected: new method/behavior fails.
- [ ] Implement `openFromLaunch` with the established session owner/invalidation helpers, preserving pending nonce across same attempt. Add internal `installPreparedGrant(session,grant)` by factoring existing renew validation/install, not a second signature validator. Main derives native target only from Connector. Perform bounds updates through the existing trusted native host; recheck document after attach before exposing visible/ready. Document external UI race: later changes invalidate mapping; subsequent actions retain per-session target validation.
- [ ] Run client tests and `npm run test:electron-security`. Expected pass; record failures by name. No commit.

### Task 4: Page short path and scoped updates

**Files (F):** modify `packages/sim-plugin/web/cad_sim/cad_sim.js`, `viewer_interaction.js`, `live_document_bootstrap.js`, `environment_store.js`; tests `teamcenter_lazy_tree.test.js`, `viewer_interaction.test.js`, `environment_store.test.js`, `cad_sim_native_view.test.js`.

**Interfaces:** local launch@2 outcome supplies plan_id; `local.openFromLaunch(input)` yields safe completion state. Legacy nonlocal and reconnect paths stay unchanged. Add `store.applyOpenedDocument(workspaceGid,expectedRowVersion,result)` with generation/current-selection fence.

- [ ] Add failing integration tests: successful local open issues launch only, no independent identity.read; no blocking openWorkspace; binding retry reuses launchOperationId; local close/invalidate happens on environment switch. Use existing JSDOM page harness, not string-count tests.

```javascript
assert.deepEqual(commands, ['simulation.teamcenter.visualization.launch.request']);
assert.equal(blockingWorkspaceReads, 0);
assert.equal(openCountAfterRetry, 1);
assert.equal(oldEnvironmentCompletionApplied, false);
```

- [ ] Run `node --test packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js packages/sim-plugin/web/cad_sim/environment_store.test.js`; Expected failure on redundant identity/refresh/current-state behavior.
- [ ] Change local branch to call local.openFromLaunch with pending operation/context. Apply returned version/document status only to the captured workspace and document. Retain pending launch on failures; never fall back silently to the historical-binding path. Defer unrelated full refresh; any explicit/background refresh uses generation fencing and cannot close the newly established interaction. No optimistic ready before Main completion.
- [ ] Run changed tests plus all cad_sim tests and `npm test`. Expected pass; report unavailable/project failures explicitly. No commit.

### Task 5: Contract evidence, review, deploy and measure

**Files:** add B `docs/verification/2026-09-22-viewer-open-short-path.md`; update exact local artifact manifests through existing unpublished local build flow under root `.runtime`. No official release approval/hash waiver.

**Interfaces:** Task1 major3 and Task3 caller must share version/input/output and current descriptor evidence; Task2 local protocol must match Main. All task tests run against final combined tree.

- [ ] Assert Catalog resolves major3 to simulation, confirmation/idempotency/exposure are inherited intentionally, grant audit resolves the real issuer, and legacy majors remain callable. Write test expecting mismatched issuer/artifact to fail. Run Provider/contract suites before generating exact local manifest.
- [ ] Fresh independent review of the complete uncommitted diff plus all new files, focusing on five Review Focus cases. Fix important findings with RED→GREEN. Preserve unrelated warm-worker/recovery edits and list the exact review range/file set.
- [ ] Build separate Debug Connector package; build/serve current frontend with the existing local app content workflow. Verify executable AND DLL/JS hashes, running paths, and actual served frontend functions. Snapshot rollback manifest; do not overwrite old package. Restart only verified AI00 components; notify user if TC login is cleared. No unrelated VisMockup closure.
- [ ] Using root `.runtime/profile_diagnostic_open.js` (updated instrumentation to new functions), open only workspace227728039260360704/document227728051386093569 twice after confirmed login. Capture total, completion RPC count, native attach/preparation, grant installation, Java PID/FMS reuse, tree clicks, direct hide/show/highlight/unhighlight, and grant-proof audit counts. Any unknown outcome stops replay.
- [ ] Report pass/fail for3–5sec goal with cache/startup conditions. Existing launch request itself measured6.3–7.4sec; if unchanged dispatch remains dominant, record that the target is not met and separately propose its optimization. Never claim this completion work guarantees3–5sec.
- [ ] Record governance gates independently, missing MySQL/live tests and rollback procedure. No commit/push.

## Self-review and handoff

Spec coverage: source authorization/atomicity/proof Task1; local handle/invalidations Task2–3; browser state/refresh Task4; governance/deployment/measurement Task5. Five Review Focus cases have named tests in Tasks1,3,4,5. Shared input excludes nonce from renderer; Main supplies it; grant stays private. No runtime changes made while writing this plan.

Recommended execution: native in this session, then one fresh whole-change reviewer. Tasks depend tightly on the completion response and local protocol; parallel independent implementation would increase interface drift. Await user review of this plan and execution-method selection before implementation.
