# Task 5 — Connector v2 cloud plans, outcomes, and reconciliation

Status: implemented and self-reviewed. Commit subject: `feat: govern Connector plan and outcome v2`.

## 1. Change classification

Compatible backend addition to the existing v2 storage/session work (through 5ced4b869). The closed v1 plan/outcome models, HMAC lease path, and v1 queue Capability contracts remain unchanged. No frontend, Knowledge governance debt, approval records, release publication, push, merge, or subagent dispatch was performed.

## 2. Authoritative context inspected

Read the Task 5 brief, closed Python v2 contracts and dedicated protocol vectors, v1 control plane, v2 runtime session service, device/plan/recovery/audit persistence, migrations 0005/0008/0009, exact table ownership registry, outbox worker, governed Simulation runtime client, outcome Capability providers, capture/materialization/document-snapshot workflows, and their existing tests. The AI00 governance skill's Git-root basename scope gate does not match this named worktree; nevertheless, the new table is explicitly registered to Simulation and its migration is validated.

## 3. Reuse, atomicity, and ownership

Reused the existing P-256 protocol verifier/canonicalizer and installed cryptography package. No new dependency. Device-row locks remain the common serialization boundary. Current device key ID, low-S P1363 signature, tenant/device/generation/execution-instance/session/lease/plan hash, ordered step results, and monotonic device journal sequence are checked inside the outcome transaction. Exact duplicate outcomes remain idempotent. The transaction writes the outcome, journal cursor, audit record, and v2 projection intent together; constraint-failure testing confirms rollback of all three mutable state records.

Migration 0010 adds `last_journal_sequence` to runtime devices and a separate `workmanship_sim_connector_runtime_projection_outbox`. This avoids mixing 256-character binary v2 identifiers with the legacy outbox's 128-character identifiers. Existing worker operations select the v1 or v2 tables through a fixed protocol option.

## 4. Implementation boundary and interfaces

- `PlanSigner(secret_provider, key_id=..., clock=...).sign(plan)` loads a cloud key record by key ID. Records contain a P-256 private key object, `not_before`, `not_after`, and `revoked`. Issuance checks both current key validity and the plan interval, finalizes key metadata and the hash, then signs. `from_jwk` rejects import; no private key is exported to a response, credential, log, or new fixture.
- `ConnectorControlPlane.queue_v2(plan, context, session_token=None)` checks owner/tenant and binds the current Electron generation/instance before signing. A cloud caller uses a server-read session-token hash snapshot, so cloud issuance does not need the Connector's plaintext token. Storage checks that snapshot again under lock.
- `OutcomeVerifier.verify(outcome, device_jwk)` delegates to the strict v2 signature contract. Outcome persistence additionally validates the registered key ID and all runtime/lease bindings under lock. `RuntimeSessionService.outcome` and `ConnectorControlPlane.complete_v2` reach this shared path.
- Equivalent input is compared within device/tenant/actor/capability/major-version scope using `normalized_input_hash`, under the device lock. Queued, issued, unknown, manual-review, and successful equivalents block a fresh plan even with a new idempotency key. Resolving an unknown effect to `failed_without_effect` permits replacement; resolving it to `succeeded` does not.
- The projection worker accepts `--protocol v2`; the default remains v1. Only the worker invokes the existing governed domain projector. The v2 outcome Capability provider requires a matching verified stored outcome and an active projection claim. Capture, materialization, and document snapshots retain the exact persisted v2 plan and map wire statuses to existing aggregate statuses. Manual review remains an unknown aggregate state. A terminal result before the capture step now stops the v2 capture workflow.

Recovery probes return a server-derived context, never the original executable plan:

```text
scope = read_only_post_condition_probe
plan_id, plan_hash, lease_id
device_id, tenant_id, runtime_generation, runtime_instance_id
probes = [{step_id, probe_id}]
nonce
```

The nonce binds the original server-stored lease/context to the authenticated recovery session (or the still-live original session). Each device-signed reconciliation step result must include the matching `nonce`, declared `probe_id`, and `classification` (`succeeded`, `failed_without_effect`, or an inconclusive value). Successful capture/snapshot evidence can include `observed_result`, which is validated by the domain workflow before projection. `ReconciliationService.reconcile(plan_id, probe_result)` classifies absent/inconclusive evidence as `manual_review_required`; the repository persists the verified transition. A signed normal success result without probe evidence cannot clear uncertainty. Recovery tokens still cannot lease or execute original mutations, and the stored original lease identity is required independently of any local journal. Reconciliation waits while the prior outcome's projection is actively claimed.

