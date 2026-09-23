# Viewer open short path — implementation evidence (in progress)

Scope: approved 2026-09-22 short-path spec/plan. Existing backend and frontend linked worktrees on test; no commits/push. No running process restarted or model opened by this change yet.

## Implementation

- bind@3 completes binding/source association and signed interaction grant/evidence in the binder's single transaction. Borrowed authorization cursor is not closed or committed. Existing majors remain registered.
- Completion key includes document, launch operation, expected revision and Main nonce; replay returns the immutable result even after receipt freshness expires. Fresh completion still verifies signed launch evidence and current runtime/source scope. Expired grants require renewal.
- Dedicated prepare_document validates the installed interaction and reads native identity on STA, without cloud command dispatch or document opening. Main checks before and after attachment.
- Main-owned completion session keeps grants and native target private. Page uses completion instead of independent identity/scope reads and blocking workspace refresh. Scoped state update fences older reads.
- Prepared attachment starts offscreen and remains hidden until Main's post-attach check. Original recovery APIs retained.

## Verification so far

- RED: missing bind@3 registration, issuer proof checks, prepare_document behavior, Main completion, prepared native visibility, page short path and scoped store update observed before respective implementation.
- Backend focused suites: **239 passed, 149 skipped**, 29 SQLite datetime deprecation warnings, 225.37s. Includes SQL source binding/authorization/audit/connector tests. Native MySQL cases skipped (no configured MySQL test database); SQLite does not prove MySQL lock behavior.
- Connector full suite outside sandbox: **448 passed**, 0 skipped, 12s. Sandbox run fails Windows DPAPI/ACL/pipe tests; not counted as product failures. One newly extended pipe test initially incorrectly reinstalled the same grant generation; corrected to test runtime mismatch after existing operations, full suite rerun green.
- Frontend focused suite: **78 passed, 1 failed**. Remaining failure is `runtime scanner requires an owned exception for the local iframe transport`: bridge source hash changed; allowlist has NOT yet been updated or waived.
- `npm run test:electron-security`: earlier checks pass, then `test_electron_tray.js` fails exact-source regex expecting unconditional production AppUserModelID; existing local test-app conditional predates this patch.
- `npm test`: stops at `test_craft_rule_capability_migrations.js` missing sibling fixture under `.worktrees/workmanship-backend/backend/tests/fixtures/craft_rule_reference_projection.json`. Not a full pass.
- Backend project `python -m pytest -q --maxfail=1`: collection blocked at `backend/tests/test_base_self_annotation_routes.py`, `ProviderTrustError: provider_artifact_mismatch: simulation`. Official manifest intentionally unchanged; local unpublished manifest must be generated for deployment.

## Pending

### Independent review follow-up

Russell reported no Critical and five Important findings. Four have implementation fixes with regression evidence; the native document/window association finding remains unresolved, so deployment is not approved by this report.

- Lost local transport: HostManager now replaces a stopped ViewerInteractionPipe only while the supervised host remains ready. The new transport verifies the server PID again; the original execute returns outcome_unknown and is not replayed. The production manager harness reproduced reuse of the stopped instance before the fix. Its old single-timer stub was corrected to retain the supervision timer rather than replace it with the Teamcenter control timer; the auth stub now implements the actual onStateChange seam. `node scripts/test_electron_connector_host_manager.js` exits 0, including startup-order tests.
- Lost renewal response: a failed renewal attempt retires only the local interaction nonce. Retry uses a fresh authorized local interaction with the retained committed business completion, without another bind or launch. New test failed with reused nonce, then passed.
- Late successful completion: retain the per-owner business completion until a different launch/navigation instead of deleting it before page acknowledgement. Closing the local session allows a fresh local interaction using that result. New test reproduced two bind calls, then passed with one.
- Bridge timeout/environment switch: track the outstanding Main open independently of display phase; close sends cancelOpen after a bridge timeout. Real MessageChannel timeout/late-result regression coverage passes.
- Unresolved: attachPrepared still chooses the native renderer by PID, whereas prepare_document verifies COM DocHandle. A→B→A document switching can evade two COM snapshots. No claim is made that a COM DocHandle is a Windows HWND. Read-only inspection of the installed Siemens VisAutomation.tlb confirmed DocHandle, viewHandle and ViewByHandle, but did not establish a documented HWND mapping. Do not deploy before this association is resolved and tested.

Fresh verification: Main/controller **31 passed**; bridge timeout/late-result subset **4 passed**; scoped `git diff --check` passed (CRLF warnings only). These are regression tests, not live VisMockup performance measurements. Runtime, current login and existing open documents were not restarted or changed. Allowlist/source-hash gate and project-wide failures above remain outstanding.

Fresh independent review dispatched; resolve Important/Critical findings, extend retry/late-owner tests, finish full page regression and exact owned transport evidence. Then build separate package, verify hashes/served functions, deploy only reviewed artifacts, and measure diagnostic bolt twice with same login generation. No speed improvement claimed yet; 3–5s remains an unverified warm/cached target. Current launch RPC alone previously took 6.3–7.4s.

Governance: AI advisory only. Full machine gate not passed; no formal release human approval or runtime verification for this revision. User approved implementation plan, not a fabricated release gate. Rollback remains current `.runtime/connector-recovery-final-20260922` package and existing manifest; it has not been switched.
