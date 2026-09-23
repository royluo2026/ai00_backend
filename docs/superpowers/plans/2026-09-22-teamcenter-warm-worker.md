# Teamcenter warm visualization worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove repeated Java startup and visualization authentication from model opens, with measured first-open and login costs.

**Architecture:** One AI00-owned Java visualization worker per explicit login generation, using one TC connection and a lazily initialized reusable FMS utility. Keep serialized source resolution and the existing material/consumer acknowledgement handshake; public Capability contracts and same-open identity evidence stay unchanged.

**Tech Stack:** Windows, .NET/C#, Java 11 Nashorn, Siemens TC SOA/FMS, Node test runner, xUnit.

**Spec:** `docs/superpowers/specs/2026-09-22-teamcenter-warm-worker-design.md`

## Global Constraints

- Teamcenter remains source authority; VisMockup remains renderer. No historical identity matching is reintroduced.
- No process pool, renderer replacement, public API, new Capability, database migration, external-client credential extraction, or Siemens configuration changes.
- The current readonly structure/search worker stays unchanged in this increment.
- Credentials are sent only once over inherited private stdin for that generation, never command arguments, files, logs or renderer IPC.
- Never automatically replay the current open/insert or fall back to the old opener.
- No lifetime-wide in-memory idempotency ledger is added.
- Formal machine_passed, human_approved and runtime_verified are unverified for this change; AI remains advisory.
- Work only in the existing backend test worktree. Preserve existing timing-test edits. Do not automatically commit, push, restart the running application, or touch unrelated models.

## Review Focus

1. Logout/account switch while native consume is blocked: readiness revoked immediately, old result fenced, owned child stopped within a bound (Task 4).
2. Child exits after native invocation: retain unknown/effect semantics; zero automatic repeats (Tasks 3–4).
3. Mismatched/oversized frames and endless SDK output: bounded memory, session invalidation, no secret forwarding (Tasks 1–3).
4. Reused cache after source access changes: every request still resolves authorized TC source; cache never grants authority (Task 2).
5. Worker dead/expired between status and open: no false ready state or silent reauthentication (Tasks 3–4).

## File ownership

Paths below are relative to the backend worktree.

- Modify `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterReadOnlyRuntime.cs`: timing parser, production worker delegation, login generation, readiness and teardown.
- Create `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterVisualizationSession.cs`: owned child, bounded transport and one-request handshake. Keep SDK/source logic in Java.
- Modify `local-runtime/src/Ai00.Connector.Adapters.VisMockup/teamcenter_visualization_launch.js`: session loop, source resolution, FMS reuse and timing.
- Preserve public `ITeamcenterWorker` operation signatures; add a separate lifecycle interface in the session file.
- Modify `local-runtime/tests/teamcenter_direct_model_source.test.cjs`; create `local-runtime/tests/teamcenter_visualization_session.test.cjs`: VM-based actual JavaScript behavior with fake SDK, not string assertions.
- Complete `local-runtime/tests/Ai00.Connector.Tests/TeamcenterVisualizationTimingTests.cs`.
- Create `local-runtime/tests/Ai00.Connector.Tests/TeamcenterVisualizationSessionTests.cs` and `TeamcenterSessionLifecycleTests.cs`: framed transport, process reuse, failure and generation tests.
- Existing regressions: `TeamcenterWorkerContractTests.cs`, `TeamcenterLeafSourceTests.cs`, `VisMockupDocumentLifecycleTests.cs`.
- Create `docs/verification/2026-09-22-teamcenter-warm-worker.md`: measured evidence, limits, artifact hashes and rollback.

## Internal interfaces and protocol

Add these internal boundaries, without changing public Capability schemas:

```csharp
internal interface ITeamcenterVisualizationLifecycle
{
    bool IsReady(long generation);
    Task StartAsync(long generation, string endpointId, string username,
        string password, CancellationToken ct);
    void Invalidate(long generation);
    Task StopAsync(long generation, CancellationToken ct);
}
```

