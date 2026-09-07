# Task 4 report — possession pairing, runtime-session fencing, governed takeover

Status: implemented and committed. Implementation commit: `77e9f7288` (`feat: fence App runtime pairing and sessions`).

## Change classification

Additive v2 transport and persistence plus a new confirmed user Capability. Legacy v1 pairing, binding, health, wake, plan, and artifact routes remain available and isolated. No Knowledge definition, frontend, release catalog artifact, runtime evidence, or approval evidence was changed or generated. Nothing was pushed, merged, published, or delegated.

## Authoritative context inspected

Read the Task 4 brief, Task 3 report and CAS implementations, protocol v2 cryptographic validation, migrations 0005/0007/0008, Simulation pairing/runtime providers and descriptor/schema registration, HTTP routes, gateway authorization/approval policy, ownership/inventory metadata, and pairing/storage/HTTP/ownership/domain-boundary tests. Used the requested existing worktree. The worktree contains no AGENTS.md. Applied TDD, ponytail, verification-before-completion, and systematic debugging when a broader check failed. The AI00 governance skill's literal Git-root-name gate excludes the named worktree; explicit task governance boundaries were still followed.

## Reuse, atomicity, ownership

Reused protocol v2 P-256 public-key parsing and low-S IEEE-P1363 ECDSA signature decoding. Reused Task 3 session registration, takeover, normal lease/outcome and recovery-session CAS methods. All runtime mutations continue to serialize on the device row. App pairing storage remains separate from v1 pairing and binding tables.

The new `workmanship_sim_connector_runtime_challenges` table has an explicit Simulation owner in both governance files. Updated their counts by one without repairing unrelated pre-existing inventory omissions. Migration 0009 passes the production migration ownership/DDL validator.

## Plan corrections

1. Task 3's committed 0008 migration contained public keys and session hashes but no persistent device credential hash, runtime type, or separate signing-challenge lifecycle. Added **0009_connector_app_auth.sql** rather than rewriting 0008. It adds credential hashes, Electron runtime type, heartbeat timestamp, pairing signing-challenge hash/expiry/consumption, a short-lived registration-challenge table with explicit protocol/key/scope pins, and the takeover instance reservation. Existing v2 rows without device credential hashes cannot authenticate through the new service.
2. Task 3 `force_takeover` returned a raw bearer token. Following the parent ruling, confirmed takeover now uses its new `require_registration=True` mode: within the same transaction it expires the generated session immediately, reserves the requested instance, and discards the raw token. The Capability returns metadata only. The reserved instance must authenticate its device credential and a fresh device signature before receiving a new raw session token once. Other instances fail with `runtime_instance_reserved`.
3. The stale HTTP route-set assertion omitted the existing wake and artifact-content routes. The assertion now includes both valid legacy routes and every new v2 control-plane route.
4. V2 browser pairing actions use the existing approve/summary/cancel Capability IDs at major version 2, preserving v1 contracts. Device pairing request/activation and runtime control are authenticated possession/token transport, not alternate user business commands.

## Implementation

### Two-key App pairing

`PairingService.request_v2(device_signing_jwk, bootstrap_encryption_jwk, nonce)` creates a five-minute `created` pairing with independent signing and RSA-decryption challenges. It stores public keys and SHA-256 nonce/challenge hashes only. The signing JWK is a closed public P-256 JWK (`kty`, `crv`, `x`, `y`); the RSA JWK is `kty=RSA`, `alg=RSA-OAEP-256`, `n`, `e`, with a 2048–4096-bit key. Private/extra signing-key fields are rejected by the shared protocol parser. Device key IDs derive from the canonical public JWK.

The confirmed `simulation.connector.pairing.approve@2` binds the pairing to the authenticated user and tenant with version CAS (`created -> user_bound`). Summary/cancel @2 enforce the bound user/tenant. Activation requires the original signing challenge, its valid P-256 signature, and the separately decrypted RSA challenge. It inserts the active device and consumes the pairing atomically (`user_bound -> activated`). A random 256-bit device credential is SHA-256 hashed in storage and delivered only inside a hybrid RSA-OAEP-SHA256/AES-256-GCM envelope addressed to the disposable RSA key. Activation returns no plaintext credential.

