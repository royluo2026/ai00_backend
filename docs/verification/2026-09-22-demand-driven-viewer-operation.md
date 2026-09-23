# Demand-driven viewer operation — verification record

Status: implementation and isolated verification complete through Task 5; local test build and deployment performed. Controlled live model validation remains pending application login. This record is not a release approval.

## Change boundary

- The model-tree click is now the intent: Main opens the exact Teamcenter source only when its runtime slot is absent, binds the resulting runtime identity, embeds it, maps the requested occurrence and continues the original absolute operation.
- Selecting a simulation environment performs no launch. Right-click “open” uses the same readiness path rather than a separate document-identity workflow.
- Existing prepared slots activate by exact document session/window token and execute locally. They do not call launch@2 or bind@3; grant expiry alone may call authorize@1.
- Concurrent readiness for one workspace/document is single-flight. Same-target absolute page intents coalesce before dispatch; different targets retain order.
- A single explicit desktop confirmation may cover open, association and the triggering operation for that exact in-flight intent. It is not retained for another scope or later intent.

## Capability compatibility

No Descriptor, Provider implementation, schema, migration, Catalog or official manifest was changed for this consumer-flow revision.

| Capability | Major | Existing version GID | Confirmation | Idempotency |
|---|---:|---|---|---|
| `simulation.teamcenter.visualization.launch.request` | 2 | `cv2_cce43b004671f2f8e0b4edfd` | user | required |
| `simulation.environment.online_source.live_document.bind` | 3 | `cv2_1f92da28d1c518cd7ca6b230` | user | required |
| `simulation.viewer.interaction.authorize` | 1 | `cv2_59f6ec1e05ca6e2b8fdef576` | none | required |

bind@3 still requires `expected_workspace_row_version`, a Main-owned idempotency key and session nonce. Its stored result is immutable on replay and a changed nonce conflicts rather than allocating another grant.

## Failure and retry semantics

- `open_not_started`: no launch side effect; a later invocation creates a fresh launch attempt.
- `open_outcome_unknown`: launch identity is frozen; the same intent does not redispatch launch.
- `opened_binding_pending`: retains the opened-source operation and retries completion only.
- `window_association_unavailable`: retains the opened-source operation and signed completion; retry does not reopen or rebind.
- `mapping_pending`: retains the ready slot and does not relaunch.
- `busy`: retains the exact prepared slot; no alternate document selection or relaunch.
- `outcome_unknown`: freezes subsequent writes in that interaction; no automatic replay or cloud fallback.
- `runtime_invalid`: drops the stale slot. It does not retry the failed operation; a later distinct user intent may open again.

## Static and isolated evidence

- Provider/contract command:
  `python -m pytest plugins/simulation/tests/test_viewer_open_completion.py plugins/simulation/tests/test_viewer_opened_source_binding.py plugins/simulation/tests/test_viewer_interaction_provider.py backend/tests/test_viewer_interaction_repository.py backend/tests/test_viewer_interaction_audit.py -q`
  Result: **76 passed**, 29 SQLite datetime deprecation warnings, 19.92s. No native MySQL case ran in this command.
- Main/runtime-slot/capability/native-controller command:
  `node --test --test-isolation=none packages/core/electron/viewer_interaction_client.test.js packages/core/electron/viewer_runtime_slots.test.js packages/core/electron/capability_client.test.js packages/sim-plugin/electron/vismockup_controller.test.js`
  Result: **48 passed**, 0 failed, 212.779ms.
- Page demand-driven command (including tree-cache integration): result **96 passed**, 0 failed, 2.214s.
- Connector full suite from Tasks 1–2: **461 passed**, 0 skipped, in the current Windows user context.
- Native isolated Win32 harness passed duplicate-title, two-MDI-parent, marker replacement, exact activation readback and HWND lifecycle reuse cases.
- Electron capability boundary, plugin lifecycle security and VisMockup native embed scripts each exited 0.

The repository-wide desktop scanner is not relabeled green: it reports two pre-existing blocked calls in `web/core/business_facade.js` and `web/main.js`, and its self-test expects the old `business_facade.js` allowlist hash. The task-owned local iframe transport remains covered by its exact file/call/source hash; no generic exception was added.

## Live evidence and governance

- Static verification: present as above.
- Native-isolated verification: present as above.
- Live validation of this revision: pending controlled deployment and diagnostic bolt test; no performance or end-to-end success claim is made here.
- `machine_passed`: unverified.
- `human_approved`: unverified. The user's product-direction approval is not a trusted `super_admin` approval of an exact Capability hash.
- `runtime_verified`: unverified until the deployed revision completes the controlled live sequence and its runtime/audit evidence is read back.

