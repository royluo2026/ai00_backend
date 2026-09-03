# AI00 Connector and VisMockup Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize the Windows Local Runtime as AI00 Connector, execute signed plans through a versioned Adapter host, and complete real VisMockup environment materialization and internal reverse-process capture.

**Architecture:** A Windows Service owns outbound control-plane traffic, secure device identity, artifact transfer and updates. A single per-user SessionHost owns the STA Adapter queue; the built-in VisMockup Adapter is the only phase-one implementation, while a fail-closed MCP Adapter contract preserves future expansion.

**Tech Stack:** .NET 8, C# 12, Windows Service, named pipes, COM interop through dynamic dispatch, Windows DPAPI/Credential Manager, native Power Request API, WiX Toolset/MSI, xUnit.

**Spec:** `docs/superpowers/specs/2026-09-03-simulation-ai00-connector-governance-design.md`

**Depends on:** `docs/superpowers/plans/2026-09-03-simulation-domain-environment-capture.md` Plan A completion gate and its frozen `ai00.connector.execution-plan.v1` vector.

## Global Constraints

- Product and installer name is `AI00 Connector`; it does not replace the AI00 web application.
- One device binds one AI00 user and runs one active SessionHost; VisMockup operations are strictly serialized on one STA queue.
- All network traffic is outbound HTTPS; no localhost HTTP listener and no inbound customer firewall rule.
- Locked screen and display-off are allowed; logged-out, SessionHost-missing, sleeping/hibernating and incompatible-product states block work.
- Use VisMockup internal `ActiveView.CaptureImage`; do not use Windows screen capture APIs.
- Use a temporary native Power Request only while a plan is active; never permanently change a power plan.
- No arbitrary COM method, script or MCP tool execution; operation IDs and contract hashes must be allowlisted.
- Device secrets are protected by DPAPI/Windows Credential Manager or certificate storage; no production secret in JSON, registry plaintext, logs or command line.
- A fake COM server can establish `machine_passed`; only an installed, real VisMockup pilot run can establish `runtime_verified`.

---

## File Map

- `local-runtime/src/Ai00.Connector.Contracts/`: ExecutionPlan, Adapter manifest, health and signed outcome contracts.
- `local-runtime/src/Ai00.Connector.Service/`: Service lifecycle, Gateway client, secure credentials, plan journal, artifacts, power guard and updater.
- `local-runtime/src/Ai00.Connector.SessionHost/`: current-user named pipe and Adapter host.
- `local-runtime/src/Ai00.Connector.Adapters.VisMockup/`: VisMockup-specific COM implementation.
- `local-runtime/src/Ai00.Connector.Adapters.Mcp/`: fail-closed MCP discovery/mapping extension.
- `local-runtime/src/Ai00.Connector.Tray/`: minimal pairing/status/diagnostics UI.
- `local-runtime/installer/`: signed MSI and per-user SessionHost registration.
- `local-runtime/tests/`: unit, protocol, fake COM and installer tests.

### Task 1: Establish AI00 Connector Naming and Solution Boundaries

