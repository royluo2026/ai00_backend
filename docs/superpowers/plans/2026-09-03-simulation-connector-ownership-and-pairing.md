# Simulation Connector Ownership and Feishu Pairing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move AI00 Connector and VisMockup completely out of Device ownership into Simulation, then add browser device-code pairing bound to the user's existing Feishu-authenticated AI00 identity.

**Architecture:** Simulation owns Connector credentials, pairing, heartbeat, plan leases, outcome outbox, VisMockup Capability descriptors, canonical HTTP adapters, and persistence. The Windows Connector remains an outbound Service plus per-user SessionHost; it never receives a Feishu token and proves pairing ownership with a verifier and ephemeral RSA key. Legacy Device/VisMockup Capability IDs and HTTP paths remain fail-closed or temporary adapters only.

**Tech Stack:** Python 3, FastAPI, Pydantic, MySQL/PyMySQL, Capability V2 Gateway, `cryptography`, .NET 8 Windows Service/WinForms, RSA-OAEP/AES-GCM, vanilla JavaScript.

**Spec:** `docs/superpowers/specs/2026-09-03-simulation-connector-feishu-pairing-design.md`

## Global Constraints

- Every new user-visible Capability owner is exactly `simulation`; no new Device Capability is allowed.
- Runtime Connector code must not import `device_backend`, `get_device_conn`, or read `AI00_DEVICE_*`.
- Connector, VisMockup, pairing, heartbeat, plan, lease, outcome, and outbox tables live in the Simulation database.
- The browser never calls localhost; Connector opens no inbound HTTP port.
- Connector never receives or persists a Feishu token; AI00 Web remains the only Feishu login surface.
- One AI00 user has at most one active Simulation Connector binding.
- Pairing expires after five minutes; user codes are non-secret locators, verifiers are hashed, and credential envelopes are encrypted to the request's ephemeral key.
- Connector execution-plan v1 remains wire-compatible; `device_id` is a deprecated serialization alias for `connector_id` until a future protocol version.
- New Capabilities start `experimental`. Never set `human_approved` or `runtime_verified` from machine work.
- Implement every behavior by RED → GREEN → REFACTOR; do not edit production code before observing the matching test fail.
- Do not regenerate global Catalog/Docs/Acceptance artifacts in this domain task; submit source changes to the designated governance task for freezing.

---

### Task 1: Simulation-owned Connector schema and controlled data migration

**Files:**
- Create: `backend/db/migrations/domains/simulation/0005_connector_control_plane.sql`
- Create: `backend/scripts/migrate_connector_to_simulation.py`
- Create: `backend/tests/test_simulation_connector_data_migration.py`
- Modify: `backend/capability_v2/official_domains.json`
- Modify: `backend/governance/domain_table_ownership.json`

**Interfaces:**
- Consumes: old read-only tables `workmanship_runtime_devices`, `workmanship_runtime_enrollments`, `workmanship_runtime_commands`, and `workmanship_device_connector_{health,heartbeat_audit,plans,projection_outbox}`.
- Produces: `MigrationReport(source_counts, target_counts, source_hashes, target_hashes)` and Simulation-owned `workmanship_sim_connector_*` tables.

- [ ] **Step 1: Write failing migration behavior tests**

```python
def test_connector_migration_is_idempotent_and_hash_equal(fake_source, fake_target):
    first = migrate_connector_rows(fake_source, fake_target)
    second = migrate_connector_rows(fake_source, fake_target)
    assert first.source_counts == first.target_counts
    assert first.source_hashes == first.target_hashes
    assert second == first

def test_connector_migration_rejects_conflicting_target(fake_source, fake_target):
    fake_target.replace("bindings", "dev-1", {"owner_user_gid": "other"})
    with pytest.raises(MigrationConflict, match="bindings:dev-1"):
        migrate_connector_rows(fake_source, fake_target)
```

These tests catch silent overwrite and duplicate-on-replay mutations.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_simulation_connector_data_migration.py -q`

Expected: import/collection failure because the migration module does not exist.

- [ ] **Step 3: Add the Simulation schema**

Create exactly these tables with primary keys, status indexes, microsecond timestamps, and constraints from the spec:

```text
workmanship_sim_connector_bindings
workmanship_sim_connector_enrollments
workmanship_sim_connector_legacy_commands
workmanship_sim_connector_health
workmanship_sim_connector_heartbeat_audit
workmanship_sim_connector_plans
workmanship_sim_connector_projection_outbox
workmanship_sim_connector_pairings
```

Bindings enforce one active row per `user_gid` using a nullable `active_owner_key` unique index. Pairings enforce unique `(installation_id, nonce_hash)` and `user_code_hash`, include `resource_version`, and contain no plaintext verifier/token column.

The projection outbox includes `lease_owner`, `lease_until`, `attempt`, `next_retry_at`, and a unique `(plan_id, outcome_hash, target_capability)` key. A database status value alone is not a lease.

- [ ] **Step 4: Implement the migration utility**

```python
@dataclass(frozen=True)
class MigrationReport:
    source_counts: dict[str, int]
    target_counts: dict[str, int]
    source_hashes: dict[str, str]
    target_hashes: dict[str, str]

