# Governed Electron App Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one Windows x64 Electron application that preserves the current web UI, uses the cloud Capability Gateway for every business operation, and owns a hidden governed .NET ConnectorHost for VisMockup execution.

**Architecture:** Keep the backend, Gateway, Providers, database, and wake transport in the cloud. Package the existing Vite UI inside a hardened Electron shell; Electron main owns OAuth tokens and forwards only closed Capability invocations. A bundled .NET AppHost leases cloud-signed protocol-v2 plans, journals COM effects, signs outcomes with a DPAPI-protected device key, and is supervised by the Electron product lifecycle.

**Tech Stack:** Electron 41, Node.js CommonJS, Vite 4, AJV 8, Electron Builder 25/NSIS, Python 3/Pydantic/pytest, MySQL-compatible migrations, .NET 8 Windows/x64, xUnit, ECDSA P-256, RSA-OAEP-SHA256, Windows DPAPI, named pipes, Job Objects, VisMockup COM/STA.

**Spec:** `docs/superpowers/specs/2026-09-07-governed-electron-app-migration-design.md`

## Global Constraints

- The supported platform is Windows x64 only.
- The production artifact is one Electron/NSIS installer, one product entry, one update channel, and one AI00 tray presence.
- The cloud backend remains authoritative; no backend, business database, or business HTTP server is packaged locally.
- Every business read or write uses `/api/v1/capabilities/{capability_id}:invoke` or its governed streaming equivalent.
- Renderer, preload, Electron IPC, named pipes, and ConnectorHost cannot authorize or describe a local business command.
- Access and refresh tokens exist only in Electron main.
- ConnectorHost accepts only `ai00.connector.execution-plan.v2`; v1 remains isolated to the legacy runtime during the pilot.
- Plan signing uses a cloud-held ECDSA P-256 private key; ConnectorHost contains public verification keys only.
- Outcome signing uses a persistent current-user-DPAPI-protected device ECDSA P-256 key distinct from the disposable RSA bootstrap key.
- Protocol v2 uses RFC 8785 UTF-8 canonical JSON, lower-case hexadecimal SHA-256 plan hashes, IEEE-P1363 low-S signatures, unpadded Base64URL, and P-256 JWK public keys.
- COM timeout, cancellation after invocation, or process loss produces `outcome_unknown`; equivalent work stays blocked until reconciliation.
- VisMockup runs outside the AI00 Job Object and survives App shutdown.
- Third-party Electron plugin windows are disabled in the first release.
- No independent Connector Service, Connector tray, SessionHost product entry, Python Bridge, loopback business endpoint, macOS, Linux, or ARM64 artifact ships in the App distribution.
- `machine_passed`, Capability `human_approved`, `runtime_verified`, and technical release approval remain separate evidence.
- Gitea and GitHub are the only source destinations; do not push or publish to GitLab.

## Repository and ownership map

- **Frontend repository:** Electron main/preload, existing Vite UI, package manifest, Electron Builder configuration, UI and packaging tests.
- **Backend repository:** Capability Gateway and governance, Simulation Provider/control plane, SQL migrations, protocol fixtures, .NET ConnectorHost and adapters, release evidence.
- **Simulation owner:** pairing, device/runtime sessions, plan issuance, leasing, outcomes, reconciliation, VisMockup Capability handlers.
- **Capability governance owner:** desktop consumer registration, provider bindings, impact closure, generated Catalog/docs, Release Gate.
- **Electron main:** OAuth/token custody, fixed-origin Capability transport, windows/platform IPC, ConnectorHost supervision, update orchestration.
- **ConnectorHost:** device identity, runtime session, wake/lease/outcome, durable journal, STA adapter execution, diagnostic-only pipe.

## Delivery order and gates

Tasks 1-6 are cloud/governance prerequisites. Tasks 7-8 create the local runtime against the frozen v2 contract. Tasks 9-11 integrate the Electron product without changing UI structure. Task 12 packages and verifies the complete product. A task is merged only after its named tests pass; a later task may consume only committed interfaces from earlier tasks.

---

### Task 1: Close the immutable governance baseline

**Files:**
- Modify: `backend/tests/test_agent_runtime_closure_acceptance_evidence.py`
- Modify: `docs/acceptance/agent-runtime-capability-closure.json`
- Modify: `docs/acceptance/agent-runtime-capability-closure.normalized.json`
- Modify: `docs/acceptance/agent-runtime-capability-closure-evidence.json`
- Modify only when the domain owner chooses versioning: the authoritative Ontology descriptors that generate `ontology.concept.get@1`, `ontology.concept.resolve@1`, and `ontology.object.list@1`
- Create: `docs/acceptance/electron-app-stage-0-snapshot.json`

**Interfaces:**
- Consumes: backend baseline commit `561efece898d8cf5a78d6e3855c5669c8bbf619b`, frontend baseline `08222e876d0ab8a8c477e6d66b6bda66ac70af88`, Catalog Release `rel_6b7ac7cd21ed113da5a033e433f09a37`.
- Produces: immutable Stage-0 snapshot ID and passing deterministic Release Gate; it does not create human approval.

- [ ] **Step 1: Reproduce the blockers without rewriting evidence**

Run from the backend repository root:

```powershell
python -m pytest backend/tests/test_capability_v2_business_release_gate.py backend/tests/test_agent_runtime_closure_acceptance_evidence.py backend/tests/test_check_capability_v2_release_gate.py -q
python backend/scripts/audit_capability_business_rules.py
```

Expected: the three Ontology hash differences and missing Agent `business_governance` evidence are visible as failures or findings.

- [ ] **Step 2: Record the exact baseline snapshot before remediation**

Create `docs/acceptance/electron-app-stage-0-snapshot.json` with this closed shape:

```json
{
  "schema_version": 1,
  "frontend_commit": "08222e876d0ab8a8c477e6d66b6bda66ac70af88",
  "backend_commit": "561efece898d8cf5a78d6e3855c5669c8bbf619b",
  "catalog_release": "rel_6b7ac7cd21ed113da5a033e433f09a37",
  "findings": [
    "ontology.concept.get@1:business_definition_hash_mismatch",
    "ontology.concept.resolve@1:business_definition_hash_mismatch",
    "ontology.object.list@1:business_definition_hash_mismatch",
    "agent_runtime_closure:business_governance_missing"
  ]
}
```