## 5. Verification evidence

TDD: observed initial missing-signer failures, then concrete failures for accepting an unregistered device key, permitting equivalent unknown input, returning the executable recovery plan, lacking v2 worker dispatch, and rejecting v2 domain projection. Added failing tests for cloud issuance without the Connector token, live-session reconciliation, observed-result projection, and terminal failures before capture; implemented each correction and reran the relevant selection.

Final command:

```powershell
python -m pytest backend/tests/test_connector_execution_plan_v1.py backend/tests/test_connector_execution_plan_v2.py backend/tests/test_connector_runtime_control_plane.py backend/tests/test_simulation_connector_outcome_capabilities.py backend/tests/test_connector_reconciliation_v2.py backend/tests/test_simulation_connector_runtime_v2_sql.py backend/tests/test_connector_runtime_sessions_v2.py backend/tests/test_simulation_connector_projection_worker.py backend/tests/test_simulation_capture_workflow.py backend/tests/test_simulation_document_snapshot_workflow.py backend/tests/test_simulation_connector_http_api.py backend/tests/test_simulation_connector_data_migration.py backend/tests/test_simulation_connector_capability_ownership.py backend/tests/integration/test_simulation_connector_projection_mysql.py -q
```

Result: **177 passed, 73 skipped**, 13.20 seconds. Skips are the native MySQL selections requiring `AI00_SIMULATION_TEST_DB_URL`. SQLite exercises real SQL transactions with dialect translation and serialized writers; it is not evidence of native MySQL row-lock behavior. A real Capability Gateway test projects a verified v2 materialization outcome through the registered provider. Protocol tests cover malformed/high-S signatures and mutations; SQL/session tests cover identity mismatches, expired sessions, recovery scope, duplicate completion, and rollback. Migration 0010 passes the owner policy validator. `git diff --check` passes (Git emits only configured LF/CRLF notices).

## 6. Governance status

- `machine_passed`: the stated local test selection and migration/whitespace checks.
- `human_approved`: not asserted or synthesized.
- `runtime_verified`: local SQLite/Gateway evidence only; production deployment, native MySQL, and an Electron/VisMockup runtime remain unverified.

## 7. Self-review and remaining concerns

Self-review traced the cloud session snapshot through signing and insertion, current-key verification through the transaction, replay handling before journal advancement, outbox reset on reconciliation, original-lease recovery binding, and exact-plan domain projection. Confirmed that failed outcome/audit transactions leave no journal or outbox residue and that successful reconciliation still blocks equivalent replacement. Updated an existing registration-set test for the Task 4 takeover Capability and upgraded old storage-only test outcomes to genuine device signatures/evidence rather than weakening production checks.

Deployment/follow-on integration must configure the cloud secret-provider callable and a `PlanSigner` on the v2 issuing control plane, apply migration 0010, and launch the v2 projection worker. The default control plane fails closed without a signer; no environment-secret or HMAC fallback is introduced. Existing v1 producer Capability wrappers remain v1; new v2 producers use the explicit `queue_v2` interface. Connector-side declared-probe dispatch and public-key trust-chain delivery remain later tasks. Native MySQL/OceanBase behavior remains unverified. Equivalent-input lookup currently scans one device's retained plans under its writer lock; an indexed normalized-input projection is the upgrade path if per-device history becomes large.

## Fix round 1 — review corrections

This section supersedes the original recovery evidence format above. Reconciliation no longer accepts or fabricates a device-signed normal execution Outcome. The normal v1 and v2 execution contracts and v2 execution-prefix validation are preserved.

### Dedicated signed evidence and server reconciliation result

`ConnectorReconciliationEvidenceV2` is a closed, strict record exposed by the `/v2/plans/{plan_id}/reconcile` HTTP body schema. Every field is required:

```text
protocol = ai00.connector.reconciliation-evidence.v2
scope = read_only_post_condition_probe
plan_id, plan_hash, lease_id, tenant_id, device_id
runtime_generation, runtime_instance_id          # original execution identity
recovery_instance_id, recovery_session_id, nonce
probes = [{step_id, probe_id, classification, observed_result}]
journal_sequence, reported_at, device_key_id
signature_algorithm, signature
```

The protocol marker separates its signature domain from normal Outcomes. The existing low-S P1363/P-256 signature primitives validate the evidence against the registered current device key. The server checks all context bindings under the existing device lock. Duplicate, reordered, and undeclared probes are rejected; missing, mixed, or inconclusive required proof yields `manual_review_required`.

Probe responses return the safe identities/scope above and an explicit ordered `required_probes` set instead of executable steps or the original plan. `recovery_session_id` and `nonce` are derived from the authenticated server-held session binding. A replacement runtime can construct the entire evidence record from this response and its read-only probe results without its predecessor's local journal. With an original signed Outcome, the server derives the invoked prefix itself and does not demand normal results for later uninvoked steps. With no original Outcome, all declared side-effect probes are required. Read probes do not veto proofs that all invoked writes had no effect; pure read plans retain their declared probe path.

Only complete absence proof for all required side effects produces `failed_without_effect`. Complete success proof produces `succeeded` only when later uninvoked work does not remain and relevant snapshot/capture result validation succeeds. Otherwise the result remains manual review. This supports multiple writes and read-before-write crashes without forcing probe observations through normal execution-prefix rules.

The persisted projection record is `ConnectorReconciledOutcomeV2`, discriminated by `record_type=server_reconciliation_v2`. It contains the untouched original signed Outcome (or null for a crash), the complete signed reconciliation evidence, and explicit server-derived projection facts. It has no top-level device signature. Original outcome audit rows remain untouched. Projection payload parsing and the governed provider recognize this separate record, and a manual-review snapshot cannot be projected as successful merely because one probe succeeded.

### Bounded Gateway identifiers

For v2 only, trace IDs use `connector-plan-` plus SHA-256(plan_id), and idempotency keys use `connector-projection-` plus SHA-256(plan_id + NUL + outcome_hash). Their lengths are 79 and 85 characters respectively. The existing request ID is also bounded. The v1 identifier format is unchanged. Real Gateway tests cover both normal and reconciled projections with 184- and 256-character plan IDs and assert the lengths and hash bindings.

### RED/GREEN and final evidence

- RED: the original recovery context lacked `recovery_instance_id` for the multi-write/crash test, and a valid 184-character plan ID failed Gateway validation with `idempotency_key` longer than 255 characters.
- GREEN: dedicated evidence tests now cover a stored signed prefix containing a successful read/write before an unknown write, crash-before-outcome with two writes, read-before-write crash, later uninvoked writes, complete absence/success, missing/mixed/inconclusive proof, closed-field validation, wrong context/signature, and preservation of both signed records.
- RED/GREEN: invalid snapshot proof originally reached the success projection branch; it now stays in manual review. A declared read probe originally polluted required write-absence evidence; required side-effect selection now avoids that conflict.
- HTTP tests reject a normal Outcome at the reconciliation endpoint and reconciliation evidence at the normal Outcome endpoint, while accepting and verifying dedicated evidence through the real service and SQL transaction.
- Final broader command: the same 14-file selection recorded in section 5. Result: **192 passed, 87 skipped**, 16.36 seconds. All skips require native MySQL configuration; SQLite/Gateway evidence does not replace native MySQL verification. `git diff --check` passes.

### Self-review and remaining concern

Reviewed the normal/evidence protocol split, exact original-lease and recovery-session bindings, required-probe ordering and coverage, original signed record preservation, server-result parsing, domain validation before success classification, and bounded Gateway values. No approval or release state was synthesized.

The reviewer's claim-owner observation remains: the governed v2 provider checks that the exact stored plan/outcome has an active outbox claim, but it does not bind the invoking Gateway consumer to that claim's `lease_owner`. The current provider payload and trusted Gateway context do not carry a worker claim identity. Adding a caller-supplied owner would not establish that proof; a real correction needs a trusted claim propagated through the worker/Gateway interface. Per the requested scope, this was documented rather than broadening interfaces. Native MySQL and production secret/worker deployment remain unverified as before.