class MigrationConflict(RuntimeError):
    pass

def migrate_connector_rows(source: RowStore, target: RowStore) -> MigrationReport:
    """Insert missing canonical rows, accept equivalent rows, reject conflicts."""
```

Normalize timestamps to UTC ISO-8601 and JSON to sorted compact form before SHA-256. Never update/delete source rows. The CLI requires explicit `--source-device-db-url` and `--target-simulation-db-url`, rejects identical URLs, and prints only counts/hashes.

- [ ] **Step 5: Register current Simulation ownership without rewriting history**

Add `0005_connector_control_plane.sql` only to Simulation schema paths. Keep historical Device migrations, but assign every new `workmanship_sim_connector_*` table to Simulation in the current ownership projection.

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
python -m pytest backend/tests/test_simulation_connector_data_migration.py backend/tests/test_domain_migration_runner.py backend/tests/test_schema_migration_static.py -q
python backend/scripts/check_domain_dependencies.py
```

Expected: all tests pass; dependency check reports zero violations.

- [ ] **Step 7: Commit**

```powershell
git add backend/db/migrations/domains/simulation/0005_connector_control_plane.sql backend/scripts/migrate_connector_to_simulation.py backend/tests/test_simulation_connector_data_migration.py backend/capability_v2/official_domains.json backend/governance/domain_table_ownership.json
git commit -m "feat(simulation): own connector persistence and migration"
```

---

### Task 2: Move Connector control plane and VisMockup Capability ownership

**Files:**
- Create: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Create: `plugins/simulation/simulation_backend/capabilities/connector_contracts.py`
- Create: `plugins/simulation/simulation_backend/data/connector_repository.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Modify: `plugins/simulation/simulation_backend/application/connector_plans.py`
- Modify: `plugins/simulation/simulation_backend/application/capture_worker.py`
- Modify: `plugins/simulation/simulation_backend/application/document_snapshots.py`
- Modify: `backend/domain_ports/simulation_runtime.py`
- Modify: `plugins/device/device_backend/capabilities/connector_runtime.py`
- Modify: `plugins/device/device_backend/capabilities/provider.py`
- Modify: `plugins/device/device_backend/capabilities/__init__.py`
- Create: `backend/tests/test_simulation_connector_capability_ownership.py`
- Modify: `backend/tests/test_simulation_reproducibility.py`
- Modify: `backend/tests/test_connector_runtime_control_plane.py`

**Interfaces:**
- Consumes: `get_simulation_conn()` and execution-plan v1 contracts.
- Produces: `simulation.connector.health.get@1`, `simulation.connector.plan.queue@1`, seven `simulation.vismockup.*@1` descriptors, and `SimulationConnectorRepository`.

- [ ] **Step 1: Write failing ownership tests**

```python
def test_connector_and_vismockup_are_owned_only_by_simulation(registry):
    ids = {
        "simulation.connector.health.get",
        "simulation.connector.plan.queue",
        "simulation.vismockup.status.get",
        "simulation.vismockup.application.launch",
        "simulation.vismockup.model.open",
        "simulation.vismockup.tree.get",
        "simulation.vismockup.selection.highlight",
        "simulation.vismockup.visibility.change.apply",
        "simulation.vismockup.capture.create",
    }
    assert {registry.resolve(cid, 1).spec.owner for cid in ids} == {"simulation"}

def test_old_device_connector_ids_are_fail_closed(registry):
    legacy = (
        ("device.connector.health.get", 1),
        ("device.connector.plan.queue", 1),
        ("device.connector.plan.queue", 2),
        ("vismockup.status", 1),
        ("vismockup.launch", 1),
        ("vismockup.model.open", 1),
        ("vismockup.tree", 1),
        ("vismockup.highlight", 1),
        ("vismockup.visibility", 1),
        ("vismockup.capture", 1),
    )
    for cid, version in legacy:
        descriptor = registry.resolve(cid, version).descriptor
        assert descriptor.lifecycle_status.value == "deprecated"
        assert not any(descriptor.exposure.model_dump().values())