- [ ] **Step 3: Apply the domain owner's Ontology decision**

If the meaning changed, add a new major Capability version and retain v1 unchanged. If the meaning did not change, regenerate the three hashes from the authoritative descriptors and attach the server-authenticated business approval for those exact hashes. Do not edit the legacy baseline to make the comparison pass.

- [ ] **Step 4: Regenerate Agent closure evidence through its existing builder**

Run the repository's acceptance generator and normalize the result, then update the evidence identity hashes. Verify `business_governance` names the exact Catalog Release and business-definition hashes rather than copying a prior pass result.

- [ ] **Step 5: Verify the baseline gate**

```powershell
python -m pytest backend/tests/test_capability_v2_business_release_gate.py backend/tests/test_agent_runtime_closure_acceptance_evidence.py backend/tests/test_capability_governance_release_gate.py backend/tests/integration/test_release_gate_full.py -q
python backend/scripts/check_capability_v2_release_gate.py
```

Expected: all deterministic checks pass. Report `human_approved` and `runtime_verified` from authoritative evidence; never infer them from pytest.

- [ ] **Step 6: Commit the baseline closure**

```powershell
git add backend/tests/test_agent_runtime_closure_acceptance_evidence.py docs/acceptance
git commit -m "governance: close App migration baseline findings"
```

---

### Task 2: Define protocol v2 and cross-language vectors

**Files:**
- Create: `backend/contracts/connector_execution_plan_v2.py`
- Create: `backend/tests/fixtures/connector_execution_plan_v2.json`
- Create: `backend/tests/test_connector_execution_plan_v2.py`
- Modify: `backend/contracts/__init__.py`

**Interfaces:**
- Produces: `ConnectorExecutionPlanV2`, `ConnectorPlanOutcomeV2`, `canonicalize_v2(value)`, `compute_plan_hash(plan)`, `verify_plan_signature(plan, jwk)`, and `verify_outcome_signature(outcome, jwk)`.
- Consumes: RFC 8785 bytes and the exact cryptographic projection in the approved spec.

- [ ] **Step 1: Write failing closed-schema and projection tests**

```python
def test_plan_hash_excludes_hash_and_signature_but_signature_includes_hash():
    raw = json.loads(VECTOR.read_text(encoding="utf-8"))["plan"]
    plan = ConnectorExecutionPlanV2.model_validate(raw)
    assert plan.compute_hash() == raw["plan_hash"]
    assert plan.verify_signature(TRUSTED_PLAN_JWK) is True
    with pytest.raises(ValidationError):
        ConnectorExecutionPlanV2.model_validate({**raw, "unknown": True})
```

- [ ] **Step 2: Run the tests and confirm v2 is absent**

```powershell
python -m pytest backend/tests/test_connector_execution_plan_v2.py -q
```

Expected: import or collection failure for `connector_execution_plan_v2`.

- [ ] **Step 3: Implement the closed records and canonical projections**

Use `ConfigDict(extra="forbid", strict=True)`. Implement these exact projections:

```python
def compute_plan_hash(value: Mapping[str, Any]) -> str:
    projected = {k: v for k, v in value.items() if k not in {"plan_hash", "signature"}}
    return hashlib.sha256(canonicalize_v2(projected)).hexdigest()

def plan_signature_bytes(value: Mapping[str, Any]) -> bytes:
    return canonicalize_v2({k: v for k, v in value.items() if k != "signature"})

def outcome_signature_bytes(value: Mapping[str, Any]) -> bytes:
    return canonicalize_v2({k: v for k, v in value.items() if k != "signature"})
```

Require `protocol`, every provenance/fencing field, ordered steps, `signature_algorithm="ecdsa-p256-sha256"`, key ID, and signature. Reject DER, padded Base64, high-S, wrong curve, unknown fields, and timestamp coercion.

- [ ] **Step 4: Check in deterministic accepted and rejected vectors**

The fixture contains `plan`, `plan_public_jwk`, `outcome`, `device_public_jwk`, `canonical_plan_without_hash_or_signature_hex`, `canonical_plan_without_signature_hex`, and rejection cases for mutation, DER, high-S, padding, downgrade, and an unknown field. Private fixture keys are test-only and carry the literal marker `TEST_VECTOR_PRIVATE_KEY_DO_NOT_USE`.

- [ ] **Step 5: Run v1 and v2 contract tests together**

```powershell
python -m pytest backend/tests/test_connector_execution_plan_v1.py backend/tests/test_connector_execution_plan_v2.py -q
```

Expected: both versions pass independently; no optional v2 field appears in v1.

- [ ] **Step 6: Commit the protocol contract**

```powershell
git add backend/contracts backend/tests/fixtures/connector_execution_plan_v2.json backend/tests/test_connector_execution_plan_v2.py
git commit -m "feat: define closed Connector protocol v2"
```

---

### Task 3: Add additive device, pairing, session, lease, and reconciliation storage

**Files:**
- Create: `backend/db/migrations/domains/simulation/0008_connector_app_runtime_v2.sql`
- Modify: `plugins/simulation/simulation_backend/data/connector_repository.py`
- Modify: `backend/governance/domain_table_ownership.json`
- Create: `backend/tests/test_simulation_connector_runtime_v2_sql.py`
- Modify: `backend/tests/test_simulation_connector_pairing_sql.py`

**Interfaces:**
- Produces: repository transactions `register_runtime_session`, `force_takeover`, `lease_v2_plan`, `complete_v2_plan`, and `mark_reconciled`.
- Invariant: `(device_id, runtime_generation, current_runtime_instance_id)` is checked atomically for every session and plan state transition.

- [ ] **Step 1: Write failing migration and race tests**

