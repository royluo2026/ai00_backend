# AI00 Connector Product-Initiated Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install AI00 Connector once as a lightweight always-on Windows service, bind it once from the Simulation page, recover interrupted credential delivery safely, and operate VisMockup without exposing codes, device IDs, localhost HTTP, or raw provider errors.

**Architecture:** The authenticated Web page creates a one-time bootstrap ticket through Simulation Capabilities and hands it to the already installed Connector through `ai00connector://`. The Connector claims the ticket, the user confirms the displayed workstation in the Simulation page, and the server issues an encrypted credential but does not mark the binding active until the Connector persists and verifies it. The Service remains lightweight and outbound-only; SessionHost and adapters run only for active work.

**Tech Stack:** Python 3, FastAPI, PyMySQL/OceanBase-compatible SQL, AI00 Capability Gateway v2.5, vanilla JavaScript, .NET 8 Windows Worker/WinForms, WiX v4, DPAPI, xUnit, pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-06-simulation-connector-in-product-onboarding-design.md`

## Global Constraints

- Normal users never enter or copy a pairing code or Connector device ID.
- Production Web never calls a workstation loopback HTTP service; no port 7654 restoration.
- All Connector pairing and operation effects remain owned by the `simulation` domain and pass through Capability Gateway.
- Only `simulation.connector.pairing.approve` and device replacement require explicit user confirmation.
- Server state becomes `active` only after Connector credential persistence and read-back verification.
- Same-user/same-installation retries recover; a different installation requires replacement confirmation and preserves the old binding until activation succeeds.
- Production custom-protocol requests accept only trusted HTTPS gateways; explicit loopback HTTP is development-only.
- Idle Service plus Tray private working set target is at most `100 MB`; ten-minute idle average CPU is below `1%`.
- SessionHost and business adapters are absent when idle and release COM/process/file/network handles after bounded idle time.
- `machine_passed`, `runtime_verified`, and `human_approved` remain separate evidence states.

---

### Task 1: Make credential issuance recoverable and activation explicit

**Files:**
- Create: `backend/db/migrations/domains/simulation/0006_connector_pairing_activation.sql`
- Modify: `plugins/simulation/simulation_backend/domain/connector_pairing.py`
- Modify: `plugins/simulation/simulation_backend/data/connector_repository.py`
- Test: `backend/tests/test_simulation_connector_pairing_capabilities.py`
- Test: `backend/tests/test_simulation_connector_pairing_sql.py`

**Interfaces:**
- Consumes: existing `PairingService.complete(pairing_id, installation_id, verifier)`.
- Produces: `PairingService.activate(pairing_id, connector_id, activation_proof) -> PairingSummary`, `PairingRepository.activate_pairing(...)`, and statuses `credential_issued`, `active`, `recovery_required`.

- [ ] **Step 1: Add failing domain tests for issuance without activation and same-installation replay**

```python
def test_credential_issue_does_not_claim_active_until_connector_ack():
    service = _service()
    created = service.request(_request())
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)
    issued = service.complete(created.pairing_id, "install-1", "proof-1")
    assert issued.activation_challenge
    assert service.repository.by_id(created.pairing_id).activation_status == "credential_issued"
    assert service.repository.binding_for_user("user-1")["status"] == "pending_activation"

def test_same_installation_retry_returns_same_envelope_without_second_binding():
    service = _service()
    created = service.request(_request())
    service.approve(created.user_code, "user-1", "team-1", expected_version=1)
    first = service.complete(created.pairing_id, "install-1", "proof-1")
    second = service.complete(created.pairing_id, "install-1", "proof-1")
    assert second.encrypted_credential_envelope == first.encrypted_credential_envelope
    assert len(service.repository.bindings) == 1
```

- [ ] **Step 2: Run the tests and verify current behavior fails**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py -q`

Expected: FAIL because completion currently writes status `completed`, inserts a second binding on recovery, and has no activation challenge.

- [ ] **Step 3: Add the forward-only migration**