```

These tests catch retained Device ownership and any open legacy exposure.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_simulation_connector_capability_ownership.py -q`

Expected: new Simulation IDs cannot resolve.

- [ ] **Step 3: Implement the Simulation repository and contracts**

Move exact health, plan validation, signing, lease, completion, and projection-outbox behavior into Simulation files. Replace `get_device_conn()` and old tables with `get_simulation_conn()` and `workmanship_sim_connector_*`.

The exact repository interface is `health(connector_id: str) -> dict | None`, `record_heartbeat(connector_id: str, expected_user_id: str, health: ConnectorHealth) -> None`, `queue_plan(plan: ConnectorExecutionPlanV1) -> OperationRef`, `lease_plan(connector_id: str, lease_seconds: int) -> dict | None`, and `complete_plan(connector_id: str, plan_id: str, lease_id: str, outcome: ConnectorPlanOutcomeV1) -> None`.

Preserve exact payload/hash checks and the projection retry-attempt behavior from `61d90b8f`.

- [ ] **Step 4: Register new Simulation capabilities**

Use closed schemas, owner `simulation`, lifecycle `experimental`, and Simulation resource selectors. Direct VisMockup atoms expose only `local_runtime=True` and remain internal workflow targets.

- [ ] **Step 5: Close legacy providers**

Keep deprecated zero-exposure descriptors for old IDs. Their handlers raise exactly:

```python
raise CapabilityBusinessError(
    "capability_migration_required",
    "Connector and VisMockup moved to the Simulation domain.",
)
```

Remove active Connector registrations/imports from Device. Keep historical migrations.

- [ ] **Step 6: Update Simulation workflow consumers**

Call `simulation.connector.health.get@1` and `simulation.connector.plan.queue@1`; emit new `simulation.vismockup.*@1` operation IDs. Keep execution-plan v1 `device_id` wire serialization unchanged.

- [ ] **Step 7: Verify GREEN**

Run:

```powershell
python -m pytest backend/tests/test_simulation_connector_capability_ownership.py backend/tests/test_connector_runtime_control_plane.py backend/tests/test_simulation_capture_workflow.py backend/tests/test_simulation_document_snapshot_workflow.py backend/tests/test_simulation_reproducibility.py -q
python backend/scripts/check_domain_dependencies.py
```

Expected: all pass and zero violations.

- [ ] **Step 8: Commit**

```powershell
git add plugins/simulation plugins/device backend/domain_ports/simulation_runtime.py backend/tests
git commit -m "refactor(simulation): move connector and vismockup ownership"
```

---

### Task 3: Make outcome projection atomic and crash-recoverable

**Files:**
- Modify: `plugins/simulation/simulation_backend/data/connector_repository.py`
- Create: `plugins/simulation/simulation_backend/application/connector_projection_worker.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `backend/domain_ports/simulation_runtime.py`
- Create: `backend/tests/integration/test_simulation_connector_projection_mysql.py`
- Modify: `backend/tests/test_simulation_connector_outcome_capabilities.py`

**Interfaces:**
- Consumes: Task 1 outbox schema and Task 2 outcome projection target resolver.
- Produces: `complete_with_projection_intent(connector_id: str, plan_id: str, lease_id: str, outcome: ConnectorPlanOutcomeV1) -> ProjectionIntent`, `claim_projection(owner: str, lease_seconds: int) -> ProjectionLease | None`, `finish_projection(plan_id: str, owner: str) -> None`, `fail_projection(plan_id: str, owner: str, error_code: str, retryable: bool) -> None`, `reclaim_stale_projections(now: datetime) -> int`, and an executable worker module.

- [ ] **Step 1: Write failing transaction/idempotency tests**

```python
def test_complete_commits_outcome_and_projection_intent_atomically(repository, leased_plan, outcome):
    repository.complete_with_projection_intent(leased_plan, outcome)
    outcome_hash = canonical_hash(outcome.model_dump(mode="json"))
    assert repository.get_plan(leased_plan.plan_id).status == "completed"
    assert repository.get_projection(leased_plan.plan_id).outcome_hash == outcome_hash

async def test_projection_idempotency_is_stable_across_attempts(runtime_client, gateway, plan, outcome):
    await runtime_client.apply_connector_outcome(plan, outcome, attempt=1)
    await runtime_client.apply_connector_outcome(plan, outcome, attempt=2)
    outcome_hash = canonical_hash(outcome.model_dump(mode="json"))
    assert gateway.idempotency_keys == [
        f"{plan.plan_id}:{outcome_hash}", f"{plan.plan_id}:{outcome_hash}",
    ]