```python
def test_active_session_cannot_be_replaced_at_same_generation(repository):
    first = repository.register_runtime_session("d1", 4, "i1", NOW, NOW + timedelta(seconds=30))
    assert first.runtime_instance_id == "i1"
    with pytest.raises(ConnectorRepositoryError, match="runtime_session_active"):
        repository.register_runtime_session("d1", 4, "i2", NOW, NOW + timedelta(seconds=30))
```

- [ ] **Step 2: Verify failure before schema changes**

```powershell
python -m pytest backend/tests/test_simulation_connector_runtime_v2_sql.py backend/tests/test_simulation_connector_pairing_sql.py -q
```

Expected: missing migration columns or repository methods.

- [ ] **Step 3: Add only additive schema changes**

Add device signing JWK/key ID, credential generation, runtime generation, current instance, session-token hash/expiry, protocol version, plan status, reconciliation state, pairing bootstrap JWK/nonce hash, signing JWK, activation timestamps, and audit columns. Add uniqueness and lookup indexes. Keep v1 rows distinguishable by required `protocol` and never reinterpret them as v2.

- [ ] **Step 4: Implement compare-and-set repository transactions**

`register_runtime_session` succeeds only with the expected generation, no unexpired session, and no `leased`, `executing`, `outcome_unknown`, or `manual_review_required` plan. `force_takeover` verifies the caller-provided new generation equals current generation plus one and rejects unresolved plans. Store only hashes of runtime-session tokens.

- [ ] **Step 5: Run migration, ownership, and concurrency tests**

```powershell
python -m pytest backend/tests/test_simulation_connector_runtime_v2_sql.py backend/tests/test_simulation_connector_pairing_sql.py backend/tests/test_simulation_connector_data_migration.py backend/tests/test_simulation_connector_capability_ownership.py -q
```

- [ ] **Step 6: Commit persistence**

```powershell
git add backend/db/migrations/domains/simulation/0008_connector_app_runtime_v2.sql backend/governance/domain_table_ownership.json plugins/simulation/simulation_backend/data/connector_repository.py backend/tests
git commit -m "feat: persist governed Connector runtime v2 state"
```

---

### Task 4: Implement possession pairing and runtime-session fencing

**Files:**
- Modify: `plugins/simulation/simulation_backend/domain/connector_pairing.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_pairing.py`
- Create: `plugins/simulation/simulation_backend/application/connector_runtime_sessions.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `backend/routers/simulation_connector.py`
- Modify: `backend/tests/test_simulation_connector_pairing_capabilities.py`
- Create: `backend/tests/test_connector_runtime_sessions_v2.py`

**Interfaces:**
- Produces: pairing state `created -> user_bound -> activated`, `RuntimeSessionService.register(device_id, generation, runtime_instance_id) -> RuntimeSession`, and user-authenticated Capability `simulation.connector.runtime.takeover@1`.
- Consumes: repository CAS operations from Task 3 and device signing/bootstrap public keys from Task 2 wire rules.

- [ ] **Step 1: Write failing possession and stale-instance tests**

```python
def test_pairing_retains_signing_key_and_discards_bootstrap_key(service):
    pending = service.request_v2(DEVICE_SIGNING_JWK, BOOTSTRAP_RSA_JWK, NONCE)
    activated = service.activate_v2(pending.pairing_id, SIGNED_CHALLENGE, DECRYPTED_CHALLENGE)
    assert activated.device_key_id == "device-key-1"
    assert activated.bootstrap_key_retained is False

def test_losing_instance_cannot_evict_winner(session_service):
    winner = session_service.register("d1", 2, "winner")
    with pytest.raises(ConnectorError, match="runtime_session_active"):
        session_service.register("d1", 2, "loser")
    assert session_service.authenticate(winner.token).runtime_instance_id == "winner"
```

- [ ] **Step 2: Run targeted tests and confirm failure**

```powershell
python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_connector_runtime_sessions_v2.py -q
```

- [ ] **Step 3: Replace secret delivery with two-key pairing v2**

Persist the P-256 signing public JWK and disposable RSA-OAEP-SHA256 bootstrap public key. Verify separate possession challenges, encrypt the runtime credential only to the RSA key, bind the signing key to the activated device, expire the pairing ID, and audit wrong tenant/user, nonce replay, cancellation, and second activation.

- [ ] **Step 4: Add short-lived runtime-session tokens**

Generate 256-bit random tokens, store SHA-256 only, return the raw token once, and require device ID, generation, current instance, permitted runtime type, and expiry on wake, heartbeat, lease, renewal, outcome, and reconciliation routes.

- [ ] **Step 5: Add governed takeover**

Register `simulation.connector.runtime.takeover@1` as a confirmed write Capability. Its handler rejects unresolved work, atomically increments generation, invalidates the prior session, and records actor, reason, prior instance, and new instance.

- [ ] **Step 6: Verify pairing, race, ownership, and HTTP boundary tests**

```powershell
python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_pairing_sql.py backend/tests/test_connector_runtime_sessions_v2.py backend/tests/test_simulation_connector_http_api.py backend/tests/test_simulation_connector_capability_ownership.py -q
```

- [ ] **Step 7: Commit pairing and fencing**

```powershell
git add plugins/simulation/simulation_backend backend/routers/simulation_connector.py backend/tests
git commit -m "feat: fence App runtime pairing and sessions"
```

---

### Task 5: Issue signed plans, verify outcomes, and reconcile unknown effects

**Files:**
- Create: `plugins/simulation/simulation_backend/application/connector_protocol_v2.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_outcomes.py`
- Modify: `plugins/simulation/simulation_backend/application/connector_projection_worker.py`
- Modify: `backend/tests/test_connector_runtime_control_plane.py`
- Modify: `backend/tests/test_simulation_connector_outcome_capabilities.py`
- Create: `backend/tests/test_connector_reconciliation_v2.py`

**Interfaces:**
- Produces: `PlanSigner.sign(plan) -> ConnectorExecutionPlanV2`, `OutcomeVerifier.verify(outcome, device_jwk)`, and `ReconciliationService.reconcile(plan_id, probe_result)`.
- Consumes: v2 records from Task 2 and current runtime-session identity from Task 4.

- [ ] **Step 1: Write failing asymmetric-signature and unknown-outcome tests**

```python
def test_connector_public_key_cannot_mint_cloud_plan(plan_signer, trusted_public_jwk):
    signed = plan_signer.sign(unsigned_plan())
    assert signed.verify_signature(trusted_public_jwk)
    with pytest.raises(ValueError):
        PlanSigner.from_jwk(trusted_public_jwk)