Activation, cancellation, and observed activation expiry discard the bootstrap JWK and challenge hashes. The RSA column is non-null in 0008, so discarded state is the empty JSON object. Credential envelope storage remains empty; activation is single use, including a second call after successful activation. Failed proofs, owner/tenant mismatches, nonce replay, cancellation, expiration, and second activation are audited. SQL timestamps are normalized to UTC at the repository boundary before Capability serialization.

### Runtime sessions

`RuntimeSessionService` owns trusted server time. Registration requires both the device credential and a fresh device signing proof. A challenge expires in 60 seconds and is consumed with exact device, generation, instance, runtime type, device key ID, and optional recovery-plan pins. Normal sessions are 256-bit random secrets, valid for up to five minutes; only SHA-256 hashes are persisted. Registration returns raw `session_token` once, and the Task 3 dataclass excludes it from repr.

Normal authentication checks device, active v2 protocol/status, generation, current instance, token hash, permitted `electron` runtime type, and expiry. Heartbeat, session renewal, plan leasing, normal Outcome, and wake all use this authentication. Writes recheck the session within storage transactions; the wake socket reauthenticates after every wait before sending another hint. Session renewal returns only expiry and cannot resurrect an expired session. Outcomes require the persistent device P-256 signature.

### Governed takeover

`simulation.connector.runtime.takeover@1` is a Simulation-owned, web-only, confirmed write Capability with `simulation.use`. Input is `device_id`, `expected_generation`, `runtime_instance_id`, and a nonempty bounded `reason`. The handler checks authenticated user/tenant ownership, and storage rejects unresolved v1 or v2 leased/executing/unknown/manual-review work. CAS increments the generation by exactly one against the observed old instance/hash. Prior and new instance identities, actor, and reason are audited in the transaction. Output/evidence contain only device ID, generation, reserved instance, and a logical audit reference.

### Reconciliation-only service path

Recovery registration requires the device credential, fresh signing proof, an expired normal session, and a named unknown/manual-review plan. Task 3 may first mark an expired leased/executing plan unknown. The random recovery token is persisted only as a hash and bound to that plan, recovery instance, execution generation/session, and expiry. It cannot authenticate normal wake, heartbeat, lease, renewal, or Outcome calls. Probe and reconciliation routes accept the named-plan recovery token, and reconciliation validates the device signature before calling Task 3 `mark_reconciled`.

The probe transport currently returns the immutable named original plan as **context**. It does not grant a normal execution lease or authorize replaying original mutation steps. Task 5 must implement the read-only probe and evidence authorization policy before real recovery is enabled; this task does not claim that policy or runtime execution evidence is complete.

## Interfaces for later tasks

Normal service calls:

```python
challenge = service.challenge(device_id, device_credential, generation, instance,
                              runtime_type="electron")
session = service.register(device_id, generation, instance,
    device_credential=device_credential, runtime_type="electron",
    challenge=challenge["challenge"], signature=low_s_p1363_signature)
service.authenticate(session.session_token, device_id=device_id, generation=generation,
                     runtime_instance_id=instance, runtime_type="electron")
```

For recovery, include `plan_id` when issuing the challenge and use `register_reconciliation` with the same plan pin. This returns `session_token`, `scope=plan_reconciliation`, expiry, device/generation/recovery-instance/plan metadata. Only the corresponding probe/reconciliation service path accepts it.

HTTP prefix: `/api/v1/simulation/connectors/v2`.

- `POST /pairings`, `POST /pairings/{pairing_id}/activate`
- `POST /runtime/challenge`, `POST /runtime/register`, `POST /runtime/reconciliation/register`
- `POST /heartbeat`, `POST /runtime/renew`
- `POST /plans/lease`, `WS /plans/wake`
- `POST /plans/{plan_id}/outcome`, `GET /plans/{plan_id}/probe`, `POST /plans/{plan_id}/reconcile`