```

These tests catch an outcome commit without durable intent and attempt-dependent downstream effects.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_simulation_connector_outcome_capabilities.py backend/tests/integration/test_simulation_connector_projection_mysql.py -q`

Expected: no atomic completion API/lease columns and current idempotency key differs by attempt.

- [ ] **Step 3: Commit outcome and outbox intent in one transaction**

Inside one `get_simulation_conn()` transaction: lock the leased plan; validate lease and exact outcome; reject conflicting outcome hash; update plan outcome; upsert the unique pending projection row; commit once. Any exception rolls back both writes. Same outcome replay returns the persisted projection; conflicting outcome raises `connector_outcome_conflict`.

- [ ] **Step 4: Implement leased claims and stale reclaim**

Claim with `SELECT plan_id,outcome_hash,target_capability,attempt FROM workmanship_sim_connector_projection_outbox WHERE status IN ('pending','retryable_failed') AND next_retry_at<=NOW(6) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`, then set `status='projecting'`, random `lease_owner`, and bounded `lease_until`. `finish_projection` and `fail_projection` require matching owner. `reclaim_stale_projections(now)` changes expired `projecting` rows to retryable pending and increments no business-effect identity.

The worker entry is:

```powershell
python -m plugins.simulation.simulation_backend.application.connector_projection_worker
```

It loops with bounded batch size, claims, invokes Gateway with `idempotency_key=f"{plan_id}:{outcome_hash}"`, finishes/fails by lease owner, and exits nonzero on unrecoverable schema/config errors.

- [ ] **Step 5: Add real MySQL/OceanBase crash tests**

Against `AI00_SIMULATION_TEST_DB_URL`, use separate processes/connections and assert persisted database state for:

```text
two concurrent complete calls with identical outcome → one plan outcome, one intent
two concurrent complete calls with conflicting outcome → one success, one connector_outcome_conflict
process killed immediately after outcome transaction commit → pending intent remains
worker killed after claim → projecting row remains leased, then stale reclaim makes it claimable
same outcome replay → same intent and same Gateway idempotency key
stale owner finish attempt → rejected; current lease owner can finish
```

Use a dedicated test database and transaction-visible polling; do not replace these cases with mocks or SQLite.

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
python -m pytest backend/tests/test_simulation_connector_outcome_capabilities.py -q
python -m pytest backend/tests/integration/test_simulation_connector_projection_mysql.py -q
```

Expected: both suites pass with zero skipped tests when `AI00_SIMULATION_TEST_DB_URL` is configured. A missing database is reported as `not run`, never passed.

- [ ] **Step 7: Commit**

```powershell
git add plugins/simulation/simulation_backend backend/domain_ports/simulation_runtime.py backend/tests
git commit -m "fix(simulation): make connector outcome projection recoverable"
```

---

### Task 4: Add Simulation browser pairing Capabilities

**Files:**
- Create: `plugins/simulation/simulation_backend/domain/connector_pairing.py`
- Create: `plugins/simulation/simulation_backend/capabilities/connector_pairing.py`
- Modify: `plugins/simulation/simulation_backend/data/connector_repository.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Create: `backend/tests/test_simulation_connector_pairing_capabilities.py`

**Interfaces:**
- Consumes: Task 2 repository and `cryptography` RSA-OAEP/AES-GCM.
- Produces: `PairingService.request/get_summary/approve/complete/read_binding` and five Simulation pairing/binding Capabilities.

- [ ] **Step 1: Write failing pairing tests**

```python
def test_user_code_cannot_complete_without_verifier(service, request):
    created = service.request(request)
    service.approve(created.user_code, actor("user-1"), expected_version=1)
    with pytest.raises(PairingError, match="pairing_proof_invalid"):
        service.complete(created.pairing_id, request.installation_id, created.user_code)

def test_pairing_summary_contains_only_safe_display_fields(service, request):
    created = service.request(request)
    summary = service.get_summary(created.user_code, actor("user-1"))
    assert set(summary.model_dump()) == {
        "pairing_id", "user_code", "device_name", "runtime_version",
        "masked_windows_user", "status", "expires_at", "resource_version",
    }

def test_one_user_cannot_silently_replace_binding(service, approved_pairings):
    service.complete_with_valid_proof(approved_pairings[0])
    with pytest.raises(PairingError, match="connector_binding_conflict"):
        service.approve(approved_pairings[1].user_code, actor("user-1"), 1)

def test_completion_retry_returns_same_envelope(service, approved_pairing):
    first = service.complete(**approved_pairing.proof)
    second = service.complete(**approved_pairing.proof)
    assert second.envelope_hash == first.envelope_hash
    assert second.encrypted_credential_envelope == first.encrypted_credential_envelope
```