## Local deployment evidence — 2026-09-22

- Frontend `dist-test-governance` built; source/build SHA-256 matched for `viewer_interaction.js`, `live_document_bootstrap.js`, `live_document_adoption.js`, and `cad_sim.js`. Built HTML is transformed and is not asserted byte-identical.
- The initial Release Connector package rejected the local `--development local` arguments. `AppHostOptions.Parse` enables those arguments only in DEBUG. The local deployment was corrected to the separately published Debug package; production startup checks were not relaxed.
- Active package: `E:\Projects\ai00_v3\.runtime\connector-demand-driven-20260922-debug`.
- Host DLL SHA-256: `F84A9B4A96CF3DFCB0FDB30F9FFF17EB153F443A7C5F6B7A7FB1D2A9A1FF4787`.
- Adapter DLL SHA-256: `EB5B2FE74AB435B4F8889AF6578D008DA28F619EF3F7E1440D8F4CB2286ADF69`.
- Installed native module SHA-256: `6BCD1AD59D3FB5CA710DE908723F3958F74C08EEC97F4B15462359C753C78F98`, matching the isolated native build. `node scripts/test_mdi_selector_native.js --runtime` exited 0 again after deployment (compiled N-API and isolated Win32 tests; not live model evidence).
- Prior Connector package remains at `.runtime/connector-shortpath-window-20260922`; prior manifest/native module were copied to `.runtime/demand-driven-rollback-20260922-1836`. Earlier frontend rollback exists at `.runtime/shortpath-window-rollback-20260922/backend-dist`; it is not asserted to be an exact pre-deployment snapshot of this turn's source.
- Live readback initially confirmed Teamcenter `ready` and Connector `ready/healthy`, but AI00 application auth was `mode:none`. Environment loading returned `invocation_unavailable`, so no diagnostic model action or benchmark was dispatched.
- The application subsequently exited; cause unverified. At the user's request it was restarted: Electron PID `306344`, backend `/health` HTTP 200, Connector `ready/healthy`, log content root matching the Debug package above. AI00 login page is present and application auth remains `mode:none`. Teamcenter session after this restart has not been asserted restored.
- Exact model opening, window reuse, node control, hot-operation latency and screen-change timing remain **unverified**. No performance completion claim is made.

Existing VisMockup processes and unrelated documents must not be closed during deployment or validation.

## Controlled diagnostic findings — 2026-09-22 evening

- AI00 and Teamcenter login were restored. Selecting diagnostic workspace `227728039260360704` made no launch; the first tree show intent prompted for confirmation.
- Runtime command `vismockup-command-6f3bc4431472562ba8d121c0c5d491659a3e9efcef7681fe18711f6685a22223` completed with opened-source receipt for PID `164164`, document handle `586`. The page nevertheless reported `open_not_started`: Main expected Gateway `accepted/operation_ref`, while the real Provider returned `completed/data=OperationRef`. Consumer parsing now supports both, and malformed successful references are classified unknown rather than safe to relaunch. This Main fix is on disk, **not yet loaded by the running Electron process**.
- A compatibility recovery against that same command exposed a second defect: the iframe's 15-second timeout expired while the native bind confirmation was still waiting. `openFromLaunch` now uses the existing long readiness deadline; actual execute deadlines remain short. A behavioral test first failed with `interaction_bridge_timeout`, then passed after the change. No confirmation bypass was added.
- First refresh still executed the old bridge. After rebuild and another refresh, Runtime evaluation confirmed the actual loaded `frameAPI` includes `openFromLaunch` in the long-deadline branch. Do not infer deployment merely from source edits. A subsequent source URL revision was bumped to `20260922-demand-driven-3`; the last inspected iframe still had revision `-2` but contained the new timeout implementation.
- Targeted Main/capability/runtime-slot/page regression: **73 passed, 0 failed**. `npm run build:web:test-governance`: exit 0 (existing non-module script bundling warnings). The global desktop scanner still reports **2 violations**, unchanged task-external files as documented above.
- Full `npm test` first stopped at missing sibling backend fixture. Re-run with `AI00_BACKEND_ROOT` pointing to the actual backend worktree passed that stage but failed `scripts/test_simulation_p0_boundary.js:35`: “page initialization must probe the bound Connector without delaying business data”. The full suite is **not green**; this assertion needs reconciliation with the demand-driven initialization design before completion.
- Recovery remains at human bind confirmation. No duplicate source launch was issued in this recovery. Hot local operations, demand-driven reuse, latency and screen-change timing remain **unverified**. The 20.05-second first-click interval includes human confirmation and is not a native-load measurement.

### Confirmed recovery rejection and Main deployment

