# Local viewer interaction — test deployment verification

Status: experimental test deployment activated on 2026-09-22; diagnostic small-part local control verified. Cold open remains slow. Not a signed release or governance approval.

## Controlled small-part runtime verification

After user login, selected only `诊断-小零件内嵌-20260921` (workspace `227728039260360704`, document `227728051386093569`, W01-89184128 bolt). One new-open invocation completed in **31,469.5ms** with native state attached and local interaction ready. No whole-vehicle open or unrelated document close. Cold open latency is unresolved.

First local actions (page controller through actual Main/pipe/COM): hide **403ms** including cold mapping; show **77.1ms**, highlight **94.9ms**, unhighlight **77.1ms**, all successful.

Then 100 samples per operation (400 total), all completed without retry or failure:

| Action | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|
| hide | 47.9 | 84.9 | 219.5 |
| show | 48.4 | 90.9 | 124.4 |
| highlight | 47.0 | 63.0 | 79.9 |
| unhighlight | 46.8 | 78.2 | 110.6 |

Actual DOM model-tree checkbox clicks (not direct controller benchmark) completed in **63.0, 61.7, 52.5ms**, toggling checked true/false/true, retaining the local-interaction tooltip. Final diagnostic part shown, selection cleared by benchmark. Measurements cover callback completion / checkbox handler completion, not observed pixel-change timing.

Read-only test database check confirmed **404 events / 404 with persisted grant proof**, 3 used grants; renewal reached generation 5. Three subsequent tree clicks were not yet uploaded at that exact checkpoint. No grant/signature/credentials printed. Raw performance samples remain in the running diagnostic iframe `__diagnosticBenchmark`; bounded readers are root `.runtime/read_diagnostic_benchmark.js` and `.runtime/read_diagnostic_audit.py`.

Final readback reached **414 events / 414 with proof**, 5 used grants, renewal generation 6. This exceeds the agent's 407 issued test actions; additional live-session actions are not attributed to this benchmark. Aggregate counts alone do not identify each subsequent click.

These controlled observations establish this small-part path only, not arbitrary assembly occurrence mapping, production acceptance, or formal `runtime_verified` governance state tied to a persisted Snapshot/test-run/revision. Formal statuses remain unverified.

## Latest deployment checkpoint

- Parent reran frontend regression after late-open/native whitelist fixes: **144 passed**, no skips. Actual compiled addon Windows pipe whitelist/PID/round-trip smoke passed independently.
- Final combined Connector TRX: **406 passed**, no skips. Server evidence correction: worker **171 passed**; parent startup/migration rerun **9 passed**. Earlier counts below are historical.
- Additive 0029 applied only to `test_workmanship_sim_viewer_grant_evidence` and the test migration ledger; checksum `500f4532fb576face066d5ce968c81a3d288f9beaaf28f07cee6269fed38404b`. 0028 unchanged.
- Authorized test App stopped, backed-up native addon replaced with staged SHA256 `4372F4A4763911E23DE6F507F57D8662C4B4299C75FE3202309A0241E95248C3`.
- New backend PID 279012; Electron PID 197872; supervised Connector PID 280536, parent 197872, executable `.runtime/connector-local-viewer-20260922/AI00.ConnectorHost.exe`.
- Main feature flag enabled. Actual cad page readback: `本地交互 · 待打开模型`; Connector ready/healthy; native detached; Teamcenter logged_out. User asked once to log in. No model opened or controlled at this checkpoint.
- Immutable issuance evidence records trusted authorization outcome, exact descriptors/version GIDs/business hashes/Catalog/provider binding, signed grant and digest. Audit checks retained proof; no per-click cloud identity check introduced.
- Governance: `machine_passed=unverified` (no authoritative Snapshot-wide Release Gate result), `human_approved=unverified`, `runtime_verified=unverified` (no live four-action/model performance evidence). Scoped tests passing and test activation do not confer those formal states. AI remains advisory.

## Scope

Current-open TC source receipt → source association → short-lived local grant → opaque native node references → dedicated local pipe. Interactive visibility/selection do not request cloud command plans. TC remains the source authority; native identity is a local reference-lifetime check, not historical identity matching.

Only the existing diagnostic small-part environment is authorized for runtime control tests. No whole-vehicle open, TC mutation, save, or unrelated document close.

## Deployment preparation

- Backend and frontend existing isolated worktrees remain on `test`. No commits or broad staging.
- Original running host: `.runtime/connector-fast-debug-publish-20260921b/AI00.ConnectorHost.exe`.
- Backup: `E:/Projects/ai00_v3/.runtime/viewer-local-predeploy-20260922/` contains the active host manifest and original backend runner. Existing host directory remains intact.
- Fixed the test backend runner's stale hardcoded `connector-reuse-publish` path: it now preserves the active manifest target, or accepts an explicit staged target confined to the test workspace.
- New launcher `.runtime/start_local_viewer_app.ps1` validates the host hash, refuses duplicate App processes, and enables the Main-owned local interaction flag.
- Launcher syntax and backend runner compilation checked. No runtime restart at this checkpoint.
- Test migration 0028 applied successfully to the three exact `test_` tables and `test_ai00_simulation_schema_migrations`; second application returned no changes. Canonical checksum `f4eb0d3c3dfb6f3fbf839bbab26ac31ba0598603f1fd7ed7ce39dbf6ea77971a`.

## Parent verification

- Python authorization/repository/audit/provider/opened-source binding/evidence: **67 passed**, 2 SQLite deprecation warnings, 49.67s. Uses isolated fixtures, not live COM.
- Frontend Main/page/native-layout/queue regression: **141 passed**, 0 skipped, 2.09s.
- Isolated frontend Vite build succeeded; page modules matched source byte-for-byte and built HTML contained the local-route marker.
- Connector final suite pending after independent review corrections; earlier 367-pass run is superseded.
- Broader frontend limitations reported by worker: `npm test` stops at a pre-existing missing craft fixture; old host-manager test also fails against HEAD's manager; bypass scanner retains two pre-existing violations, not waived.
- Timing caveat: protocol `journal_ms` measures admission flush only, and `total_ms` is captured before terminal outcome fsync so the retained response is deterministic. Neither is full UI latency. Real acceptance must time caller click-to-response; `com_ms` includes STA queue time.

## Independent adapter review

Review found ambiguous active-document adoption during native open, insufficient active-document checks around writes, unbounded cold occurrence enumeration, and missing hot-path counter assertions. Corrections and regression verification are in progress; earlier test counts are not final acceptance.

## Acceptance still required

- Final integrated .NET, Python, page/Main protocol tests and frontend build.
- Additive migration restricted to `test_` tables and exact runtime package/asset verification.
- Real diagnostic four-action execution, durable audit receipt, and renewal.
- Cold mapping separated from 100 visibility and 100 selection response samples.
- Pixel-change timing is separate from response timing; no claim of instant rendering without observation.