These tests catch short-code authentication, silent replacement, and duplicate credential issuance.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py -q`

Expected: import failure for `connector_pairing`.

- [ ] **Step 3: Implement state and cryptography**

```python
class PairingStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    COMPLETING = "completing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    RECONCILIATION_REQUIRED = "reconciliation_required"

```

The exact service interface is `request(command: PairingRequestCommand) -> PairingRequested`, `get_summary(user_code: str, actor: PairingActor) -> PairingSummary`, `approve(user_code: str, actor: PairingActor, expected_version: int) -> PairingApproved`, `complete(pairing_id: str, installation_id: str, verifier: str) -> PairingCompleted`, and `read_binding(actor: PairingActor) -> ConnectorBinding | None`.

Hash verifier with SHA-256 and user code with HMAC-SHA256 using `AI00_CONNECTOR_PAIRING_CODE_SECRET`. Generate a 256-bit Connector token, persist only its hash, encrypt credential JSON with AES-256-GCM, and wrap the AES key with request RSA-3072/OAEP-SHA256.

- [ ] **Step 4: Register closed Capability contracts**

Register exactly:

```text
simulation.connector.pairing.request@1
simulation.connector.pairing.get@1
simulation.connector.pairing.approve@1
simulation.connector.pairing.complete@1
simulation.connector.binding.read@1
```

`approve` requires `simulation.use`, user confirmation, expected version, and Gateway idempotency. `request`/`complete` accept only `LOCAL_RUNTIME` bootstrap consumer `ai00.connector.bootstrap` and receive no normal Simulation scopes.

- [ ] **Step 5: Add error/concurrency cases and make each pass**

Cover five-minute expiry, duplicate nonce, malformed public key, wrong installation ID/verifier, cross-user approval, concurrent approval/completion, provider failure, and reconciliation. Run the single file after every RED/GREEN slice.

- [ ] **Step 6: Run focused and ABAC tests**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_capability_abac_matrix.py backend/tests/test_simulation_connector_outcome_capabilities.py -q`

Expected: all pass; bootstrap identity cannot invoke anything except pairing request/complete.

- [ ] **Step 7: Commit**

```powershell
git add plugins/simulation/simulation_backend backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_capability_abac_matrix.py
git commit -m "feat(simulation): add connector browser pairing capabilities"
```

---

### Task 5: Canonical Simulation HTTP adapters and legacy route isolation

**Files:**
- Create: `backend/routers/simulation_connector.py`
- Modify: `backend/routers/device_runtime.py`
- Create: `backend/tests/test_simulation_connector_http.py`
- Modify: `backend/tests/test_device_runtime_protocol.py`
- Modify: `backend/tests/test_connector_runtime_control_plane.py`

**Interfaces:**
- Consumes: Task 2 control plane and Task 4 pairing Capabilities through Gateway/server-authenticated adapters.
- Produces: canonical `/api/v1/simulation/connector/*` endpoints and temporary deprecated adapters at old paths.

- [ ] **Step 1: Write failing route tests**

```python
def test_pair_approval_uses_feishu_authenticated_actor(client, feishu_user):
    response = client.post(
        "/api/v1/simulation/connector/pairings/CODE/approve",
        headers=feishu_user.headers,
        json={"expected_resource_version": 1},
    )
    assert response.status_code == 200
    assert response.json()["data"]["approved_user_gid"] == feishu_user.gid

def test_legacy_heartbeat_is_only_a_deprecated_adapter(client, connector):
    response = client.post(
        "/api/v1/connector/heartbeat",
        headers=connector.headers,
        json=connector.health,
    )
    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
```

These tests catch request-body identity and retained Device execution behind old URLs.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_simulation_connector_http.py -q`

Expected: canonical routes return 404.

- [ ] **Step 3: Implement canonical adapters**

Expose pairing request/safe-summary/approve/complete, binding, heartbeat, plan lease/completion, artifact download, and result-artifact upload below `/api/v1/simulation/connector`. Handlers invoke Gateway/Simulation ports and never import `device_backend`.

Browser approval derives actor/tenant from existing Feishu-backed `get_current_user` and uses Gateway confirmation semantics. Bootstrap request/complete construct only the restricted bootstrap consumer after proof and rate-limit validation; they never fabricate a user actor.

- [ ] **Step 4: Reduce old routes to adapters**

Keep path shapes required by installed Connector versions, delegate to the same Simulation adapter functions, and return `Deprecation: true`, `Sunset`, and canonical `Link` headers. Legacy enrollment/command paths stay admin-only and cannot register new consumers.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest backend/tests/test_simulation_connector_http.py backend/tests/test_device_runtime_protocol.py backend/tests/test_connector_runtime_control_plane.py -q
python backend/scripts/check_domain_dependencies.py
```