def test_unknown_outcome_blocks_equivalent_plan(control_plane):
    control_plane.complete_v2(unknown_outcome())
    with pytest.raises(ConnectorError, match="reconciliation_required"):
        control_plane.queue_v2(equivalent_plan())
```

- [ ] **Step 2: Verify tests fail against v1 HMAC behavior**

```powershell
python -m pytest backend/tests/test_connector_runtime_control_plane.py backend/tests/test_simulation_connector_outcome_capabilities.py backend/tests/test_connector_reconciliation_v2.py -q
```

- [ ] **Step 3: Implement cloud-only ECDSA plan signing**

Load private keys from the cloud secret provider by `key_id`; never include them in pairing credentials, logs, fixtures outside the test-vector file, or Connector responses. Sign after all plan bindings and `plan_hash` are final. Enforce key validity interval and revocation before issuance.

- [ ] **Step 4: Verify device-signed outcomes before state projection**

Require current generation, current instance, lease ID, plan hash, monotonic journal sequence, registered device key ID, and valid low-S P1363 signature. Persist the verified outcome and projection intent atomically; only the projection worker applies the domain transition.

- [ ] **Step 5: Add explicit reconciliation transitions**

`outcome_unknown` blocks equivalent normalized input. A declared post-condition probe may transition to `succeeded` or `failed_without_effect`; absent or inconclusive probes transition to `manual_review_required`. Only `failed_without_effect` permits a replacement plan.

- [ ] **Step 6: Run cloud protocol and integration tests**

```powershell
python -m pytest backend/tests/test_connector_execution_plan_v2.py backend/tests/test_connector_runtime_control_plane.py backend/tests/test_simulation_connector_outcome_capabilities.py backend/tests/test_connector_reconciliation_v2.py backend/tests/integration/test_simulation_connector_projection_mysql.py -q
```

- [ ] **Step 7: Commit the v2 control plane**

```powershell
git add plugins/simulation/simulation_backend backend/tests
git commit -m "feat: govern Connector plan and outcome v2"
```

---

### Task 6: Register desktop consumers, providers, impact closure, and release approvals

**Files:**
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_pairing.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `docs/governance/user-function-registry.json`
- Modify generated outputs: `docs/capabilities/catalog.v2.json`, `docs/capabilities/openapi-fragment.v2.json`, `docs/capabilities/mcp-tools.v2.json`, `docs/capabilities/agent-tools.v2.json`, `docs/capabilities/simulation/*.md`, `docs/governance/capability-catalog-release.json`
- Create: `backend/capability_v2/desktop_release_approval.py`
- Create: `backend/tests/test_desktop_app_capability_governance.py`
- Create: `backend/tests/test_desktop_release_approval.py`

**Interfaces:**
- Produces: server-signed desktop consumer claim, complete Simulation provider/consumer bindings, computed App impact closure, and independently signed technical release approval validation.
- Invariant: AI remains advisory; only the trusted server/human workflow may set Capability `human_approved` or technical approval.

- [ ] **Step 1: Write failing governance tests**

```python
def test_renderer_identity_override_is_rejected(gateway_client):
    response = gateway_client.invoke(
        "simulation.vismockup.status.get", {"consumer_id": "forged-browser"}
    )
    assert response.error.code == "consumer_identity_override_forbidden"

def test_release_author_cannot_approve_own_artifacts(approval_service):
    with pytest.raises(ReleaseApprovalError, match="separation_of_duties"):
        approval_service.verify(record(author="u1", reviewers=["u1"]))
```

- [ ] **Step 2: Run and observe missing consumer/approval enforcement**

```powershell
python -m pytest backend/tests/test_desktop_app_capability_governance.py backend/tests/test_desktop_release_approval.py -q
```

- [ ] **Step 3: Register the desktop consumer and exact provider ownership**

The Gateway derives `consumer_id="ai00.desktop.windows-x64"` from the authenticated cloud session claim. Reject request-body identity overrides. Add pairing, runtime takeover, plan, outcome, reconciliation, and compatibility bindings under Simulation ownership with confirmation and permission declarations.

- [ ] **Step 4: Validate technical release approval independently**

Require immutable artifact hashes, `desktop_release_approver` role, author/reviewer separation, configured signature threshold, expiry, trusted release-authority key, and current revocation state. Do not map this record to Capability `human_approved`.

- [ ] **Step 5: Regenerate Catalog and docs with repository generators**

```powershell
python backend/scripts/build_capability_catalog.py
python backend/scripts/generate_capability_docs.py
python backend/scripts/build_user_function_registry.py
python backend/scripts/check_web_capability_routes.py
```

- [ ] **Step 6: Run the full deterministic governance gate**

```powershell
python -m pytest backend/tests/test_desktop_app_capability_governance.py backend/tests/test_desktop_release_approval.py backend/tests/test_simulation_connector_capability_ownership.py backend/tests/test_capability_governance_release_gate.py backend/tests/integration/test_release_gate_full.py -q
python backend/scripts/check_capability_v2_release_gate.py
```

- [ ] **Step 7: Commit governance artifacts**

```powershell
git add backend/capability_v2 backend/tests plugins/simulation/simulation_backend/capabilities docs/capabilities docs/governance
git commit -m "governance: register governed Windows desktop runtime"
```

---

### Task 7: Implement .NET protocol v2, device keys, and shared vectors

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Contracts.V2/Ai00.Connector.Contracts.V2.csproj`
- Create: `local-runtime/src/Ai00.Connector.Contracts.V2/ProtocolV2.cs`
- Create: `local-runtime/src/Ai00.Connector.Contracts.V2/CanonicalJsonV2.cs`
- Create: `local-runtime/src/Ai00.Connector.Contracts.V2/ProtocolV2Signatures.cs`
- Create: `local-runtime/src/Ai00.Connector.Contracts.V2/DeviceSigningKeyStore.cs`
- Modify: `local-runtime/Ai00.LocalRuntime.sln`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj`
- Create: `local-runtime/tests/Ai00.Connector.Tests/ProtocolV2VectorTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/DeviceSigningKeyStoreTests.cs`

**Interfaces:**
- Produces: `ExecutionPlanV2.ParseAndVerify`, `OutcomeV2Signer.Sign`, and `DeviceSigningKeyStore.GetOrCreate`.
- Consumes: `backend/tests/fixtures/connector_execution_plan_v2.json` from Task 2.

- [ ] **Step 1: Add the fixture to the xUnit output and write failing vector tests**

```csharp
[Fact]
public void PythonPlanVectorVerifiesInDotNet()
{
    var vector = ProtocolVector.Load("connector_execution_plan_v2.json");
    var plan = ExecutionPlanV2.ParseAndVerify(vector.PlanJson, vector.PlanPublicJwk);
    Assert.Equal(vector.PlanHash, plan.PlanHash);
}

[Fact]
public void DerAndHighSSignaturesFailClosed()
{
    Assert.Throws<ProtocolV2Exception>(() => ExecutionPlanV2.ParseAndVerify(Vector.DerPlan, Vector.PlanPublicJwk));
    Assert.Throws<ProtocolV2Exception>(() => ExecutionPlanV2.ParseAndVerify(Vector.HighSPlan, Vector.PlanPublicJwk));
}
```

- [ ] **Step 2: Run xUnit and confirm the project/types are missing**

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~ProtocolV2VectorTests|FullyQualifiedName~DeviceSigningKeyStoreTests"
```

- [ ] **Step 3: Implement strict parsing and P1363 verification**

Reject unknown JSON members before deserialization, reproduce the exact RFC 8785 fixture bytes, verify lower-case hash text, import only P-256 JWK public coordinates, require 64-byte unpadded Base64URL low-S signatures, and call `ECDsa.VerifyData(data, signature, HashAlgorithmName.SHA256, DSASignatureFormat.IeeeP1363FixedFieldConcatenation)`.

- [ ] **Step 4: Persist the device signing key with current-user DPAPI**

Store a versioned blob under the App-owned user-data directory using `DataProtectionScope.CurrentUser`. Keep the disposable RSA bootstrap private key only in memory through activation and zero/dispose it immediately afterward. Never return private key bytes from the store API.

- [ ] **Step 5: Run v1/v2 and key-store tests**

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~CanonicalJsonTests|FullyQualifiedName~ExecutionPlanVectorTests|FullyQualifiedName~ProtocolV2VectorTests|FullyQualifiedName~DeviceCredentialStoreTests|FullyQualifiedName~DeviceSigningKeyStoreTests"
```

- [ ] **Step 6: Commit .NET contracts**

```powershell
git add local-runtime backend/tests/fixtures/connector_execution_plan_v2.json
git commit -m "feat: add .NET Connector protocol v2 contracts"
```

---

### Task 8: Build application-owned ConnectorHost and safe COM recovery

**Files:**
- Create: `local-runtime/src/Ai00.Connector.AppHost/Ai00.Connector.AppHost.csproj`
- Create: `local-runtime/src/Ai00.Connector.AppHost/Program.cs`
- Create: `local-runtime/src/Ai00.Connector.AppHost/AppHostOptions.cs`
- Create: `local-runtime/src/Ai00.Connector.AppHost/DiagnosticPipeHost.cs`
- Create: `local-runtime/src/Ai00.Connector.AppHost/RuntimeSessionWorker.cs`
- Create: `local-runtime/src/Ai00.Connector.AppHost/PlanExecutionWorker.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/PlanJournal.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupConnection.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/PostConditionProbes.cs`
- Modify: `local-runtime/Ai00.LocalRuntime.sln`
- Create: `local-runtime/tests/Ai00.Connector.Tests/AppHostLifecycleTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/OutcomeUnknownRecoveryTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/VisMockupBreakawayTests.cs`

**Interfaces:**
- Produces: hidden `AI00.ConnectorHost.exe`, diagnostic-only named-pipe protocol, runtime-session worker, durable v2 execution journal, and bounded post-condition probes.
- Consumes: Task 4 session endpoints, Task 5 plans/outcomes, Task 7 contracts and device key store.

- [ ] **Step 1: Write failing lifecycle and recovery tests**

```csharp
[Fact]
public async Task JournalIsDurableBeforeComInvocation()
{
    await worker.ExecuteAsync(plan, CancellationToken.None);
    Assert.True(journal.Events.Single(e => e.Kind == "invocation_started").Flushed);
    Assert.True(fakeCom.WasCalledAfter(journal.LastFlushUtc));
}

[Fact]
public async Task TimeoutBecomesOutcomeUnknownAndStopsLaterSteps()
{
    var outcome = await worker.ExecuteAsync(twoStepPlan, CancellationToken.None);
    Assert.Equal("outcome_unknown", outcome.OverallStatus);
    Assert.Equal(1, fakeCom.CallCount);
}
```

- [ ] **Step 2: Run focused tests and confirm AppHost is absent**

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~AppHostLifecycleTests|FullyQualifiedName~OutcomeUnknownRecoveryTests|FullyQualifiedName~VisMockupBreakawayTests"
```

- [ ] **Step 3: Compose existing workers into AppHost**

Set `<AssemblyName>AI00.ConnectorHost</AssemblyName>`, `<TargetFramework>net8.0-windows</TargetFramework>`, and `<RuntimeIdentifier>win-x64</RuntimeIdentifier>` in the AppHost project. Use the generic host without `UseWindowsService`. Parse only fixed arguments `--parent-pid`, `--pipe-name`, `--launch-nonce`, `--manifest-path`, and `--gateway-origin`. Refuse startup on version, signer, manifest digest, or parent identity mismatch. Register pairing, session, wake, lease, journal, STA adapter, reconciliation, and outcome services; do not register Service, Tray, SessionHost, loopback HTTP, or MCP command dispatch.

- [ ] **Step 4: Restrict the diagnostic pipe**

Apply a current-user SID ACL and require nonce, parent PID, child PID, executable path, signer, and manifest digest in the handshake. Permit only `ready`, `health`, `pairing_state`, bounded `diagnostic`, and `shutdown`; reject payload members that could carry a Capability, plan, operation, file command, token, or credential.

- [ ] **Step 5: Make unknown outcomes durable and reconcilable**

Flush `plan_received`, `lease_acquired`, and `invocation_started` before COM. On timeout, cancellation after start, or process recovery without a terminal event, sign `outcome_unknown`, stop remaining steps, and run only the declared post-condition probe after cloud authorization.

- [ ] **Step 6: Launch VisMockup outside the AI00 job**

Use the allowlisted signed installation path and `CREATE_BREAKAWAY_FROM_JOB`; verify with `IsProcessInJob` that VisMockup is outside the AI00 Job before reporting launch success. Never terminate an existing or AI00-launched VisMockup process during AppHost shutdown.

- [ ] **Step 7: Run the complete Connector suite**

```powershell
dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release
```

Expected: existing v1 legacy tests and new v2/AppHost tests pass.

- [ ] **Step 8: Commit AppHost**

```powershell
git add local-runtime
git commit -m "feat: add application-owned ConnectorHost"
```

---

### Task 9: Harden Electron auth and the single Capability transport

**Files:**
- Create: `[frontend] packages/core/electron/capability_client.js`
- Modify: `[frontend] packages/core/electron/auth_manager.js`
- Modify: `[frontend] packages/core/electron/preload.js`
- Modify: `[frontend] packages/core/electron/main.js`
- Create: `[frontend] scripts/test_electron_capability_boundary.js`
- Create: `[frontend] scripts/test_electron_auth_security.js`
- Modify: `[frontend] package.json`

**Interfaces:**
- Produces: main-only `CapabilityClient.invoke(capabilityId, envelope)`, public preload `invokeCapability(capabilityId, envelope)`, and redacted auth state `{mode,user,expires_at}`.
- Consumes: fixed Gateway origin and server-signed desktop consumer claim from Task 6.

- [ ] **Step 1: Write failing source-boundary tests**

```javascript
test('preload exposes one governed business transport', () => {
  const source = fs.readFileSync('packages/core/electron/preload.js', 'utf8');
  assert.match(source, /invokeCapability/);
  assert.doesNotMatch(source, /exposeInMainWorld\('_cloudFetch'/);
  assert.doesNotMatch(source, /Bearer|refresh_token|access_token/);
});
```

- [ ] **Step 2: Run and confirm the legacy `_cloudFetch` boundary fails**

```powershell
node scripts/test_electron_capability_boundary.js
node scripts/test_electron_auth_security.js
```

- [ ] **Step 3: Implement OAuth Authorization Code with PKCE in main**

Generate state and verifier in memory, open the system browser, accept only `ai00://auth/callback` with exact state and a short-lived code, exchange the code from main, and store access/refresh tokens only inside `AuthManager`. Return no token from `getState`, broadcasts, errors, logs, or IPC.

- [ ] **Step 4: Implement the fixed-origin Capability client**

Validate Capability IDs with `^[a-z][a-z0-9_.-]+$`, validate a closed InvocationEnvelope with AJV, construct only `/api/v1/capabilities/${encodeURIComponent(id)}:invoke`, attach the main-owned access token, preserve idempotency identity across bounded auth retry, and return normalized success/error envelopes.

- [ ] **Step 5: Replace the preload transport**

Expose a frozen API function:

```javascript
invokeCapability: (capabilityId, envelope) =>
  ipcRenderer.invoke('capability:invoke', { capabilityId, envelope })
```

The main handler validates sender origin and schema before calling `CapabilityClient`. Do not expose arbitrary channel, URL, path, headers, method, or token arguments.

- [ ] **Step 6: Run auth, IPC, and existing frontend tests**

```powershell
node scripts/test_electron_capability_boundary.js
node scripts/test_electron_auth_security.js
npm test
```

- [ ] **Step 7: Commit the Electron business boundary**

```powershell
git add packages/core/electron scripts/test_electron_capability_boundary.js scripts/test_electron_auth_security.js package.json package-lock.json
git commit -m "feat: enforce governed Electron capability transport"
```

---

### Task 10: Supervise ConnectorHost and lock down Electron platform surfaces

**Files:**
- Create: `[frontend] packages/core/electron/connector_host_manager.js`
- Create: `[frontend] packages/core/electron/job_object_binding.js`
- Create: `[frontend] packages/core/electron/native/job_object/binding.gyp`
- Create: `[frontend] packages/core/electron/native/job_object/job_object.cc`
- Modify: `[frontend] packages/core/electron/main.js`
- Modify: `[frontend] packages/core/electron/windows.js`
- Modify: `[frontend] packages/core/electron/plugin_manager.js`
- Delete from production use: `[frontend] packages/core/electron/plugin_preload.js`
- Create: `[frontend] scripts/test_electron_connector_host_manager.js`
- Modify: `[frontend] scripts/test_electron_plugin_lifecycle_security.js`

**Interfaces:**
- Produces: `ConnectorHostManager.start()`, `stop()`, `getPublicState()`, native `createKillOnCloseJob()`, `assignProcess(jobHandle, pid)`, and `closeJob(jobHandle)`.
- Consumes: packaged `AI00.ConnectorHost.exe`, signed manifest, current-user singleton, and diagnostic protocol from Task 8.

- [ ] **Step 1: Write failing supervision and plugin tests**

```javascript
test('third-party plugin windows fail closed', () => {
  assert.throws(() => manager.openPluginWindow('third-party.demo'), /official_plugin_required/);
});

test('business payload is rejected on diagnostic pipe', async () => {
  await assert.rejects(
    host.acceptDiagnostic({ type: 'execute', operation_id: 'vismockup.model.open@1' }),
    /diagnostic_message_forbidden/
  );
});

test('second launch for the same Windows user activates the first instance', async () => {
  const result = await launchSecondInstanceForCurrentUser();
  assert.equal(result.secondProcessExited, true);
  assert.equal(result.firstWindowFocused, true);
});
```

- [ ] **Step 2: Run and confirm current broad plugin/host behavior fails**

```powershell
node scripts/test_electron_connector_host_manager.js
node scripts/test_electron_plugin_lifecycle_security.js
```

- [ ] **Step 3: Add the minimal Windows Job Object binding**

The Node-API addon wraps `CreateJobObjectW`, sets `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK`, assigns only the spawned ConnectorHost PID with `AssignProcessToJobObject`, and closes the handle on App exit. ConnectorHost blocks on the nonce handshake before cloud registration, eliminating the spawn-to-assignment execution window.

- [ ] **Step 4: Validate ConnectorHost identity before readiness**

Generate an unguessable pipe name and 256-bit nonce. Verify installed path, Authenticode signer, manifest digest, parent/child PIDs, and handshake nonce. Expose only redacted readiness, health, pairing ID/state, and diagnostics to Renderer.

Use Electron's single-instance lock at current-user scope. A second launch activates the existing window. Fast user switching creates a separate Electron instance, DPAPI identity, ConnectorHost, and device binding for the other Windows user.

- [ ] **Step 5: Harden windows, protocol, IPC, files, and plugins**

Resolve `app://root` paths with `path.resolve`, require containment under packaged allowlisted roots, reject encoded traversal and unexpected hosts, enable context isolation and sandboxing, disable Node integration, deny permissions by default, validate external URLs, bound file APIs to user-selected/App-owned paths, and allow official packaged plugin assets only. Remove the local Python Bridge startup.

- [ ] **Step 6: Verify lifecycle and security**

```powershell
node scripts/test_electron_connector_host_manager.js
node scripts/test_electron_plugin_lifecycle_security.js
node scripts/test_electron_capability_boundary.js
npm test
```

- [ ] **Step 7: Commit supervision and hardening**

```powershell
git add packages/core/electron scripts package.json package-lock.json
git commit -m "feat: supervise ConnectorHost in the Electron lifecycle"
```

---

### Task 11: Migrate Renderer calls and freeze UI parity

**Files:**
- Modify: `[frontend] web/**/*.js`
- Modify: `[frontend] web/**/*.html`
- Modify: `[frontend] packages/*/web/**/*.js`
- Modify: `[frontend] packages/*/web/**/*.html`
- Modify: `[frontend] packages/*/electron/**/*.js`
- Create: `[frontend] scripts/test_no_desktop_business_bypass.js`
- Create: `[frontend] scripts/capture_app_ui_baseline.js`
- Create: `[frontend] scripts/compare_app_ui_baseline.js`
- Create: `[frontend] web/tests/app-ui-baseline/*.png`
- Modify: `[frontend] package.json`

**Interfaces:**
- Produces: zero `_cloudFetch`, loopback bridge, Renderer business `fetch`, or business IPC call sites in the packaged App; approved visual baselines for critical pages.
- Consumes: `window.electronAPI.invokeCapability` from Task 9 and unchanged current UI markup/layout.

- [ ] **Step 1: Generate an exhaustive migration ledger and failing bypass test**

The test scans first-party HTML/JS and fails on `_cloudFetch`, `127.0.0.1` business bridges, `/api/` fetches outside the approved auth/bootstrap shell, dynamic Electron IPC channels, and direct VisMockup commands. Store every accepted non-business exception with file, line pattern, owner, reason, and expiry in `scripts/desktop_platform_route_allowlist.json`.

- [ ] **Step 2: Run the scanner and preserve the initial failure list as review evidence**

```powershell
node scripts/test_no_desktop_business_bypass.js
```

Expected: failures include the current preload `_cloudFetch`, admin pages, canvas flows, and plugin loopback bridge.

- [ ] **Step 3: Replace each business call with an exact Capability invocation**

For each call site, use its governed Capability ID, major version, Catalog Release, operation, idempotency key, confirmation receipt, and resource selector. Remove fallback direct REST code; do not wrap arbitrary URLs in the new API. Regenerate existing web migration evidence after the final call site is removed.

- [ ] **Step 4: Capture the approved UI baseline without restructuring UI**

Launch the packaged production assets with deterministic fixture data and capture login, workspace, Craft lineage, standard operations, Simulation/VisMockup, settings, pop-out windows, and approval flows at 1920x1080 and 125% Windows scaling. Record Electron/Chromium version and fixture identity beside each PNG.

- [ ] **Step 5: Add deterministic image and interaction comparison**

Add exact dev dependencies `pixelmatch@7.1.0` and `pngjs@7.0.0` to `package.json` and commit the resolved lockfile. Use `webContents.capturePage()` for screenshots and compare decoded PNG pixels with `pixelmatch`; fail when changed pixels exceed 0.1% outside checked-in masks. Also assert navigation targets, iframe origins, title-bar controls, shortcuts, theme, pop-out state, and approval transitions.

- [ ] **Step 6: Run migration, UI, build, and existing suites**

```powershell
node scripts/test_no_desktop_business_bypass.js
node scripts/compare_app_ui_baseline.js
npm run build:web:production
npm test
```

- [ ] **Step 7: Commit Renderer migration and baselines**

```powershell
git add web packages scripts package.json package-lock.json
git commit -m "feat: migrate desktop UI to governed capability invocation"
```

---

### Task 12: Package, update, pilot, and cut over the Windows x64 product

**Files:**
- Modify: `[frontend] package.json`
- Create: `[frontend] electron-builder-app.yml`
- Create: `[frontend] scripts/build_connector_host.ps1`
- Create: `[frontend] scripts/build_signed_app_release.ps1`
- Create: `[frontend] scripts/test_app_installer_contents.js`
- Create: `[frontend] scripts/test_app_update_rollback.ps1`
- Create: `[backend] docs/governance/electron-app-release-manifest.schema.json`
- Create per release: `[backend] docs/acceptance/electron-app-release-candidate.json`
- Modify: `[backend] local-runtime/tests/pilot/run-vismockup-pilot.ps1`

**Interfaces:**
- Produces: one signed Windows x64 NSIS installer, signed release manifest, compatibility policy, pilot evidence, and rollback/cutover record.
- Consumes: committed frontend build, AppHost self-contained x64 output, backend Catalog Release, adapter manifest, trusted/revoked keys, technical approval, and runtime evidence.

- [ ] **Step 1: Write failing installer-content assertions**

```javascript
assert.deepEqual(architectures, ['x64']);
assert(files.includes('resources/connector/AI00.ConnectorHost.exe'));
assert(!files.some(p => /Connector\.Service|Connector\.Tray|SessionHost|server\.py|gitlab/i.test(p)));
assert.equal(trayEntryCount, 1);
```

- [ ] **Step 2: Publish ConnectorHost as self-contained win-x64**

```powershell
dotnet publish local-runtime/src/Ai00.Connector.AppHost/Ai00.Connector.AppHost.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

Copy only the allowlisted signed output and manifest into Electron `extraResources`; exclude PDBs, tests, source, credentials, journals, prior installers, and developer tools.

- [ ] **Step 3: Restrict Electron Builder to Windows x64**

Remove macOS/Linux targets and legacy desktop scripts from the supported release path. Build web production assets first, validate App/ConnectorHost/protocol compatibility, then run Electron Builder with `electron-builder-app.yml`. Sign the installer and every executable with the configured Windows publisher certificate.

- [ ] **Step 4: Validate the signed release chain**

Verify HTTPS origin, release-manifest signature, installer SHA-256, Authenticode chain, App/ConnectorHost versions, Catalog Release, adapter hash, local-state schema compatibility, minimum security version, rotation overlap, revocation list, and anti-downgrade rule before update. A mismatch blocks local execution and installation.

- [ ] **Step 5: Test clean install, upgrade, failure, rollback, repair, and uninstall**

```powershell
node scripts/test_app_installer_contents.js
powershell -ExecutionPolicy Bypass -File scripts/test_app_update_rollback.ps1
```

Assert no Windows Service or separate startup/tray entry exists, App shutdown kills ConnectorHost, VisMockup survives, failed update leaves the previous complete version, incompatible rollback requires re-pairing/new generation, and full uninstall removes App-owned credentials/journal while retaining user documents.

- [ ] **Step 6: Run full pre-pilot verification**

Backend repository:

```powershell
python -m pytest backend/tests plugins/simulation/tests -q
dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release
python backend/scripts/check_capability_v2_release_gate.py
```

Frontend repository:

```powershell
npm ci
npm test
npm run build:web:production
node scripts/test_no_desktop_business_bypass.js
node scripts/compare_app_ui_baseline.js
node scripts/test_app_installer_contents.js
```

- [ ] **Step 7: Collect bounded Windows x64 pilot evidence**

Record exact frontend/backend commits, App/ConnectorHost/adapter/installer hashes, Catalog Release, device/generation/session IDs, pairing, wake latency, normal plans, duplicate delivery, network loss, App and Host crashes, COM timeout, reconciliation, VisMockup absence, update, rollback, repair, uninstall, and proof that no bypass executed. Keep `runtime_verified=false` until the authoritative pilot workflow signs the complete evidence.

- [ ] **Step 8: Apply release gates and cut over**

Promotion requires deterministic `machine_passed=true`, applicable Capability `human_approved=true`, signed technical release approval, and `runtime_verified=true`. Retain web plus legacy Connector rollback during the pilot. After threshold approval, stop distributing Service/Tray/SessionHost/Python Bridge artifacts; retire ordinary web navigation in a separate governed change.

- [ ] **Step 9: Commit source-side release automation and evidence schema**

Frontend repository:

```powershell
git add package.json package-lock.json electron-builder-app.yml scripts
git commit -m "build: package governed Windows x64 App"
```

Backend repository:

```powershell
git add docs/governance/electron-app-release-manifest.schema.json local-runtime/tests/pilot docs/acceptance/electron-app-release-candidate.json
git commit -m "governance: define Electron App release evidence"
```

## Final verification and publication

- [ ] Confirm both repositories are clean and every commit named by release evidence exists locally.
- [ ] Verify Gitea and GitHub `test` refs resolve to the intended commits before creating a release candidate.
- [ ] Push only Gitea and GitHub; do not configure or push GitLab.
- [ ] Recompute the App impact closure after all frontend and backend commits are immutable.
- [ ] Run the deterministic Release Gate against that exact closure.
- [ ] Obtain Capability business approval only where the business definition or behavior changed.
- [ ] Obtain separately signed technical release approval for installer, binaries, migrations, IPC, protocol, and update policy.
- [ ] Run the Windows x64 pilot and attach authoritative runtime evidence.
- [ ] Promote only after all four evidence dimensions independently pass.

## Governance status at plan creation

- **Change classification:** new protocol and consumer/provider implementation plus controlled breaking deployment migration; legacy v1 and old Connector remain during the pilot, then retire through an explicit governed cutover.
- **Authoritative context inspected:** approved design commit `b23cd853f`, current Catalog/generated Capability docs, Simulation pairing/runtime Providers, connector SQL migrations, Electron main/preload/plugin surfaces, .NET contracts/service/session host/adapter/tests, and Release Gate tests.
- **Reuse and ownership:** reuse the existing Capability Gateway, Simulation Provider, wake broker, Connector repository, .NET adapter/STA code, DPAPI store, and Electron UI. Simulation owns all Connector business effects; Electron and local diagnostics own no business effect.
- **Implementation boundary:** frontend repository owns Electron/UI/packaging; backend repository owns cloud governance, Simulation control plane, database, contracts, AppHost, adapters, and evidence.
- **Current verification:** design and plan text only; implementation tests have not run for the changes described here.
- **Current evidence:** `machine_passed=unverified`, `human_approved=false` for future changed Capability versions, `runtime_verified=false`, technical release approval absent.
- **Unresolved operational dependencies:** Windows code-signing identity, cloud ECDSA release/plan key provisioning, authorized `desktop_release_approver` assignments, and a controlled Windows x64 pilot environment must exist before Task 12 promotion.