`TeamcenterProcessWorker` implements this interface by delegating to `TeamcenterVisualizationSession`. `Invalidate` synchronously fences that generation and cancels its token; `StopAsync` targets only that generation, so late teardown cannot kill a replacement. Session owns its process and stream drain tasks. Runtime calls Start instead of throwaway ValidateCredentials for lifecycle-capable workers; legacy injected workers retain existing Validate behavior, with explicit tests for both paths.

Wire prefix `AI00_TC_VIS_V2:` with newline-delimited JSON, maximum 65,536 UTF-8 bytes per frame, duplicate/unknown fields rejected. Envelope: `{type, generation, request_id, payload}`. Generation is an invariant decimal string; request IDs are 32 lowercase hex characters. Login has endpoint/username/password payload; consumes retain the current consume payload; acknowledgements have empty payload. Allowed types: `login`, `ready`, `consume`, `material_ready`, `material_consumed`, `material_failed`, `result`, `logout`, `closed`. Preserve existing material/result payload fields. Never include raw SDK errors: map to existing closed Connector error codes.

Only one request is active. Authentication response matches login ID; material and result match consume ID; acknowledgement echoes consume ID; logout uses a new ID. Wrong ordering/ID/generation invalidates child. No login message is logged. Max 16 queued protocol frames; overflow invalidates session. Discard non-protocol stdout with bounded incremental reads, never allocate an unbounded line. Stderr retains at most 32 sanitized timing entries and no raw text. Logout grace is 2 seconds, then kill only the owned process and boundedly join drains. EOF releases Java resources.

### Task 1: Finish numeric phase timing

**Interfaces:** retain `internal static string? TeamcenterProcessWorker.SanitizeVisualizationTiming(string line)`; add JavaScript `timed(phase, action)` returning action result and rethrowing the same exception.

- [ ] Run the existing RED tests, preserving output:

```powershell
node --test local-runtime/tests/teamcenter_direct_model_source.test.cjs
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~TeamcenterVisualizationTimingTests
```

Expected: positive parser case and two timing cases fail, existing source tests pass.

- [ ] Implement a closed parser: exactly phase/string and elapsed_ms/number, no duplicate fields, finite 0–3,600,000ms; reject non-object and malformed JSON. Whitelist `process_start`, `login`, `source_load`, `launch_info`, `dataset_resolve`, `fms_init`, `file_load`, `fms_get_files`, `material_retain`, `native_consumer`, `ack_final`, `logout`. Reconstruct JSON rather than forwarding original text.

```javascript
function timed(phase, action) {
  var start = java.lang.System.nanoTime();
  try { return action(); }
  finally {
    java.lang.System.err.println('AI00_TC_TIMING_V1:' + JSON.stringify({
      phase: phase,
      elapsed_ms: Number(java.lang.System.nanoTime() - start) / 1000000
    }));
  }
}
```

Use the existing Java.type System test seam when integrating this function. Wrap SDK calls and parent phases without logging values, errors, identifiers or paths.

- [ ] Add oversized timing-line rejection (over 1,024 characters) and positive tests for every whitelisted phase; rerun both commands to PASS.

### Task 2: Make Java a serial authenticated session

**Interfaces:** `runSession(io, sdk)` is the testable JavaScript orchestration function. `io.read()` returns a parsed validated frame or null/EOF; `io.write(frame)` emits a bounded frame. `sdk.login(payload)` returns a connection object exposing `prepare(payload)`, `cleanup()`, `logout()`. `prepare` contains the existing TC source/launch-info/FMS logic and returns the current material payload. `cleanup` removes only current request temporary files. Production adapter creates one FMS utility lazily inside this connection.

- [ ] Write behavior tests in `teamcenter_visualization_session.test.cjs` using in-memory arrays for io and a fake SDK. Core test input and expectations:

```javascript
const frame = (type, id, payload = {}) => ({type, generation:'1', request_id:id.repeat(32), payload});
const input = [frame('login','a',{endpoint_id:'tc-production',username:'u',password:'p'}),
  frame('consume','b'), frame('material_consumed','b'),
  frame('consume','c'), frame('material_consumed','c'), frame('logout','d')];
const output = []; let logins=0, prepares=0, cleanups=0, logouts=0;
runSession({read:()=>input.shift() || null, write:x=>output.push(x)}, {
  login:()=>{logins++; return {
    prepare:()=>{prepares++; return {material_path:'controlled-test-path'};},
    cleanup:()=>{cleanups++;}, logout:()=>{logouts++;}
  };}
});
assert.equal(logins,1); assert.equal(prepares,2);
assert.equal(cleanups,2); assert.equal(logouts,1);
assert.deepEqual(output.map(x=>x.type),['ready','material_ready','result','material_ready','result','closed']);
```

- [ ] Run `node --test local-runtime/tests/teamcenter_visualization_session.test.cjs`; expect missing session implementation failure.
- [ ] Implement loop: require login first; validate each frame; prepare each source; emit material; accept exactly one matching ack; clean per-request material in finally; emit final result; await next request. Exit and release connection on EOF, auth expiry or malformed protocol. Never repeat consume. Failed consumer must not produce successful result. Move logout/release to outer finally, not each request.
- [ ] Extend behavioral tests: denied second source calls prepare and returns failure despite cached bytes; wrong ack ID/generation/type; EOF during ack; two consumes without ack; failed consumer; session expiry; FMS constructed once for two direct models; per-request temporary cleanup on success/failure; password not written to output. Run both Node test files to PASS.

### Task 3: Own the persistent child and bounded transport

**Interfaces:** session implements lifecycle above; add `Task<TeamcenterLaunchResult> ConsumeAsync(TeamcenterSourceSelector selector, string expectedVisdocUid, string visualizationOperation, Func<string,CancellationToken,Task> consumer, CancellationToken ct)`. It uses the active generation, retained material helpers and existing result mapping. Internal constructor accepts `Func<System.Diagnostics.Process> startProcess` for an owned fake-child test seam; production supplies existing secured Java ProcessStartInfo.

- [ ] Add tests using a test child launched from the existing test assembly through a dedicated helper mode, or a checked-in Node fixture `local-runtime/tests/fixtures/teamcenter_visualization_child.cjs` invoked with an absolute Node path. Fixture reads real stdin, emits frames and tracks starts/consumes; it receives only fake credentials. Expose counters via responses, not filesystem secrets.
- [ ] Core reuse test drives Start(1), Consume(Open), Consume(Insert), Stop(1), asserting one process start, one login, two source preparations and two consumer callbacks. Deliberately leave child alive after first result: first consume must finish before process exit. Run the SessionTests filter RED.
- [ ] Implement per-process bounded stream pumps, exact frame validation and linked cancellation. Delegate existing worker consume to session; remove per-open process startup/exit waiting. Keep secured operation roots, ValidateMaterialPath, RetainRendererMaterial and current source/result comparison.

```text
consume:
  capture generation and session cancellation token
  send one consume frame; await matching material_ready
  validate source evidence and path; retain material
  invoke consumer once, remembering its original error
  send consumed/failed ack; await matching result
  fence generation before returning
  finally clean only operation directory
failure:
  invalidate generation; stop owned child; never resend
  preserve consumer error / existing post-dispatch unknown semantics
```

- [ ] Add parameterized tests for frame >65,536 bytes, duplicate fields, wrong generation/ID, unsolicited response, queue overflow, megabytes of non-protocol output, stderr secret lines, crash before/after consumer, cancellation before/after consumer and stale final result. Assert zero second consumer invocation, retained diagnostics <=32, no raw diagnostic forwarding, bounded completion.
- [ ] Run SessionTests and WorkerContractTests filters PASS. Ensure fake child processes are terminated by test finally blocks on assertion failure.