Expected: all pass and zero domain violations.

- [ ] **Step 6: Commit**

```powershell
git add backend/routers/simulation_connector.py backend/routers/device_runtime.py backend/tests
git commit -m "feat(simulation): expose canonical connector control plane"
```

---

### Task 6: Windows Connector browser pairing and canonical endpoints

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Service/ConnectorPairing.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/ConnectorGatewayClient.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/DeviceGatewayClient.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/DeviceCredentialStore.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/RuntimeOptions.cs`
- Modify: `local-runtime/src/Ai00.Connector.Tray/Program.cs`
- Modify: `local-runtime/src/Ai00.Connector.Tray/StatusView.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/ConnectorBrowserPairingTests.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/ServerContractTests.cs`

**Interfaces:**
- Consumes: canonical HTTP contract from Task 5.
- Produces: `ConnectorPairing.RunBrowserFlowAsync(Uri, CancellationToken)` and DPAPI-protected `ConnectorCredential(ConnectorId, UserId, WindowsSid, Token)`.

- [ ] **Step 1: Write failing .NET pairing tests**

```csharp
[Fact]
public async Task BrowserPairingNeverPlacesVerifierOrTokenInUrl()
{
    var result = await fixture.PairAsync();
    Assert.Equal($"{fixture.Gateway}/simulation/connector/pair?code=ABCD-EFGH",
                 result.BrowserUri.ToString());
    Assert.DoesNotContain(result.Verifier, result.BrowserUri.ToString());
    Assert.DoesNotContain("token", result.BrowserUri.Query,
                          StringComparison.OrdinalIgnoreCase);
}

[Fact]
public async Task LostCompletionResponseReusesSameEncryptedEnvelope()
{
    var first = await fixture.CompleteAndDropResponseAsync();
    var second = await fixture.RetryCompletionAsync();
    Assert.Equal(first.EnvelopeHash, second.EnvelopeHash);
}
```

These tests catch proof leakage and duplicate credential issuance.

- [ ] **Step 2: Run tests and verify RED**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore --filter ConnectorBrowserPairingTests -m:1 /nodeReuse:false`

Expected: compile failure because browser pairing API does not exist.

- [ ] **Step 3: Implement the minimal browser flow**

Use .NET built-ins: `RSA.Create(3072)`, `RandomNumberGenerator.GetBytes(32)`, `SHA256.HashData`, `Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true })`, `AesGcm`, and existing DPAPI storage. Poll no faster than `poll_interval_seconds`; stop on expiry/cancellation.

The Tray/current interactive user generates key and SID, then communicates with Service through the fixed named pipe. Never perform pairing as LocalSystem. Delete ephemeral materials after success or terminal failure.

- [ ] **Step 4: Switch clients and labels**

Replace `/api/v1/connector/*` and `/api/v1/device-runtime/*` with `/api/v1/simulation/connector/*`. Preserve execution-plan v1 header/JSON aliases; change visible labels from “设备” to “Connector”.