**Files:**
- Modify: `local-runtime/Ai00.LocalRuntime.sln`
- Create: `local-runtime/src/Ai00.Connector.Contracts/Ai00.Connector.Contracts.csproj`
- Create: `local-runtime/src/Ai00.Connector.Service/Ai00.Connector.Service.csproj`
- Create: `local-runtime/src/Ai00.Connector.SessionHost/Ai00.Connector.SessionHost.csproj`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/Ai00.Connector.Adapters.VisMockup.csproj`
- Modify: `local-runtime/Directory.Build.props`
- Modify: `local-runtime/README.md`
- Create: `local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj`

**Interfaces:**
- Produces: projects named `Ai00.Connector.*`; assembly version remains independent from protocol and Adapter versions.
- Consumes: no runtime behavior yet; existing code is moved without semantic changes.

- [ ] **Step 1: Add a failing solution-layout test**

```csharp
[Fact]
public void ProductAssembliesUseConnectorName()
{
    var names = typeof(ConnectorExecutionPlan).Assembly.GetReferencedAssemblies().Select(x => x.Name);
    Assert.DoesNotContain(names, x => x!.StartsWith("Ai00.LocalRuntime", StringComparison.Ordinal));
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release`

Expected: test project/type is missing.

- [ ] **Step 3: Create focused projects and move existing classes**

Move contracts, Service and SessionHost code with namespace-only changes. Extract `VisMockupAdapter` into its project and define `IConnectorAdapter` in Contracts:

```csharp
public interface IConnectorAdapter
{
    AdapterManifest Manifest { get; }
    Task<AdapterHealth> ProbeAsync(CancellationToken cancellationToken);
    Task<AdapterResult> ExecuteAsync(AdapterOperation operation, CancellationToken cancellationToken);
}
```

- [ ] **Step 4: Build and run unchanged-behavior tests**

Run: `dotnet build local-runtime/Ai00.LocalRuntime.sln -c Release`

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --no-build`

Expected: build and tests pass.

- [ ] **Step 5: Commit**

```bash
git add local-runtime
git commit -m "refactor(connector): establish product and adapter boundaries"
```

### Task 2: Implement Cross-Language Plans and Signed Adapter Manifests

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Contracts/ExecutionPlan.cs`
- Create: `local-runtime/src/Ai00.Connector.Contracts/AdapterManifest.cs`
- Create: `local-runtime/src/Ai00.Connector.Contracts/CanonicalJson.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/ExecutionPlanVectorTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/AdapterManifestTests.cs`

**Interfaces:**
- Produces: `ConnectorExecutionPlan`, `ConnectorStep`, `AdapterManifest`, `AdapterOperationContract`, `PlanValidator.Validate(...)`.
- Consumes: Plan A checked-in JSON vector and service signing key ring.

- [ ] **Step 1: Write failing Python-vector compatibility tests**

```csharp
[Fact]
public void PythonPlanVectorHasIdenticalCanonicalHash()
{
    var vector = TestVector.Load("connector_execution_plan_v1.json");
    var plan = JsonSerializer.Deserialize<ConnectorExecutionPlan>(vector.PlanJson, Json.Options)!;
    Assert.Equal(vector.PlanHash, plan.ComputeHash());
}

[Fact]
public void UnknownOperationIsRejectedBeforeAnyAdapterCall()
{
    var error = PlanValidator.Validate(Plan.WithOperation("vismockup.raw.com@1"), Manifests.VisMockup);
    Assert.Equal("adapter_operation_not_allowed", error.Code);
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter ExecutionPlanVectorTests`

Expected: missing contract types.

- [ ] **Step 3: Implement exact v1 models and validation**

Reject bad signature, plan/payload hash, expiry, wrong device/user, unsupported protocol, Adapter major, operation ID, contract hash, duplicate step and invalid dependency before creating an Adapter instance.

```csharp
public static PlanValidationResult Validate(ConnectorExecutionPlan plan, AdapterManifest manifest, ValidationContext context)
{
    if (plan.ExpiresAt <= context.UtcNow) return PlanValidationResult.Fail("plan_expired");
    if (plan.DeviceId != context.DeviceId || plan.UserId != context.UserId) return PlanValidationResult.Fail("plan_identity_mismatch");
    foreach (var step in plan.Steps)
        if (!manifest.Supports(step.OperationId, step.ContractHash)) return PlanValidationResult.Fail("adapter_contract_mismatch");
    return PlanValidationResult.Success();
}
```

- [ ] **Step 4: Implement signed Adapter manifest loading**

Load built-in manifests from assembly resources; load future external manifests only from the administrator allowlisted directory and require organization signature plus Authenticode-signed assembly.

```csharp
public AdapterManifest LoadBuiltIn(Assembly assembly, string resourceName)
{
    using var stream = assembly.GetManifestResourceStream(resourceName) ?? throw new ConnectorException("adapter_manifest_missing");
    var manifest = JsonSerializer.Deserialize<AdapterManifest>(stream, Json.Options) ?? throw new ConnectorException("adapter_manifest_invalid");
    signatureVerifier.RequireTrusted(manifest, assembly.Location);
    return manifest;
}
```

- [ ] **Step 5: Run contract suite**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "ExecutionPlanVectorTests|AdapterManifestTests"`

Expected: all tests pass and the Python vector hash matches exactly.

- [ ] **Step 6: Commit**

```bash
git add local-runtime/src/Ai00.Connector.Contracts local-runtime/tests/Ai00.Connector.Tests
git commit -m "feat(connector): validate signed plans and adapter manifests"
```

### Task 3: Enforce Single-User SessionHost and Secure Device Identity

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Service/DeviceCredentialStore.cs`
- Create: `local-runtime/src/Ai00.Connector.Service/SessionHostSupervisor.cs`
- Create: `local-runtime/src/Ai00.Connector.SessionHost/SingleInstanceGuard.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/Program.cs`
- Modify: `local-runtime/src/Ai00.Connector.SessionHost/Program.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/SessionOwnershipTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/DeviceCredentialStoreTests.cs`

**Interfaces:**
- Produces: `IDeviceCredentialStore`, `SessionHostSupervisor.GetHealthAsync()`, per-device/user named mutex and current-user named pipe ACL.
- Consumes: enrolled device ID, bound Windows SID and AI00 user ID.

- [ ] **Step 1: Write failing ownership and plaintext-secret tests**

```csharp
[Fact]
public async Task SecondSessionHostForDeviceIsRejected()
{
    using var first = SingleInstanceGuard.Acquire("device-1", CurrentSid);
    var error = Assert.Throws<ConnectorException>(() => SingleInstanceGuard.Acquire("device-1", CurrentSid));
    Assert.Equal("interactive_session_conflict", error.Code);
}

[Fact]
public void StoredCredentialDoesNotContainPlaintextToken()
{
    store.Save(new DeviceCredential("device-1", "secret-token"));
    Assert.DoesNotContain("secret-token", File.ReadAllText(store.StoragePath));
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "SessionOwnershipTests|DeviceCredentialStoreTests"`

Expected: missing implementations.

- [ ] **Step 3: Implement DPAPI credential protection and SID binding**

Use `ProtectedData.Protect(..., DataProtectionScope.LocalMachine)` with an ACL restricted to Service SID; bind stored metadata to device ID, AI00 user ID and allowed Windows SID. Never pass the token on a process command line.

```csharp
public void Save(DeviceCredential credential)
{
    var clear = JsonSerializer.SerializeToUtf8Bytes(credential, Json.Options);
    var cipher = ProtectedData.Protect(clear, Entropy, DataProtectionScope.LocalMachine);
    atomicFile.Write(StoragePath, cipher, serviceOnlyAcl);
}
```

- [ ] **Step 4: Implement supervisor and one SessionHost**

The Service observes logged-on sessions, launches SessionHost only for the bound SID, reports missing/logged-out/conflict states, and never executes COM inside Session 0. Named pipe remains `CurrentUserOnly` and additionally verifies the peer PID/SID.

```csharp
public async Task<SessionHealth> EnsureBoundSessionAsync(DeviceBinding binding, CancellationToken ct)
{
    var sessions = windowsSessions.ForSid(binding.WindowsSid);
    if (sessions.Count == 0) return SessionHealth.Missing;
    if (sessions.Count > 1) return SessionHealth.Conflict;
    await launcher.EnsureSessionHostAsync(sessions.Single(), binding.DeviceId, ct);
    return SessionHealth.Ready;
}
```

- [ ] **Step 5: Run tests**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "SessionOwnershipTests|DeviceCredentialStoreTests"`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add local-runtime/src/Ai00.Connector.Service local-runtime/src/Ai00.Connector.SessionHost local-runtime/tests/Ai00.Connector.Tests
git commit -m "feat(connector): secure device identity and user session"
```

### Task 4: Add Durable Plan Journal, Leasing and Reconciliation

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Service/PlanJournal.cs`
- Create: `local-runtime/src/Ai00.Connector.Service/ConnectorGatewayClient.cs`
- Create: `local-runtime/src/Ai00.Connector.Service/PlanWorker.cs`
- Create: `local-runtime/src/Ai00.Connector.SessionHost/AdapterDispatcher.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/PlanRecoveryTests.cs`

**Interfaces:**
- Produces: durable `PlanState` and `StepState`; exact-once local admission by `plan_id`; signed outcome reconciliation.
- Consumes: Tasks 2-3 and Plan A `/api/v1/connector/*` endpoints.

- [ ] **Step 1: Write failing restart and replay tests**

```csharp
[Fact]
public async Task RestartReconcilesStartedStepBeforeLeasingAnotherPlan()
{
    journal.RecordStarted("plan-1", "step-1");
    await worker.StartOnceAsync();
    Assert.Equal("plan-1", gateway.FirstReconciliation.PlanId);
    Assert.Equal(0, gateway.LeaseCallsBeforeReconciliation);
}

[Fact]
public async Task CompletedPlanReplayReturnsRetainedSignedOutcome()
{
    journal.RecordCompleted("plan-1", SignedOutcomes.Success);
    var result = await worker.AcceptAsync(Plans.WithId("plan-1"));
    Assert.Equal(SignedOutcomes.Success, result);
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter PlanRecoveryTests`

Expected: missing journal/worker types.

- [ ] **Step 3: Implement append-only local journal and atomic snapshots**

Persist plan admission, step start, step result hash, artifact upload state and final signed outcome under ProgramData with Service-only ACL. Use write-temp + flush + atomic replace; retain completed outcomes through the server reconciliation window.

```csharp
public void Append(JournalRecord record)
{
    lock (_gate)
    {
        _records.Add(record);
        atomicFile.Replace(_path, JsonSerializer.SerializeToUtf8Bytes(_records, Json.Options));
    }
}
```

- [ ] **Step 4: Implement outbound heartbeat/lease/complete loop**

Heartbeat advertises exact protocol, Connector version, SID-bound session, power state, Adapter/product versions and operation contract hashes. Back off network failures; never drop an active local plan lease silently.

```csharp
while (!stoppingToken.IsCancellationRequested)
{
    await gateway.HeartbeatAsync(await health.BuildAsync(stoppingToken), stoppingToken);
    if (journal.HasUnreconciledPlan) await reconciler.ReconcileAsync(stoppingToken);
    else if (await gateway.LeaseAsync(stoppingToken) is { } plan) await executor.ExecuteAsync(plan, stoppingToken);
    await delay.WaitAsync(backoff.Next(), stoppingToken);
}
```

- [ ] **Step 5: Run recovery and protocol tests**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "PlanRecoveryTests|ExecutionPlanVectorTests"`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add local-runtime/src/Ai00.Connector.Service local-runtime/src/Ai00.Connector.SessionHost local-runtime/tests/Ai00.Connector.Tests
git commit -m "feat(connector): persist and reconcile execution plans"
```

### Task 5: Implement Artifact Transfer and Temporary Power Guard

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Service/ArtifactTransfer.cs`
- Create: `local-runtime/src/Ai00.Connector.Service/SystemPowerGuard.cs`
- Create: `local-runtime/src/Ai00.Connector.Service/TemporaryFileStore.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/ArtifactTransferTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/SystemPowerGuardTests.cs`

**Interfaces:**
- Produces: verified input materialization, resumable output upload, bounded cleanup and `ISystemPowerGuard.Acquire(planId)`.
- Consumes: signed ArtifactRef and one-time plan-scoped upload/download URLs.

- [ ] **Step 1: Write failing integrity and lifecycle tests**

```csharp
[Fact]
public async Task HashMismatchDeletesMaterializedInputAndFailsClosed()
{
    var error = await Assert.ThrowsAsync<ConnectorException>(() => transfer.DownloadAsync(BadHashArtifact));
    Assert.Equal("artifact_integrity_failed", error.Code);
    Assert.False(File.Exists(error.LocalPath));
}

[Fact]
public void PowerRequestIsReleasedWhenPlanThrows()
{
    Assert.Throws<InvalidOperationException>(() => { using var guard = power.Acquire("plan-1"); throw new InvalidOperationException(); });
    Assert.Equal(1, native.ReleaseCalls);
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "ArtifactTransferTests|SystemPowerGuardTests"`

Expected: missing services.

- [ ] **Step 3: Implement bounded artifact storage and upload reconciliation**

Validate artifact ID, size, SHA-256 and extension; store only under the Connector cache root. Persist upload session before transfer, query status after ambiguous responses, and never recapture to replace an unconfirmed upload.

```csharp
public async Task<MaterializedArtifact> DownloadAsync(ArtifactRef artifact, CancellationToken ct)
{
    var path = files.PathFor(artifact.ArtifactId);
    await gateway.DownloadAsync(artifact, path, ct);
    if (new FileInfo(path).Length != artifact.ByteSize || Sha256.File(path) != artifact.Sha256)
        throw files.DeleteAndError(path, "artifact_integrity_failed");
    return new(artifact.ArtifactId, path, artifact.Sha256, artifact.ByteSize);
}
```

- [ ] **Step 4: Implement native Power Request RAII wrapper**

Use `PowerCreateRequest`, `PowerSetRequest(PowerRequestSystemRequired)`, `PowerClearRequest`, and `CloseHandle`. Acquire only while executing an admitted plan; release in `Dispose` on success, failure and cancellation. Do not request display-required state.

```csharp
public IDisposable Acquire(string planId)
{
    var handle = native.PowerCreateRequest($"AI00 Connector plan {planId}");
    native.PowerSetRequest(handle, PowerRequestType.SystemRequired);
    return new PowerLease(handle, native);
}
```

- [ ] **Step 5: Run tests**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "ArtifactTransferTests|SystemPowerGuardTests"`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add local-runtime/src/Ai00.Connector.Service local-runtime/tests/Ai00.Connector.Tests
git commit -m "feat(connector): secure artifacts and prevent active-job sleep"
```

### Task 6: Implement VisMockup Probe and Active Document Snapshot

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupConnection.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/DocumentSnapshotReader.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/FakeVisMockupCom.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/VisMockupSnapshotTests.cs`

**Interfaces:**
- Produces: `vismockup.application.probe@1` and `vismockup.document.snapshot@1`.
- Consumes: only COM objects reached from the verified active VisMockup application/document.

- [ ] **Step 1: Write failing attach-vs-launch and bounded-tree tests**

```csharp
[Fact]
public async Task ProbeAttachesExistingInstanceWithoutLaunchingAnother()
{
    fakeCom.ExistingApplication = FakeApplication.WithDocument("BOM-1");
    var health = await adapter.ProbeAsync(CancellationToken.None);
    Assert.True(health.DocumentReady);
    Assert.Equal(0, fakeCom.LaunchCalls);
}

[Fact]
public async Task SnapshotRejectsTreeBeyondNodeLimit()
{
    fakeCom.ExistingApplication = FakeApplication.WithNodes(10_001);
    var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.SnapshotAsync(maxNodes: 10_000, maxDepth: 64));
    Assert.Equal("bom_snapshot_limit_exceeded", error.Code);
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter VisMockupSnapshotTests`

Expected: missing Adapter implementation.

- [ ] **Step 3: Implement explicit active-instance connection semantics**

Use the verified VisMockup-supported active-object path first. Launch only when the operation payload explicitly permits it, then wait with a bounded timeout. Never call `Activator.CreateInstance` during a probe intended to attach the user's open document.

```csharp
public object RequireActiveApplication(bool allowLaunch)
{
    if (com.TryGetActiveObject(ProgId, out var app)) return app;
    if (!allowLaunch) throw new ConnectorException("vismockup_unavailable");
    launcher.Start();
    return com.WaitForActiveObject(ProgId, TimeSpan.FromSeconds(30));
}
```

- [ ] **Step 4: Implement iterative bounded snapshot traversal**

Return root/document/source identity, stable node key, parent key, printable name, occurrence/model identifiers and child order. Enforce `max_nodes=10000`, `max_depth=64`, detect duplicate/cyclic node keys, canonicalize and hash the complete snapshot.

```csharp
while (queue.TryDequeue(out var current))
{
    if (nodes.Count == maxNodes) throw new ConnectorException("bom_snapshot_limit_exceeded");
    if (current.Depth > maxDepth || !seen.Add(current.NodeKey)) throw new ConnectorException("bom_snapshot_invalid");
    nodes.Add(reader.ReadNode(current));
    foreach (var child in reader.Children(current).Reverse()) queue.Enqueue(child);
}
```

- [ ] **Step 5: Run tests on one STA thread**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "VisMockupSnapshotTests|AdapterManifestTests"`

Expected: all tests pass and fake COM records one thread/apartment.

- [ ] **Step 6: Commit**

```bash
git add local-runtime/src/Ai00.Connector.Adapters.VisMockup local-runtime/tests/Ai00.Connector.Tests
git commit -m "feat(connector): snapshot active VisMockup documents"
```

### Task 7: Materialize and Verify VisMockup Scenes

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/ModelAttacher.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/SceneController.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/InternalCapture.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/VisMockupSceneTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/VisMockupCaptureTests.cs`

**Interfaces:**
- Produces: `vismockup.model.attach@1`, `vismockup.scene.apply@1`, `vismockup.scene.verify@1`, `vismockup.view.capture@1`.
- Consumes: Task 5 verified local Artifact paths and Task 6 active document identity.

- [ ] **Step 1: Write failing full-state and internal-capture tests**

```csharp
[Fact]
public async Task ApplyUsesCompleteExpectedSetsAndConvergesOnReplay()
{
    await adapter.ApplySceneAsync(Scene.Visible("P-1", "P-2").WithResource("T-1"));
    await adapter.ApplySceneAsync(Scene.Visible("P-1", "P-2").WithResource("T-1"));
    Assert.Equal(new[] { "P-1", "P-2", "T-1" }, fakeCom.VisibleNodeKeys.Order());
}

[Fact]
public async Task CaptureUsesVisMockupActiveViewNotDesktopApi()
{
    var artifact = await adapter.CaptureAsync(CaptureProfile.Png(1920, 1080));
    Assert.Equal(1, fakeCom.ActiveView.CaptureImageCalls);
    Assert.Equal(0, fakeDesktopCapture.Calls);
    Assert.Equal("image/png", artifact.MediaType);
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "VisMockupSceneTests|VisMockupCaptureTests"`

Expected: missing scene/capture implementations.

- [ ] **Step 3: Implement model attach with document/hash guards**

Before every attach verify active document ID and baseline snapshot hash. Validate the materialized model artifact, attach through documented COM, return the created node binding and reject duplicate/ambiguous attachment outcomes.

```csharp
public NodeBinding Attach(AttachRequest request)
{
    documentGuard.Require(request.DocumentId, request.BaselineSnapshotHash);
    pathPolicy.RequireVerifiedArtifact(request.ArtifactPath, request.ArtifactSha256);
    var created = com.AttachModel(request.ArtifactPath);
    return nodeResolver.RequireSingleCreatedNode(created, request.BindingId);
}
```

- [ ] **Step 4: Implement full scene apply and verification**

Resolve only manifest node keys, set the complete expected visibility state, apply current-operation resource state and capture profile, then compute the actual visible-node/profile hash. Never infer missing nodes or silently keep unknown visibility.

```csharp
public string Apply(SceneState expected)
{
    var known = nodes.RequireAll(expected.AllNodeKeys);
    foreach (var node in known) com.SetVisible(node, expected.VisibleNodeKeys.Contains(node.Key));
    captureProfile.Apply(expected.CaptureProfile);
    return Verify(expected).ActualSceneHash;
}
```

- [ ] **Step 5: Implement internal capture and artifact metadata**

Call `documents.Item(1).ActiveView.CaptureImage(tempPath)`, verify the file exists and is nonempty, inspect PNG signature and dimensions, compute SHA-256 and return a local Artifact descriptor. A retry creates a new attempt/path.

```csharp
public LocalArtifact Capture(CaptureRequest request)
{
    var path = files.NewAttemptPath(request.PlanId, request.StepId, request.Attempt, ".png");
    com.ActiveView.CaptureImage(path);
    png.RequireValid(path, request.Width, request.Height);
    return LocalArtifact.FromFile(path, "image/png");
}
```

- [ ] **Step 6: Run tests and commit**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "VisMockupSceneTests|VisMockupCaptureTests"`

Expected: all tests pass.

```bash
git add local-runtime/src/Ai00.Connector.Adapters.VisMockup local-runtime/tests/Ai00.Connector.Tests
git commit -m "feat(connector): materialize and capture VisMockup scenes"
```

### Task 8: Add a Fail-Closed MCP Adapter Extension

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Adapters.Mcp/Ai00.Connector.Adapters.Mcp.csproj`
- Create: `local-runtime/src/Ai00.Connector.Adapters.Mcp/McpAdapter.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.Mcp/McpToolMapping.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/McpAdapterPolicyTests.cs`
- Modify: `local-runtime/Ai00.LocalRuntime.sln`

**Interfaces:**
- Produces: disabled-by-default MCP stdio/local/intranet client and explicit `AI00 capability -> MCP tool + schema hash` mapping.
- Consumes: signed administrator allowlist and Adapter-scoped credential references.

- [ ] **Step 1: Write failing deny-by-default tests**

```csharp
[Fact]
public async Task DiscoveredToolWithoutGovernedMappingIsNotAdvertised()
{
    server.Tools = [new("feishu.send_message", InputSchemaHash)];
    var manifest = await adapter.BuildManifestAsync();
    Assert.Empty(manifest.Operations);
}

[Fact]
public async Task SchemaDriftDisablesMappedTool()
{
    mappings.Allow("knowledge.feishu.read@1", "feishu.search", ExpectedHash);
    server.Tools = [new("feishu.search", DifferentHash)];
    var health = await adapter.ProbeAsync(CancellationToken.None);
    Assert.Equal("mcp_tool_contract_mismatch", health.ErrorCode);
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter McpAdapterPolicyTests`

Expected: MCP Adapter types missing.

- [ ] **Step 3: Implement minimal JSON-RPC stdio client and mapping gate**

Support initialize, tools/list and tools/call only. Do not implement resources, prompts or arbitrary server installation in phase one. Validate every input/output against the pinned schema hash and redact configured sensitive fields.

```csharp
public async Task<AdapterResult> ExecuteAsync(AdapterOperation operation, CancellationToken ct)
{
    var mapping = mappings.Require(operation.OperationId, operation.ContractHash);
    schemas.ValidateInput(mapping.InputSchema, operation.Payload);
    var result = await client.CallToolAsync(mapping.ToolName, operation.Payload, ct);
    schemas.ValidateOutput(mapping.OutputSchema, result);
    return AdapterResult.Completed(redactor.Apply(result, mapping.SensitiveFields));
}
```

- [ ] **Step 4: Keep cloud SaaS server-preferred**

The configuration must reject `https` cloud endpoints unless an administrator marks the endpoint `local_dependency_required=true` with an audited reason. Do not ship a Feishu credential or mapping in the default installer.

```csharp
if (endpoint.Scheme == Uri.UriSchemeHttps && (!config.LocalDependencyRequired || string.IsNullOrWhiteSpace(config.AuditReason)))
    throw new ConnectorException("cloud_mcp_server_preferred");
```

- [ ] **Step 5: Run tests and commit**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter McpAdapterPolicyTests`

Expected: all tests pass.

```bash
git add local-runtime/src/Ai00.Connector.Adapters.Mcp local-runtime/tests/Ai00.Connector.Tests local-runtime/Ai00.LocalRuntime.sln
git commit -m "feat(connector): add governed MCP adapter extension"
```

### Task 9: Build the Installer, Tray and Signed Update Path

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Tray/Ai00.Connector.Tray.csproj`
- Create: `local-runtime/src/Ai00.Connector.Tray/Program.cs`
- Create: `local-runtime/src/Ai00.Connector.Tray/StatusView.cs`
- Create: `local-runtime/installer/Ai00.Connector.wixproj`
- Create: `local-runtime/installer/Product.wxs`
- Modify: `local-runtime/src/Ai00.Connector.Service/UpdateManifest.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/UpdateStateMachine.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/InstallerContractTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/UpdateRollbackTests.cs`

**Interfaces:**
- Produces: signed MSI installing Service plus bound-user SessionHost/Tray startup; signed drain/switch/health-check/rollback updates.
- Consumes: administrator installation and organization signing certificate supplied by CI secrets.

- [ ] **Step 1: Write failing installer/update contract tests**

```csharp
[Fact]
public void InstallerRegistersServiceAndPerUserSessionHostWithoutInboundPort()
{
    var wix = File.ReadAllText(ProductWxs);
    Assert.Contains("Ai00ConnectorService", wix);
    Assert.Contains("Ai00ConnectorSessionHost", wix);
    Assert.DoesNotContain("FirewallException", wix);
}

[Fact]
public void FailedPostSwitchHealthCheckRollsBackPreviousSlot()
{
    var state = updater.Apply(SignedPackage, healthCheck: () => false);
    Assert.Equal(UpdateState.RolledBack, state);
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter "InstallerContractTests|UpdateRollbackTests"`

Expected: MSI and completed update behavior missing.

- [ ] **Step 3: Implement minimal tray**

Expose pairing code entry, bound user/device, Service/SessionHost/Adapter/VisMockup health, version, diagnostics export and unlink. Do not expose business workflow controls or raw command execution.

```csharp
var menu = new ContextMenuStrip();
menu.Items.Add("配对", null, (_, _) => pairing.Show());
menu.Items.Add("状态", null, (_, _) => status.Show());
menu.Items.Add("导出诊断", null, async (_, _) => await diagnostics.ExportAsync());
menu.Items.Add("解绑", null, async (_, _) => await pairing.UnlinkAsync());
```

- [ ] **Step 4: Implement MSI and update completion**

Install Service under a restricted service identity, ProgramData ACLs, Event Log source and bound-user startup task. Verify package SHA-256, organization signature and Authenticode before drain/switch; roll back on failed health check.

```xml
<ServiceInstall Id="Ai00ConnectorService" Name="AI00Connector" DisplayName="AI00 Connector" Start="auto" Type="ownProcess" ErrorControl="normal" />
<ServiceControl Id="StartAi00Connector" Name="AI00Connector" Start="install" Stop="both" Remove="uninstall" Wait="yes" />
```

- [ ] **Step 5: Build installer in Windows CI and commit**

Run: `dotnet build local-runtime/Ai00.LocalRuntime.sln -c Release`

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --no-build`

Run: `dotnet build local-runtime/installer/Ai00.Connector.wixproj -c Release`

Expected: solution and MSI build pass; produced binaries are signed in release CI, not with repository test keys.

```bash
git add local-runtime
git commit -m "feat(connector): package signed Windows connector"
```

### Task 10: Complete Server-to-Connector and Real VisMockup Acceptance

**Files:**
- Create: `local-runtime/tests/Ai00.Connector.Tests/ServerContractTests.cs`
- Create: `local-runtime/tests/pilot/run-vismockup-pilot.ps1`
- Create: `local-runtime/tests/pilot/pilot-case.schema.json`
- Create: `docs/runbooks/ai00-connector-vismockup-pilot.md`

**Interfaces:**
- Produces: automated server/Connector contract evidence and a reproducible real-machine pilot procedure.
- Consumes: completed Plan A, Tasks 1-9, installed supported VisMockup and a non-production Craft/BOM fixture.

- [ ] **Step 1: Write failing end-to-end contract test**

```csharp
[Fact]
public async Task ServerPlanCompletesReverseCaptureAndCraftAttachExactlyOnce()
{
    var run = await server.StartCaptureAsync(Pilot.EnvironmentId, connector.DeviceId);
    await connector.RunUntilIdleAsync();
    var result = await server.GetCaptureRunAsync(run.RunId);
    Assert.Equal(new[] { "op-30", "op-20", "op-10" }, result.Steps.Select(x => x.OperationId));
    Assert.All(result.Steps, x => Assert.Equal("attached", x.Status));
}
```

- [ ] **Step 2: Run against fake COM and confirm RED**

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter ServerContractTests`

Expected: FAIL because the server-to-Connector test harness has not been wired.

- [ ] **Step 3: Wire the server test host to the fake Connector and confirm GREEN**

Start the FastAPI test host with the Plan A test database, enroll the fake Connector through the public Device API, lease real signed plans, dispatch them through `FakeVisMockupCom`, upload produced PNG bytes through the real Artifact API and read back Craft associations.

```csharp
await using var server = await Ai00TestServer.StartAsync();
var connector = await FakeConnector.EnrollAsync(server, FakeVisMockupCom.WithBom(Pilot.Bom));
await connector.RunUntilIdleAsync();
Assert.All(await server.GetCraftScreenshotsAsync(Pilot.BopVersion), item => Assert.StartsWith("artifact:", item.ArtifactRef));
```

Run: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release --filter ServerContractTests`

Expected: PASS without claiming real VisMockup runtime verification.

- [ ] **Step 4: Implement pilot script with explicit assertions**

The script must verify existing-instance attachment, BOM snapshot ID/hash, resource model attachment, descending operation IDs, expected scene hashes, PNG signature/dimensions/hash, ArtifactRefs and Craft association readback. It must stop on the first unexpected identity/version change.

```powershell
$result = Invoke-RestMethod -Headers $headers -Uri "$Ai00Base/api/simulation/capture-runs/$CaptureRunId"
if (($result.data.steps.operation_id -join ',') -ne 'op-30,op-20,op-10') { throw 'capture_order_mismatch' }
if ($result.data.steps.Where({ $_.status -ne 'attached' }).Count -ne 0) { throw 'capture_attach_incomplete' }
```

- [ ] **Step 5: Run the real pilot matrix**

On the designated workstation run unlocked, locked, display-off, and RDP-disconnected cases while preventing sleep only during the job. Also test network loss, Service restart, SessionHost restart and VisMockup crash. Record raw result IDs, Connector/Adapter/VisMockup versions, code revision and hashes.

- [ ] **Step 6: Evaluate governance without conflating evidence states**

Run the repository Catalog/doc/acceptance commands from Plan A again at the exact Connector commit. Submit real pilot evidence to the controlled evidence service. Only the trusted release workflow may derive `machine_passed`, `human_approved`, and `runtime_verified`.

- [ ] **Step 7: Commit test/runbook sources, not fabricated runtime results**

```bash
git add local-runtime/tests/Ai00.Connector.Tests/ServerContractTests.cs local-runtime/tests/pilot docs/runbooks/ai00-connector-vismockup-pilot.md
git commit -m "test(connector): add VisMockup pilot acceptance harness"
```

### Task 11: Deprecate Direct VisMockup Capability Exposure

**Files:**
- Modify: `plugins/device/device_backend/capabilities/runtime.py`
- Modify: `plugins/device/device_backend/capabilities/provider.py`
- Modify: `docs/migrations/capability-v1-retirement.md`
- Create: `backend/tests/test_vismockup_capability_deprecation.py`
- Modify: generated files under `docs/capabilities/` and `docs/governance/` using repository scripts only.

**Interfaces:**
- Produces: lifecycle/deprecation metadata and migration guidance from direct `vismockup.*@1` calls to `simulation.environment.*@1` and `simulation.capture_run.*@1`.
- Consumes: successful Task 10 fake integration; real pilot evidence remains an independent release input.

- [ ] **Step 1: Write failing exposure tests**

```python
def test_direct_vismockup_capabilities_are_not_new_agent_or_mcp_surfaces(catalog):
    for capability_id in DIRECT_VISMOCKUP_IDS:
        descriptor = catalog.resolve(capability_id, 1)
        assert descriptor.lifecycle_status == "deprecated"
        assert descriptor.exposure.agent is False
        assert descriptor.exposure.mcp is False

def test_deprecation_names_governed_replacement(catalog):
    capture = catalog.resolve("vismockup.capture", 1)
    assert "simulation.capture_run.start" in capture.deprecation_message
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest backend/tests/test_vismockup_capability_deprecation.py -q`

Expected: existing descriptors are stable and broadly exposed.

- [ ] **Step 3: Add an explicit compatibility window**

Mark direct `vismockup.*@1` deprecated, remove agent/plugin/MCP exposure for new calls, retain the minimum internal/local-runtime compatibility path until the published sunset date, and document replacements per operation. Do not delete Device command transport or rewrite historical operations.

```python
if governed.id in DEPRECATED_VISMOCKUP_CAPABILITIES:
    updates.update({
        "lifecycle_status": LifecycleStatus.DEPRECATED,
        "deprecation_message": VISMOCKUP_REPLACEMENTS[governed.id],
        "exposure": ExposurePolicy(local_runtime=True),
    })
```

- [ ] **Step 4: Regenerate and validate the Catalog**

Run: `python backend/scripts/build_capability_catalog.py`

Run: `python backend/scripts/generate_capability_docs.py`

Run: `python backend/scripts/build_user_function_registry.py --strict`

Run: `python -m pytest backend/tests/test_vismockup_capability_deprecation.py backend/tests/test_capability_catalog_release.py backend/tests/test_user_function_registry.py -q`

Expected: generated projections match the deprecated lifecycle and all tests pass.

- [ ] **Step 5: Commit**

```bash
git add plugins/device/device_backend/capabilities/runtime.py plugins/device/device_backend/capabilities/provider.py docs/migrations/capability-v1-retirement.md docs/capabilities docs/governance backend/tests/test_vismockup_capability_deprecation.py
git commit -m "deprecate(device): route VisMockup use through simulation workflows"
```

## Plan B Completion Gate

The phase-one product is complete only when the signed MSI installs on the pilot workstation, the bound user can pair one Connector, the server dispatches a contract-matched plan, the existing VisMockup document is materialized, internal captures complete while Windows is locked and awake, every artifact is associated with the correct Craft operation, failure cases reconcile, and the trusted governance workflow records the three status dimensions independently.