### Task 4: Integrate login generation and safe teardown

**Interfaces:** runtime public LoginAsync/GetSessionStatus/LogoutAsync/Dispose stay unchanged. Under credentialState hold monotonically increasing generation and a cancellation source. No new public fields. Production readiness requires credentials AND lifecycle.IsReady(current generation).

- [ ] Add `TeamcenterSessionLifecycleTests.cs` with a lifecycle-capable fake worker and controllable TaskCompletionSources. Tests: login calls Start once and Validate zero times; normal source-read credentials remain available; dead child makes status not-ready; explicit login after death starts new generation.
- [ ] Add logout/account-switch race test: hold consumer completion pending; invoke logout; immediately assert status not-ready, lifecycle invalidated and cancellation signaled; release old consumer and assert it cannot publish a result into a subsequent generation. Run LifecycleTests RED.
- [ ] Implement revocation before waiting on gate. Snapshot old generation/CTS under credentialState, clear credentials and invalidate generation; cancel/stop outside lock. A login attempt reserves its generation before waiting, and may publish credentials only if still current. Consume captures generation and linked cancellation while gated, checks generation after await. Stop(old generation) must not stop new child.
- [ ] Dispose marks runtime disposed, invalidates/cancels/terminates owned child boundedly; do not dispose the semaphore while pending callers may release it. All newly entering methods check disposed before accessing state. Add tests for Dispose during queued operation, expiry during source preparation and legacy worker validation behavior.
- [ ] Run full .NET tests, both Node behavioral suites; preserve launch v1/v2 and local control tests. No false-ready default interface implementation.

### Task 5: Stage, measure and report without widening authority

**Files:** verification document above, new isolated root `.runtime/connector-warm-worker-20260922` package; runtime manifest only after all tests and planned activation approval.

- [ ] Record git diff/status, run complete .NET suite and Node suites. Compare public launch receipts and source authority with existing lifecycle tests; inspect repository provider/catalog requirements and record this internal lifecycle classification. Do not promote formal governance statuses without their required evidence.
- [ ] Publish isolated package, not over running binaries:

```powershell
dotnet publish local-runtime/src/Ai00.Connector.AppHost/Ai00.Connector.AppHost.csproj -c Release -o E:/Projects/ai00_v3/.runtime/connector-warm-worker-20260922
```

- [ ] Confirm package entry executable, adapter/host DLL hashes and launcher script inclusion. Retain current `.runtime/connector-local-viewer-20260922` and manifest backup. Activate only that staged package through the existing supervisor workflow; request login once if session restart requires it. Do not launch additional manually managed Connector instances.
- [ ] Use only workspace `227728039260360704`, document `227728051386093569`, diagnostic W01-89184128. Record login-to-ready, first open, two repeated opens, per-phase times, child PID reuse, native attach, binding, grant and total ready time. Ensure no unrelated docs are closed. Warm reuse must show one Java process/login, not merely a shorter second run.
- [ ] Exercise diagnostic local hide/show/highlight/unhighlight and audit delivery, then leave the model visible. Record callbacks separately from pixel-render latency. No whole-vehicle benchmark.
- [ ] Document measured before/after (baseline total 28.44–31.47s, Connector launch 14–15s), source of each number, unresolved cloud-stage cost and login cost. If startup fails, worker leaks, source/receipt mismatch occurs, or controls regress, restore the exact previous manifest/package through supervisor and report failed acceptance. Do not claim numeric improvement without new measurements.

## Self-review / handoff

- Spec coverage: timing Task 1; persistent authenticated session/FMS/source authority Task 2; protocol/material/error semantics Task 3; lifecycle/readiness Task 4; governance/deployment/measurement Task 5.
- Five Review Focus cases have owning test tasks. Public launch contracts and native identity read remain unchanged; no speculative shortcut to native attach.
- Plan review required before implementation. Recommended execution: native in this session, because Java protocol, C# session and generation lifecycle are tightly coupled; independent review after regression verification.