- [ ] **Step 5: Verify GREEN**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore --nologo -v minimal -m:1 /nodeReuse:false`

Expected: all tests pass, including session ownership, heartbeat, artifacts, recovery, VisMockup capture, and installer contracts.

- [ ] **Step 6: Commit**

```powershell
git add local-runtime
git commit -m "feat(connector): pair through simulation browser authorization"
```

---

### Task 7: Web pairing, automatic Connector selection, and production Bridge removal

**Files:**
- Create: `E:/Projects/ai00/workmanship-web/packages/sim-plugin/web/cad_sim/connector_pairing.js`
- Create: `E:/Projects/ai00/workmanship-web/packages/sim-plugin/web/cad_sim/connector_pairing.html`
- Modify: `E:/Projects/ai00/workmanship-web/packages/sim-plugin/web/cad_sim/cad_sim.html`
- Modify: `E:/Projects/ai00/workmanship-web/packages/sim-plugin/web/cad_sim/cad_sim.js`
- Create: `E:/Projects/ai00/workmanship-web/packages/sim-plugin/web/cad_sim/connector_pairing.test.mjs`

**Interfaces:**
- Consumes: pairing get/approve and binding read Capabilities plus existing Web Capability invoke/confirm helper.
- Produces: `resolveBoundConnector(invoke): Promise<ConnectorBinding>`; pairing page accepts only non-secret `code` from URL.

- [ ] **Step 1: Write failing Web tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { approvalPayload, resolveBoundConnector } from './connector_pairing.js';

function buildProductionCadSimulation() {
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  execFileSync(npm, ['run', 'build:web'], { stdio: 'pipe' });
  return readFileSync(
    'dist-production/packages/sim-plugin/web/cad_sim/cad_sim.js', 'utf8',
  );
}

test('capture resolves binding instead of prompting for connector id', async () => {
  const calls = [];
  const fakeInvoke = async (id) => {
    calls.push(id);
    return { binding: { connector_id: 'connector-1', status: 'online' } };
  };
  const binding = await resolveBoundConnector(fakeInvoke);
  assert.equal(binding.connector_id, 'connector-1');
  assert.deepEqual(calls, ['simulation.connector.binding.read']);
});

test('approval payload cannot supply a user id', () => {
  assert.deepEqual(approvalPayload('ABCD-EFGH', 3), {
    user_code: 'ABCD-EFGH', expected_resource_version: 3,
  });
});

test('production cad simulation bundle has no localhost bridge', async () => {
  const bundle = await buildProductionCadSimulation();
  assert.equal(bundle.includes('127.0.0.1'), false);
  assert.equal(bundle.includes('localhost'), false);
  assert.equal(bundle.includes('/bridge/vis_mockup'), false);
  assert.equal(bundle.includes('请输入已配对的 AI00 Connector'), false);
});
```

These tests catch manual ID restoration, browser-selected identity, and any production Bridge bypass.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --test packages/sim-plugin/web/cad_sim/connector_pairing.test.mjs`

Expected: module/function not found.

- [ ] **Step 3: Implement pairing page**

Read/normalize only `code` from `URLSearchParams`. Fetch the safe request summary through Gateway, display Connector name/version and masked Windows identity, then use existing confirmation-token flow for `simulation.connector.pairing.approve@1`. If no Feishu session exists, use existing AI00 auth redirect and preserve only the non-secret code return path.

- [ ] **Step 4: Remove every production localhost Bridge binding**

Delete `_bridge`, `_captureOpSequenceLegacy`, its constants, and every production event binding for direct launch/open/reset/capture/tree/visibility/selection/highlight/debug calls. Bind environment construction and reverse capture only to their governed Simulation workflows. Remove or hide controls whose governed workflow is outside the current scope; do not leave a disabled handler that can be called from `window.top`.

Do not copy Bridge code into another production-imported module. Git history is the recovery mechanism; a future explicit non-production diagnostic tool requires a separate reviewed entry point and is not part of this task.

- [ ] **Step 5: Replace manual prompt**

```javascript
export async function resolveBoundConnector(invoke) {
  const data = await invoke('simulation.connector.binding.read', {}, { version: 1 });
  if (!data.binding) throw new Error('请先绑定 AI00 Connector');
  if (data.binding.status !== 'online') throw new Error('AI00 Connector 当前离线');
  return data.binding;
}
```

Use `binding.connector_id` to populate the execution-plan v1 compatibility field. Remove manual Connector ID input and never add localhost fallback.

- [ ] **Step 6: Verify GREEN and build**

Run:

```powershell
node --test packages/sim-plugin/web/cad_sim/connector_pairing.test.mjs
node --check packages/sim-plugin/web/cad_sim/cad_sim.js
npm run build:web
```

Expected: tests/check/build pass; the production output has no localhost/Bridge URL, direct VisMockup control binding, or manual Connector prompt.

- [ ] **Step 7: Commit the Web repository separately**

```powershell
git add packages/sim-plugin/web/cad_sim dist-production
git commit -m "feat(simulation): pair and resolve the user's connector"
```

Record the Web SHA in the AI00 verification report.

---

### Task 8: End-to-end boundary enforcement and cleanup

**Files:**
- Create: `backend/tests/test_simulation_connector_pairing_e2e.py`
- Modify: `backend/tests/test_simulation_domain_boundary.py`
- Modify: `backend/tests/test_integration_target_gateway_contract.py`
- Modify: `backend/tests/test_capability_abac_matrix.py`
- Modify: `backend/tests/test_simulation_runtime_port_bindings.py`
- Modify: `plugins/device/device_backend/public.py`
- Modify: `plugins/device/device_backend/capabilities/__init__.py`

**Interfaces:**
- Consumes: Tasks 1-6 and real Gateway/Registry bindings.
- Produces: one Feishu actor → pairing → heartbeat → binding → plan test and deterministic no-Device-dependency gates.

- [ ] **Step 1: Write failing real-Gateway E2E test**

```python
async def test_feishu_user_pairs_and_queues_only_own_connector(gateway, connector):
    request = await connector.request_pairing(gateway)
    await gateway_confirm_and_invoke(
        "simulation.connector.pairing.approve", 1,
        {"user_code": request.user_code, "expected_resource_version": 1},
        feishu_identity("user-1", "team-1"),
    )
    credential = await connector.complete_pairing(gateway, request)
    await connector.heartbeat(gateway, credential)
    binding = await invoke(gateway, "simulation.connector.binding.read", 1, {},
                           feishu_identity("user-1", "team-1"))
    assert binding["binding"]["connector_id"] == credential.connector_id
    assert await queue_exact_plan(gateway, binding["binding"], "user-1")