- After the user confirmed, recovery returned `launch_evidence_unavailable`, not success. Read-only invocation of the real evidence verifier against the persisted diagnostic command returned **`launch_evidence_stale`**. Receipt timestamp was `2026-09-22T10:53:41.718233Z`; verification time was `11:09:09Z`. Runtime generation, runtime instance and session-token hash still matched. The cause is the 120-second launch-evidence freshness rule, masked by the repository's generic error mapping; no identity mismatch or geometry-load delay was demonstrated.
- No write was replayed against this stale receipt and no signature/freshness check was bypassed. Its original document remains open. Long model opening and long confirmation delays versus the 120-second rule remain a known unresolved boundary.
- The 73 focused tests passed again. Exact AI00 Main PID `290208` was stopped and restarted from the inspected frontend tree as PID `340564`, loading the parsing fix. Connector readback is ready/healthy; AI00 Feishu authentication persisted. Siemens PID `164164` remains alive; no model was closed.
- Teamcenter displays logged out after Connector restart. The new complete demand-driven opening/control validation is blocked pending Teamcenter login; no hot-operation timings are claimed.

### Diagnostic live control — 19:19 onward

- After login, the real model-tree show click used Main-owned launch/bind. Command `vismockup-command-9e29d287a5b3e1155d842d7e3ffe049c78d66d3e9d64b874640e259f9f172319` succeeded and returned the existing bolt document `586` in PID `164164`; it did not create a second document handle. Source-side timing logs included dataset resolve 618ms, source load 565ms, FMS get files 66ms and native consumer 178ms (individual phases, not an asserted additive end-to-end duration).
- The next failure was `native_view_bounds_unavailable`: page bounds were only sent when already visible/associated. Readiness therefore could not perform its first native attachment. A scoped diagnostic staged the real viewport dimensions then resumed the SAME Main attempt. It completed in 2482.5ms, with the show command reporting local total 119.6ms / COM 108.9ms. No source launch was repeated by that resume.
- Four `executeIntent` actions succeeded: hide 371.4ms, show 358.0ms, highlight 343.3ms, unhighlight 454.2ms. An additional **100 sequential operations** (25 each hide/show/highlight/unhighlight) succeeded with **0 command errors**: response P50 **359.3ms**, P95 **417.1ms**, max **437.6ms**; local-command P50 **34.1ms**, P95 **58.0ms**, max **70.2ms**. These are command-response measurements, **not visible-screen-change measurements**.
- Page readback exposed `_liveDocumentContextUnavailable=true` despite Main readiness, so the placeholder remained visible. This explicitly prevents labeling the command benchmark as complete UI success. A new controller `onReady` callback reconciles the workspace row version and reuses the compatibility path's presentation finalizer. Bounds now stage independently of visibility, without revealing an unverified view. Behavioral regressions failed before these fixes and passed after them.
- Refresh reuse (without another launch) then failed `vismockup_visibility_invalid`: Main activation first hid an already-detached viewport, and the native API rejects visibility calls without an attachment. A focused regression reproduced this. Controller hide now returns its existing detached state when no parent exists; show still follows native validation. This desktop fix requires restart and was not in the measured 100-operation runtime.
- Latest targeted suite: **99 passed, 0 failed** across Main capability/client/slots, page interaction/native layout, and native controller tests. The updated test-governance frontend built successfully. Independent focused review requested. Complete refreshed UI, final deployed regression and observable screen timing remain pending; governance states are unchanged/unverified.

### Focused review and revised desktop load

- Reviewer found duplicated readiness: page `ensureReady` followed by Main `executeIntent` invoking readiness again, causing two activation/attachment cycles per click. Main now skips the second cycle only for its exact non-closed owned session, matching stored slot and active native owner; quarantine still rejects. Node resolution and execution retain grant/session validation. RED showed extra activate/prepare wire calls; GREEN shows only resolve/execute and expired authorization rejection. Reviewer re-read this condition and found no Critical/Important issue; real screen behavior remains outside isolated evidence.
- Final combined related suite: **142/142 passed**. Normal isolated execution of all cad_sim tests: **305/307 passed**, with existing stale asset revision assertions in `connector_recovery.test.js:395` and `teamcenter_entry_assets.test.js:10` still failing. An earlier no-isolation run had additional global-state interference and is not treated as the canonical all-page result. Full npm test also retains the earlier recorded initialization-boundary failure.
- Restarted the exact AI00 process after focused review: new Main PID `338716`. Connector ready/healthy, AI00 auth still Feishu; Teamcenter logged out. Siemens PID `164164` remained alive; no model was closed. This loads the detached-hide and duplicate-readiness fixes, but their deployed end-to-end model test is pending login. Prior 100-operation figures apply to the pre-shortcut runtime, not this final revision.