Device challenge/registration uses `X-AI00-Device-Credential` and a closed body containing device ID, generation, runtime instance ID, runtime type, optional plan ID, and (for registration) challenge/signature. Normal registration rejects a plan scope; recovery registration requires it. Runtime-authenticated routes require all five headers: `X-AI00-Device-ID`, `X-AI00-Runtime-Generation`, `X-AI00-Runtime-Instance-ID`, `X-AI00-Runtime-Type`, and `X-AI00-Runtime-Session`. Browser bearer identity alone cannot issue or use a runtime session. User takeover remains behind the Capability gateway; no takeover HTTP bypass was added.

## Verification evidence

Observed red phases:

- Initial possession test failed because the new App pairing repository did not exist.
- New route-set, browser rejection, and takeover registration tests failed before their route/provider implementations.
- Exact ownership test failed before adding the challenge table owner.
- UTC wire-output regression failed with `2026-09-07 12:05:00` before repository timestamp normalization.

Final focused command:

```powershell
python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_pairing_sql.py backend/tests/test_connector_runtime_sessions_v2.py backend/tests/test_simulation_connector_http_api.py backend/tests/test_simulation_connector_capability_ownership.py backend/tests/test_simulation_connector_runtime_v2_sql.py backend/tests/test_simulation_connector_data_migration.py backend/tests/test_simulation_domain_boundary.py -q
```

Result: **119 passed, 58 skipped**, exit 0. Skips are the opt-in native MySQL cases; `AI00_SIMULATION_TEST_DB_URL` is not configured. SQLite uses actual SQL transactions and a dialect adapter, including a two-thread registration race. It is not native MySQL row-lock evidence.

Coverage includes actual P-256 signatures, RSA challenge and credential-envelope decryption, hashed credentials/tokens, nonce/signature replay, owner/tenant mismatch, expiration and cancellation audits, stale-instance fencing, reserved-instance takeover, unresolved-work rejection, secret-free Capability output/evidence, the real gateway's missing-approval rejection before mutation, HTTP identity pins, browser-token rejection, recovery scope, and recovery-token rejection by WebSocket wake and all normal control-plane endpoints. Existing v1 pairing/storage/HTTP tests passed.

`git diff --check` passed, and changed runtime Python modules parsed successfully. The production migration validator accepts 0009 and the explicit challenge-table owner check passes.

Broader check:

```powershell
python -m pytest backend/tests/test_domain_table_ownership.py backend/tests/test_simulation_domain_boundary.py -q
```

Result: **8 passed, 1 failed**. The failure is the same committed-baseline global inventory mismatch reported by Task 3. Read-only `git show HEAD:<file>` comparison confirmed the nine pre-existing inventory omissions: `workmanship_agent_capability_outbox` plus Simulation connector bindings, enrollments, health, heartbeat_audit, legacy_commands, pairings, plans, and projection_outbox. Task 4 adds its new table to both files and does not alter those unrelated omissions.

## Self-review

Reviewed the complete diff against the brief and the parent reservation ruling. Confirmed no v1 endpoint removal, no plaintext device/session/recovery credential storage, no user-token route bypass, exact scope on consumed registration proofs, atomic device-first runtime replacement and audit, discarded takeover bearer token, and secret-free Capability output/evidence. Corrected the UTC serialization regression found during review. No remaining Task 4-specific test failure is known.

## Governance status

- `machine_passed`: focused Task 4/related suites and migration/owner policy checks passed, subject to explicitly recorded skips and the unrelated global inventory failure.
- `human_approved`: not claimed. Task instructions authorized implementation; they are not a runtime approval or release approval.
- `runtime_verified`: not claimed. No live App, Feishu user, production DB, persistent approval service, or native MySQL row-lock execution was exercised.

## Concerns and remaining integration work

- Native MySQL migration/row-lock behavior remains unverified until the opt-in test database is configured.
- Catalog publication/governance activation is untouched; new user Capability versions need the later planned release workflow.
- Task 5 owns read-only probe/evidence authorization, active-session reconciliation policy, v2 dispatch/signing, and any plan-lease renewal semantics. Current recovery plan context must never be treated as an execution lease or mutation replay authority.
- No App frontend or live runtime consumes these contracts yet; client JWK export must provide the closed public-key wire fields, and signatures use the existing v2 low-S P1363/base64url format.
- The global ownership/inventory mismatch remains a pre-existing unrelated finding.