```sql
ALTER TABLE `workmanship_sim_connector_pairings`
  ADD COLUMN `activation_challenge_hash` CHAR(64) NULL AFTER `credential_envelope_hash`,
  ADD COLUMN `activation_status` VARCHAR(32) NOT NULL DEFAULT 'not_issued' AFTER `activation_challenge_hash`,
  ADD COLUMN `activated_at` DATETIME(6) NULL AFTER `completed_at`;

ALTER TABLE `workmanship_sim_connector_bindings`
  ADD COLUMN `activated_at` DATETIME(6) NULL AFTER `last_seen_at`;
```

Keep migration `0005` and its anonymous legacy status check immutable. Use `activation_status` for `not_issued`, `credential_issued`, `active`, and `recovery_required`; retain legacy `status='completing'` during issuance and `status='completed'` only after activation. Binding rows use `status='pending_activation'` until the activation transaction changes them to `offline`; that table has no status check to replace.

- [ ] **Step 4: Implement issue-or-replay and activation as repository transactions**

```python
def complete(self, pairing_id: str, installation_id: str, verifier: str) -> PairingCompletion:
    record = self._proved_pairing(pairing_id, installation_id, verifier)
    if record.status in {"credential_issued", "active"}:
        return self._stored_completion(record)
    completion, binding = self._issue_credential(record)
    self.repository.issue_credential(record, record.approved_user_gid, binding)
    return completion

def activate(self, pairing_id: str, connector_id: str, activation_proof: str) -> PairingSummary:
    record = self.repository.by_id(pairing_id)
    if record is None or record.connector_id != connector_id:
        raise PairingError("pairing_not_found")
    if not secrets.compare_digest(record.activation_challenge_hash or "", _hash(activation_proof)):
        raise PairingError("pairing_activation_proof_invalid")
    self.repository.activate_pairing(record, expected_version=record.resource_version)
    return self._summary(record.pairing_id)
```

The SQL implementation must `SELECT ... FOR UPDATE`, reuse the existing binding when owner and installation match, and convert `pymysql.err.IntegrityError` into `PairingError("connector_binding_conflict")` rather than leaking 500.

- [ ] **Step 5: Add SQL transaction tests**

Cover same-installation replay, concurrent activation, conflicting installation, and rollback when the pairing update fails after binding insert. Assert one binding row and one envelope hash.

- [ ] **Step 6: Run focused backend tests**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_pairing_sql.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the recoverable state machine**

```bash
git add backend/db/migrations/domains/simulation/0006_connector_pairing_activation.sql plugins/simulation/simulation_backend/domain/connector_pairing.py plugins/simulation/simulation_backend/data/connector_repository.py backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_pairing_sql.py
git commit -m "fix(simulation): make connector activation recoverable"
```

### Task 2: Add authenticated bootstrap tickets and governed contracts

**Files:**
- Modify: `backend/db/migrations/domains/simulation/0006_connector_pairing_activation.sql`
- Modify: `plugins/simulation/simulation_backend/domain/connector_pairing.py`
- Modify: `plugins/simulation/simulation_backend/data/connector_repository.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_pairing.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Test: `backend/tests/test_simulation_connector_pairing_capabilities.py`
- Test: `backend/tests/test_simulation_connector_capability_ownership.py`

**Interfaces:**
- Consumes: activation state machine from Task 1.
- Produces: `bootstrap.create`, `bootstrap.get`, `activate`, and `cancel` Capability contracts; `PairingRequest.bootstrap_token`; stable business errors.

- [ ] **Step 1: Write failing Capability contract tests**

```python
def test_bootstrap_is_user_scoped_and_pair_request_claims_it_once():
    provider, web, local = _provider_contexts()
    ticket = provider.bootstrap_create({}, web).data
    request = _request().model_copy(update={"bootstrap_token": ticket["bootstrap_token"]})
    claimed = provider.request(request.model_dump(), local).data
    assert claimed["bootstrap_id"] == ticket["bootstrap_id"]
    with pytest.raises(CapabilityBusinessError, match="pairing_bootstrap_reused"):
        provider.request(request.model_dump(), local)