```

This catches Gateway bypass, unreadable bindings, and cross-owner queueing.

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_e2e.py -q`

Expected: first incomplete cross-component contract fails.

- [ ] **Step 3: Add executable boundary gates**

Make runtime registry/dependency tests fail if active Simulation Connector code imports Device internals/DB settings or Device resolves a non-deprecated Connector/VisMockup capability. Test behavior and dependency graph, not source text alone.

- [ ] **Step 4: Remove remaining Device runtime exports**

Delete active exports only after every consumer resolves to Simulation. Retain only fail-closed descriptors required for Catalog compatibility. Run unrelated Device physical-domain tests.

- [ ] **Step 5: Run focused matrix**

Run:

```powershell
python -m pytest backend/tests/test_simulation_connector_data_migration.py backend/tests/test_simulation_connector_capability_ownership.py backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_http.py backend/tests/test_simulation_connector_pairing_e2e.py backend/tests/test_simulation_capture_workflow.py backend/tests/test_simulation_document_snapshot_workflow.py backend/tests/test_simulation_connector_outcome_capabilities.py backend/tests/test_capability_abac_matrix.py -q
python backend/scripts/check_domain_dependencies.py
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore --nologo -v minimal -m:1 /nodeReuse:false
```

Expected: all pass; zero domain violations; zero .NET failures.

- [ ] **Step 6: Commit**

```powershell
git add backend/tests plugins/device plugins/simulation
git commit -m "test(simulation): enforce connector ownership end to end"
```

---

### Task 9: Governance evidence and controlled handoff

**Files:**
- Create: `docs/superpowers/reports/2026-09-03-simulation-connector-pairing-verification.md`
- Do not modify: generated global Catalog, generated Capability docs, acceptance manifest, or approval evidence.

**Interfaces:**
- Consumes: exact AI00/Web SHAs and raw test results.
- Produces: governance change record and review request for task `01a0183f-f392-7d73-a4e6-d5822122fe5d`.

- [ ] **Step 1: Run source checks without regenerating global artifacts**

Run:

```powershell
python -m pytest backend/tests/test_capability_bootstrap.py backend/tests/test_domain_provider_loader.py -q
python backend/scripts/check_domain_dependencies.py
python backend/scripts/build_capability_catalog.py --check
```

Catalog release drift caused only by new source descriptors/hashes is recorded for the governance task. Provider mismatch or code failure remains a domain blocker.

- [ ] **Step 2: Write exact verification report**

Use the governance proposal template. Record every new/deprecated Capability, owner, Provider, API, consumer, migration, command, raw result, and unavailable check. Set `machine_passed=true` only if all domain checks pass; keep `human_approved=unverified`, `runtime_verified=unverified`, and `advisory=true`.

- [ ] **Step 3: Commit report**

```powershell
git add docs/superpowers/reports/2026-09-03-simulation-connector-pairing-verification.md
git commit -m "docs(simulation): report connector migration evidence"
```

- [ ] **Step 4: Submit governance review**

Send exact AI00 commits, Web commit, evidence, Catalog drift, and explicit GO/NO-GO request to task `01a0183f-f392-7d73-a4e6-d5822122fe5d`. That task freezes Provider hashes, Catalog, generated docs, and acceptance manifest. Do not claim its result before it responds.

- [ ] **Step 5: Preserve runtime truth**

Keep `runtime_verified` false until a target workstation proves:

```text
Feishu Web login → browser pairing approval → Connector credential → heartbeat
→ Simulation environment plan → Connector lease → VFFrame.Application COM
→ VisMockup internal capture → artifact upload → Craft screenshot attachment
```

Record locked-screen/non-sleep execution separately from unlocked-session execution.