def test_bootstrap_projection_never_exposes_secret_material():
    value = provider.bootstrap_get({"bootstrap_id": bootstrap_id}, web).data
    assert not ({"bootstrap_token", "verifier_hash", "ephemeral_public_key"} & value.keys())
```

- [ ] **Step 2: Run tests and observe missing capabilities**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_capability_ownership.py -q`

Expected: FAIL because bootstrap/activate/cancel are not registered.

- [ ] **Step 3: Add bootstrap storage to migration `0006`**

```sql
CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_pairing_bootstraps` (
  `bootstrap_id` VARCHAR(128) PRIMARY KEY,
  `owner_user_gid` VARCHAR(191) NOT NULL,
  `team_gid` VARCHAR(191) NOT NULL,
  `token_hash` CHAR(64) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `pairing_id` VARCHAR(128) NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY `uq_sim_connector_bootstrap_token` (`token_hash`),
  KEY `idx_sim_connector_bootstrap_owner` (`owner_user_gid`,`status`,`expires_at`),
  CHECK (`status` IN ('created','claimed','approved','credential_issued','active','cancelled','expired'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 4: Define exact Capability schemas and Provider methods**

Add:

```python
"simulation.connector.pairing.bootstrap.create": obj({}, ()),
"simulation.connector.pairing.bootstrap.get": obj({"bootstrap_id": STRING}, ("bootstrap_id",)),
"simulation.connector.pairing.activate": obj({
    "pairing_id": STRING, "connector_id": STRING, "activation_proof": STRING,
}, ("pairing_id", "connector_id", "activation_proof")),
"simulation.connector.pairing.cancel": obj({
    "bootstrap_id": STRING, "expected_version": {"type": "integer", "minimum": 1},
}, ("bootstrap_id", "expected_version")),
```

Register all four with owner `simulation`, version `1`, lifecycle `experimental`, exact exposure, `simulation.use` for Web operations, and local-runtime-only exposure for activate. `approve` keeps `confirmation="user"`. Every result returns `EvidenceRef` hashed from its safe projection.

- [ ] **Step 5: Implement ticket claim and ownership rules**

`bootstrap.create` derives owner/team only from `CapabilityContext`; the raw token is returned once and only its SHA-256 hash is stored. `pairing.request` atomically changes `created -> claimed`. `bootstrap.get` requires the same owner. `cancel` rejects active records. Ticket lifetime is exactly two minutes.

- [ ] **Step 6: Run Capability and ownership tests**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_capability_ownership.py -q`

Expected: PASS with no plaintext ticket in repository projections or evidence.

- [ ] **Step 7: Commit governed bootstrap capabilities**

```bash
git add backend/db/migrations/domains/simulation/0006_connector_pairing_activation.sql plugins/simulation/simulation_backend/domain/connector_pairing.py plugins/simulation/simulation_backend/data/connector_repository.py plugins/simulation/simulation_backend/capabilities/connector_contracts.py plugins/simulation/simulation_backend/capabilities/connector_pairing.py plugins/simulation/simulation_backend/capabilities/provider.py backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_capability_ownership.py
git commit -m "feat(simulation): add governed connector bootstrap tickets"
```

### Task 3: Keep HTTP adapters thin and eliminate raw 500s

**Files:**
- Modify: `backend/routers/simulation_connector.py`
- Test: `backend/tests/test_simulation_connector_http_api.py`
- Test: `backend/tests/test_connector_runtime_control_plane.py`

**Interfaces:**
- Consumes: Task 2 Capability providers through the canonical Gateway invoke path.
- Produces: local-runtime bootstrap HTTP endpoints and stable HTTP error mapping without direct repository business logic.

- [ ] **Step 1: Add failing route and error tests**

```python
def test_connector_routes_include_activation_and_no_public_code_page_dependency():
    paths = {route.path for route in simulation_connector.router.routes}
    assert "/api/v1/simulation/connectors/pairings/{pairing_id}/activate" in paths

def test_integrity_conflict_is_a_stable_409(monkeypatch):
    monkeypatch.setattr(simulation_connector.default_service, "complete", _raise("connector_binding_conflict"))
    response = client.post("/api/v1/simulation/connectors/pairings/pair-1/complete", json=_proof())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "connector_binding_conflict"
```

- [ ] **Step 2: Run the focused HTTP tests and verify failure**

Run: `python -m pytest backend/tests/test_simulation_connector_http_api.py backend/tests/test_connector_runtime_control_plane.py -q`

- [ ] **Step 3: Add only the Local Runtime adapters needed for claim, complete, and activate**

Use request models with `extra="forbid"`. Do not add a second Web bootstrap API: authenticated Web calls the Gateway capabilities directly. Map proof errors to 403, not-found to 404, conflicts to 409, expired to 410, and provider availability to 503. Never return exception text.

- [ ] **Step 4: Assert route-to-Capability governance mapping**

Extend the route audit fixture so each added route resolves to its exact `simulation.connector.pairing.*@1` capability and stable lifecycle target. Direct `SqlPairingRepository` calls are forbidden in the new handlers.

- [ ] **Step 5: Run HTTP and governance route tests**

Run: `python -m pytest backend/tests/test_simulation_connector_http_api.py backend/tests/test_connector_runtime_control_plane.py backend/tests/test_route_capability_governance.py -q`

Expected: PASS and no unbound public route.

- [ ] **Step 6: Commit HTTP adapters**

```bash
git add backend/routers/simulation_connector.py backend/tests/test_simulation_connector_http_api.py backend/tests/test_connector_runtime_control_plane.py
git commit -m "fix(simulation): expose stable connector pairing adapters"
```

### Task 4: Persist pending pairing material and acknowledge activation

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Service/PendingPairingStore.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/ConnectorPairing.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/DeviceCredentialStore.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/Program.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/ConnectorBrowserPairingTests.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/DeviceCredentialStoreTests.cs`

**Interfaces:**
- Consumes: bootstrap ticket URI, complete endpoint, activate endpoint.
- Produces: `PendingPairingStore.Save/Load/Delete`, `ConnectorPairing.HandleUriAsync(Uri)`, restart-safe completion.

- [ ] **Step 1: Add failing crash-recovery and activation tests**

```csharp
[Fact]
public async Task RestartAfterIssueReusesProtectedPendingKeyAndActivatesAfterReadBack()
{
    await harness.PairUntilCredentialIssuedAsync(failCredentialWrite: true);
    Assert.True(File.Exists(harness.PendingPairingPath));
    Assert.Equal("pending_activation", harness.ServerBindingStatus);
    await harness.RestartAndResumeAsync();
    Assert.Equal("active", harness.ServerBindingStatus);
    Assert.Equal(harness.IssuedEnvelopeHash, harness.ReplayedEnvelopeHash);
    Assert.False(File.Exists(harness.PendingPairingPath));
}
```

- [ ] **Step 2: Run tests and observe loss of the in-memory RSA key**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --no-restore --filter "ConnectorBrowserPairingTests|DeviceCredentialStoreTests"`

Expected: FAIL because the pairing RSA key and verifier currently exist only in process memory and no activation call exists.

- [ ] **Step 3: Implement a DPAPI-protected pending store**

```csharp
public sealed record PendingPairing(
    string BootstrapId, string PairingId, string InstallationId,
    string Verifier, string PrivateKeyPkcs8, string GatewayUrl, DateTimeOffset ExpiresAt);

public interface IPendingPairingStore
{
    void Save(PendingPairing value);
    PendingPairing? Load();
    void Delete();
}
```

Use the same atomic temporary-file pattern as `DeviceCredentialStore`, `ProtectedData` with distinct entropy, `LocalMachine` scope, and zero clear buffers. Persist before claiming the ticket.

- [ ] **Step 4: Replace browser-code flow with ticket handling and activation**

`HandleUriAsync` accepts only `ai00connector://pair`, an allowlisted gateway, `bootstrap_id`, and `bootstrap_token`. It resumes an unexpired stored pairing before creating a new key. After decrypting, save both credential stores, load them back, verify connector/user/installation fields, call `/activate`, then delete pending material. Do not call `Process.Start` for a browser.

- [ ] **Step 5: Keep support CLI as a wrapper over the same state machine**

`pair --ticket-uri <uri> --no-browser` may remain for diagnostics, but must call `HandleUriAsync`; remove the old flow that creates and displays a user code. Unknown arguments fail before network access.

- [ ] **Step 6: Run all Connector unit tests**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --no-restore`

Expected: all tests PASS, including injected write failure and restart recovery.

- [ ] **Step 7: Commit local credential recovery**

```bash
git add local-runtime/src/Ai00.Connector.Service/PendingPairingStore.cs local-runtime/src/Ai00.Connector.Service/ConnectorPairing.cs local-runtime/src/Ai00.Connector.Service/DeviceCredentialStore.cs local-runtime/src/Ai00.Connector.Service/Program.cs local-runtime/tests/Ai00.Connector.Tests/ConnectorBrowserPairingTests.cs local-runtime/tests/Ai00.Connector.Tests/DeviceCredentialStoreTests.cs
git commit -m "fix(connector): recover pairing before activation"
```

### Task 5: Install the always-on Service and custom protocol without idle SessionHost

**Files:**
- Modify: `local-runtime/installer/Product.wxs`
- Create: `local-runtime/src/Ai00.Connector.Tray/PairingPipeClient.cs`
- Create: `local-runtime/src/Ai00.Connector.Service/PairingPipeHost.cs`
- Create: `local-runtime/src/Ai00.Connector.Tray/SessionHostBroker.cs`
- Modify: `local-runtime/src/Ai00.Connector.Tray/Program.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/SessionHostSupervisor.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/Program.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/RuntimeWorker.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/InstallerContractTests.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/SessionOwnershipTests.cs`

**Interfaces:**
- Consumes: `ai00connector://pair` and `ConnectorPairing.HandleUriAsync` from Task 4.
- Produces: Windows protocol registration, single-instance Tray-to-Service forwarding over an ACL-limited named pipe, and on-demand SessionHost lifecycle through the interactive Tray broker.

- [ ] **Step 1: Add failing installer contract tests**

```csharp
Assert.Contains(@"Software\Classes\ai00connector", wix, StringComparison.Ordinal);
Assert.Contains("URL Protocol", wix, StringComparison.Ordinal);
Assert.Contains("Start=\"auto\"", wix, StringComparison.Ordinal);
Assert.DoesNotContain("AI00 Connector SessionHost\" Value=", wix, StringComparison.Ordinal);
Assert.Contains("AI00 Connector Tray", wix, StringComparison.Ordinal);
```

Add a test proving two protocol launches forward to one Tray instance and invalid gateway/parameters never reach the Service.

- [ ] **Step 2: Run installer/session tests and verify they fail**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --no-restore --filter "InstallerContractTests|SessionOwnershipTests"`

- [ ] **Step 3: Register `ai00connector://` and remove SessionHost login autostart**

WiX must register the protocol command to the Tray executable with `"%1"`, retain auto-start LocalService and Tray login startup, and remove the SessionHost `CurrentVersion\Run` value. Do not add a firewall exception or localhost listener.

- [ ] **Step 4: Forward URI requests through an ACL-limited named pipe**

The Tray owns the custom protocol, validates scheme/host/query, and forwards the opaque ticket to the Service. `PairingPipeHost` uses a fixed pipe name, denies network clients, limits messages to 8 KiB, reads the caller SID through named-pipe impersonation, and passes that verified interactive SID to `ConnectorPairing`; it must not trust a SID in URI parameters. The Service never opens a browser.

The same Tray instance exposes a separate fixed control message for SessionHost launch. After the Service leases a plan requiring an interactive adapter, `SessionHostSupervisor` asks the authenticated Tray broker for the bound SID to start exactly one SessionHost in that user's session. This avoids `CreateProcessAsUser` token handling in the Service and avoids a second scheduler loop.

- [ ] **Step 5: Add bounded idle shutdown for SessionHost**

After the last operation completes, SessionHost exits after a configurable five-minute idle interval. A new plan restarts it. Cancellation and Service shutdown release process handles. Tests use a fake clock rather than sleeping.

- [ ] **Step 6: Build MSI inputs and run tests**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --no-restore`

Run: `dotnet build local-runtime/installer/Ai00.Connector.wixproj -c Release --no-restore`

Expected: tests and WiX build PASS; produced MSI contains Service, Tray, SessionHost payload, and protocol registration.

- [ ] **Step 7: Commit installation behavior**

```bash
git add local-runtime/installer/Product.wxs local-runtime/src/Ai00.Connector.Tray/PairingPipeClient.cs local-runtime/src/Ai00.Connector.Service/PairingPipeHost.cs local-runtime/src/Ai00.Connector.Tray/SessionHostBroker.cs local-runtime/src/Ai00.Connector.Tray/Program.cs local-runtime/src/Ai00.Connector.Service/SessionHostSupervisor.cs local-runtime/src/Ai00.Connector.Service/Program.cs local-runtime/src/Ai00.Connector.Service/RuntimeWorker.cs local-runtime/tests/Ai00.Connector.Tests/InstallerContractTests.cs local-runtime/tests/Ai00.Connector.Tests/SessionOwnershipTests.cs
git commit -m "feat(connector): install lightweight always-on runtime"
```

### Task 6: Put the complete binding flow inside the Simulation page

**Files (frontend worktree `E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`):**
- Create: `packages/sim-plugin/web/cad_sim/connector_onboarding.js`
- Create: `packages/sim-plugin/web/cad_sim/connector_onboarding.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/index.html`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `package.json`

**Interfaces:**
- Consumes: Gateway capabilities from Task 2 and `ai00connector://pair` registration from Task 5.
- Produces: `createConnectorOnboarding({invoke, openProtocol, clock})` with `refresh`, `connect`, `approve`, `cancel`, and state subscription; automatic active connector selection.

- [ ] **Step 1: Write failing state-machine tests**

```javascript
test('normal flow never asks for code or device id', async () => {
  const ui = createConnectorOnboarding(harness.dependencies());
  await ui.connect();
  harness.connectorClaims({ device_name: '工位 A', masked_windows_user: 'l***8' });
  await ui.refresh();
  assert.equal(ui.state.kind, 'awaiting_confirmation');
  assert.equal(ui.state.deviceName, '工位 A');
  assert.equal('userCode' in ui.state, false);
  assert.equal('connectorDeviceId' in ui.state, false);
});

test('offline active binding does not start a new pairing', async () => {
  harness.binding({ status: 'offline', connector_id: 'connector-1' });
  await ui.refresh();
  assert.equal(ui.state.kind, 'offline');
  assert.equal(harness.callsFor('simulation.connector.pairing.bootstrap.create').length, 0);
});
```

- [ ] **Step 2: Run Node tests and verify the module is missing**

Run: `node --test packages/sim-plugin/web/cad_sim/connector_onboarding.test.js`

- [ ] **Step 3: Implement the pure onboarding state controller**

Use only `_invokeCapability`. `connect()` invokes bootstrap create then calls `openProtocol(ticket.uri)`. `refresh()` polls bootstrap get with bounded backoff and stops on active, cancelled, expired, component unmount, or 120 seconds. `approve()` calls the existing confirmation-aware Gateway flow; do not synthesize or bypass confirmation.

- [ ] **Step 4: Replace device-ID input with one status card**

Remove `connectorDeviceId`. Add one card containing layered status rows for Service, SessionHost, Adapter, and VisMockup plus contextual actions: install, connect, confirm, recover, diagnose, and launch VisMockup. Escape all server text with existing `_esc` before HTML insertion.

- [ ] **Step 5: Auto-select the current user's active connector**

Feed `binding.connector_id` directly into the existing governed capture workflow. If binding is absent, offline, pending activation, or incompatible, disable capture with a precise user message. Never accept a typed connector ID.

- [ ] **Step 6: Keep the legacy pair page hidden**

Do not link `web/simulation_connector/pair.html` from Simulation, workbench, installer, or Tray. Leave it available only for the declared compatibility period.

- [ ] **Step 7: Run frontend tests and production build**

Run: `node --test packages/sim-plugin/web/cad_sim/connector_onboarding.test.js packages/sim-plugin/web/cad_sim/capture_workflow.test.js`

Run: `npm run test:simulation-p0-boundary`

Run: `npm run build:web`

Expected: all tests and build PASS; production scan contains no loopback fetch and no device-ID input.

- [ ] **Step 8: Commit frontend onboarding**

```bash
git add packages/sim-plugin/web/cad_sim/connector_onboarding.js packages/sim-plugin/web/cad_sim/connector_onboarding.test.js packages/sim-plugin/web/cad_sim/index.html packages/sim-plugin/web/cad_sim/cad_sim.css packages/sim-plugin/web/cad_sim/cad_sim.js package.json
git commit -m "feat(simulation): connect local runtime from simulation page"
```

### Task 7: Enforce idle resource budgets

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Service/RuntimeWorker.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/RuntimeOptions.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/IdleRuntimeTests.cs`
- Create: `local-runtime/scripts/measure_idle_runtime.ps1`
- Modify: `local-runtime/README.md`

**Interfaces:**
- Consumes: Service/SessionHost lifecycle from Task 5.
- Produces: jittered bounded polling, no idle business processes, repeatable ten-minute resource report.

- [ ] **Step 1: Add fake-clock tests for idle traffic and backoff**

```csharp
[Fact]
public async Task IdleWorkerUsesOneSharedLeaseLoopAndBacksOffAfterFailure()
{
    await worker.AdvanceAsync(TimeSpan.FromMinutes(10));
    Assert.InRange(gateway.HeartbeatCalls, 9, 21);
    Assert.InRange(gateway.LeaseCalls, 9, 121);
    Assert.Equal(0, sessionHost.LaunchCalls);
    Assert.True(gateway.Delays.Zip(gateway.Delays.Skip(1)).All(x => x.Second >= x.First || x.Second == options.PollCeiling));
}
```

- [ ] **Step 2: Run idle tests and verify current fixed-delay behavior fails**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --no-restore --filter IdleRuntimeTests`

- [ ] **Step 3: Implement one shared wait loop with jittered exponential backoff**

Reset backoff after a successful server response, cap it at 60 seconds, and honor cancellation immediately. Do not add per-Adapter timers. Heartbeat remains independently scheduled and does not cause SessionHost launch.

- [ ] **Step 4: Add a measurement script with hard exit criteria**

The script samples Service and Tray once per second for ten minutes and emits JSON with average CPU, peak private working set, handle delta, thread delta, request count, and whether SessionHost/Adapter processes appeared. Exit nonzero when average CPU is at least 1%, combined private working set exceeds 100 MB, or any idle business process appears.

- [ ] **Step 5: Run unit tests and a shortened development sample**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --no-restore`

Run: `powershell -ExecutionPolicy Bypass -File local-runtime/scripts/measure_idle_runtime.ps1 -DurationSeconds 60 -OutputPath .runtime/connector-idle-dev.json`

Expected: unit tests PASS. The 60-second result is diagnostic only; release evidence still requires ten minutes.

- [ ] **Step 6: Commit resource enforcement**

```bash
git add local-runtime/src/Ai00.Connector.Service/RuntimeWorker.cs local-runtime/src/Ai00.Connector.Service/RuntimeOptions.cs local-runtime/tests/Ai00.Connector.Tests/IdleRuntimeTests.cs local-runtime/scripts/measure_idle_runtime.ps1 local-runtime/README.md
git commit -m "perf(connector): enforce lightweight idle runtime"
```

### Task 8: Regenerate governance artifacts and perform end-to-end acceptance

**Files:**
- Regenerate: `backend/capability_v2/official_domains.json`
- Regenerate: `backend/tests/acceptance/fixtures/case-manifest.json`
- Regenerate: `docs/capabilities/catalog.v2.json`
- Regenerate: `docs/capabilities/openapi-fragment.v2.json`
- Regenerate: `docs/capabilities/simulation/*.md`
- Regenerate: `docs/governance/capability-catalog-lineage.json`
- Regenerate: `docs/governance/capability-catalog-release.json`
- Create: `docs/audits/2026-09-06-simulation-connector-onboarding-runtime.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: catalog-consistent build plus machine, runtime, and human-approval evidence separation.

- [ ] **Step 1: Regenerate the Catalog and documents**

Run: `python backend/scripts/build_capability_catalog.py`

Run: `python backend/scripts/generate_capability_docs.py`

Run: `python backend/scripts/build_capability_acceptance_manifest.py`

Do not hand-edit generated hashes or release metadata.

- [ ] **Step 2: Run static Capability gates**

Run: `python backend/scripts/build_capability_catalog.py --check`

Run: `python backend/scripts/generate_capability_docs.py --check`

Run: `python backend/scripts/build_capability_acceptance_manifest.py --check`

Run: `python backend/scripts/check_domain_dependencies.py`

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`

Expected: every command exits 0; all new routes and consumers bind to stable or explicitly experimental targets permitted by the release profile.

- [ ] **Step 3: Run backend, Connector, and frontend regression suites**

Run: `python -m pytest backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_pairing_sql.py backend/tests/test_simulation_connector_http_api.py backend/tests/test_connector_runtime_control_plane.py -q`

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --no-restore`

Run in frontend worktree: `npm run test:simulation-p0-boundary`

Run in frontend worktree: `npm run build:web`

- [ ] **Step 4: Apply migration to test-prefixed tables through the controlled migration runner**

Apply `0006` to `test_workmanship_*` only. Verify columns/checks/indexes through schema inventory. Do not modify production tables in this task.

- [ ] **Step 5: Install the test MSI and run the real user journey**

Verify Windows Service is automatic and running, Tray is visible, SessionHost is absent while idle, and `ai00connector://` is registered. From the Simulation page click connect, inspect the device summary, personally confirm once, verify DPAPI credential files, activation, heartbeat, and automatic connector selection. No code or device ID may be entered.

- [ ] **Step 6: Exercise recovery and VisMockup**

Inject a credential-write failure between issue and activation, restart Connector, and verify recovery creates no second binding. Then launch real VisMockup through the governed page operation and verify Service, SessionHost, Adapter, COM, and page state agree.

- [ ] **Step 7: Capture ten-minute idle evidence**

Run: `powershell -ExecutionPolicy Bypass -File local-runtime/scripts/measure_idle_runtime.ps1 -DurationSeconds 600 -OutputPath .runtime/connector-idle-release.json`

Record commit IDs, MSI SHA-256, catalog release, database snapshot identifier, test results, process/resource measurements, and VisMockup observations in the audit file. Set `runtime_verified=true` only if the real chain passes. Leave `human_approved=false` until the super administrator approves the business definitions in Governance Center.

- [ ] **Step 8: Commit generated evidence without unrelated working-tree files**

```bash
git add backend/capability_v2/official_domains.json backend/tests/acceptance/fixtures/case-manifest.json docs/capabilities docs/governance/capability-catalog-lineage.json docs/governance/capability-catalog-release.json docs/audits/2026-09-06-simulation-connector-onboarding-runtime.md
git commit -m "test(simulation): verify connector product onboarding"
```

## Final Release Gate

- [ ] Backend, frontend, Connector, installer, Catalog, docs, domain dependency, route governance, and offline acceptance checks all pass on the exact commits being released.
- [ ] Test database contains exactly one active binding for the tested user/installation and no abandoned duplicate binding from injected failure.
- [ ] The Simulation page reaches active Connector and real VisMockup without an independent pairing page, copied code, typed device ID, localhost fetch, or raw provider error.
- [ ] Ten-minute idle resource evidence meets CPU/process criteria and either meets the `100 MB` memory target or emits a blocking performance Finding.
- [ ] Runtime report records `machine_passed`, `runtime_verified`, and `human_approved` independently.
