# Teamcenter Search and VisMockup Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add retained local Teamcenter login, project selection, deterministic fuzzy search, revision-rule selection, and explicit online open/insert actions for VisMockup.

**Architecture:** Electron sends credentials only through the authenticated local control pipe; Connector retains them in memory and exposes closed status/logout commands. Teamcenter read operations remain signed Connector plans. Online Visualization material is created as a current-user-only temporary VVI and consumed inside the same Connector process by the existing VisMockup COM adapter.

**Tech Stack:** C#/.NET 8, Java 11 Nashorn Teamcenter SOA, Python capability registry, Electron/Node.js, browser JavaScript, VisAutomation COM.

**Spec:** `docs/superpowers/specs/2026-09-16-teamcenter-search-vismockup-actions-design.md`

## Global Constraints

- Passwords remain only in Connector memory and are cleared on logout, failed-session invalidation, and disposal.
- Search supports exact, prefix, and contains matching only; typo correction and semantic search are forbidden.
- Project input `P` resolves to Item ID `P-ENG0001` and Revision ID `00;1`.
- `Latest Working` is the preferred default revision rule; configuration date remains user-selectable.
- Selecting a source never opens VisMockup automatically.
- VVI content, SessionID, and CredToken never cross into web, execution-plan output, diagnostics, or logs.
- Generated capability artifacts are rebuilt by repository scripts, not hand-edited.
- `machine_passed`, `human_approved`, and `runtime_verified` remain independent.

---

### Task 1: Teamcenter local login lifecycle

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.AppHost/TeamcenterControlPipeHost.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterReadOnlyRuntime.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/TeamcenterControlProtocolTests.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/TeamcenterReadOnlyRuntimeTests.cs`
- Modify in frontend worktree: `packages/core/electron/connector_host_manager.js`
- Modify in frontend worktree: `packages/core/electron/connector_host_teamcenter.test.js`
- Modify in frontend worktree: `packages/core/electron/main.js`
- Modify in frontend worktree: `packages/core/electron/preload.js`

**Interfaces:**
- Produces: `TeamcenterReadOnlyRuntime.GetSessionStatus()` returning state plus masked username.
- Produces: `TeamcenterReadOnlyRuntime.LogoutAsync()`.
- Produces to renderer: `teamcenterGetSession()` and `teamcenterLogout()`.

- [ ] **Step 1: Write failing protocol and runtime tests**

Add tests proving login/status/logout messages are closed, status never includes a password, logout clears credentials, and disposal leaves no reusable session.

- [ ] **Step 2: Run tests and verify RED**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "TeamcenterControlProtocolTests|TeamcenterReadOnlyRuntimeTests"`

Expected: failures because status/logout commands and runtime methods do not exist.

- [ ] **Step 3: Implement the minimal closed control protocol**

Use a discriminated request with exact field sets:

```csharp
public sealed record TeamcenterStatusCommand(string RequestId);
public sealed record TeamcenterLogoutCommand(string RequestId);
public sealed record TeamcenterSessionStatus(string State, string MaskedUsername);
```

Keep login rate limiting. Return only `type`, `request_id`, `state`, `code`, and `masked_username` where applicable.

- [ ] **Step 4: Add Electron IPC with validation**

Expose only parameterless status/logout calls and validate exact response fields before resolving renderer promises.

- [ ] **Step 5: Run focused backend and Electron tests and verify GREEN**

Run:

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "TeamcenterControlProtocolTests|TeamcenterReadOnlyRuntimeTests"
node --test packages/core/electron/connector_host_teamcenter.test.js
```

- [ ] **Step 6: Commit each repository**

Backend commit: `feat(teamcenter): add local login lifecycle`

Frontend commit: `feat(teamcenter): expose local login lifecycle`

### Task 2: Revision rules and deterministic search

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterReadOnlyRuntime.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/TeamcenterReadOnlyRuntimeTests.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/TeamcenterWorkerContractTests.cs`
- Create if absent: `docs/contracts/teamcenter.product.search@2.json`
- Create: `docs/contracts/teamcenter.revision_rule.search@1.json`

**Interfaces:**
- Produces adapter operation `teamcenter.revision_rule.search@1` with `{ rules: string[] }`.
- Produces adapter operation `teamcenter.product.search@2` consuming `{endpoint_id, query, revision_id, revision_rule, configuration_date, limit}`.

- [ ] **Step 1: Write failing tests for rule ordering and match ranking**

Tests assert `Latest Working` is first when present and search ranking is exact ID, ID prefix, ID contains, then name; revision is exact; results are capped at 20.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "Teamcenter"`

Expected: missing operations and v2 payload support.

- [ ] **Step 3: Add worker commands and closed payload validation**

Extend the whitelist to `revision_rules` and implement saved-query-backed candidate lookup. Normalize only surrounding whitespace and case for ranking; never edit distance, tokenize semantically, or expand synonyms.

- [ ] **Step 4: Add C# DTOs and adapter manifest entries**

Use explicit records:

```csharp
public sealed record TeamcenterRevisionRulesResult(string[] Rules);
public sealed record TeamcenterSearchQuery(string Query, string RevisionId, int Limit);
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "Teamcenter"`

- [ ] **Step 6: Commit**

Commit: `feat(teamcenter): add revision rules and fuzzy item search`

### Task 3: Secure online VVI open and insert

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/teamcenter_visualization_launch.js`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterReadOnlyRuntime.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/VisMockupDocumentLifecycleTests.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/TeamcenterReadOnlyRuntimeTests.cs`
- Create: `docs/contracts/teamcenter.visualization.insert@1.json`

**Interfaces:**
- `ConsumeVisualizationAsync(selector, expectedVisdocUid, credentials, consumer, ct)` holds the Java SOA session open while `consumer(path)` runs, then acknowledges consumption and completes cleanup/logout.
- `OpenOnlineAsync(material)` calls `Documents.Open`.
- `InsertOnlineAsync(material)` calls `ActiveDocument.InsertDocument`.

- [ ] **Step 1: Write failing lifecycle tests**

Tests prove open creates a new document, insert retains the same active document, insert without an active document returns `vismockup_active_document_required`, and temporary material is deleted on success and failure.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "VisMockupDocumentLifecycleTests|TeamcenterReadOnlyRuntimeTests"`

- [ ] **Step 3: Refactor launch worker to create restricted material**

Create the VVI under the Connector-owned state root. Emit one bounded ready frame only:

```json
{"material_path":"<local path>","source_identity_hash":"sha256:<64 hex>","expected_visdoc_uid":"<uid>"}
```

Never serialize the VVI body. Apply the current-user-only ACL before writing content.

Keep the Java SOA session alive while waiting for one bounded stdin acknowledgement. C# calls the supplied COM consumer before writing `consumed`; on error it writes `failed`. Both processes enforce a timeout and delete the material in `finally`.

- [ ] **Step 4: Add open/insert adapter operations with unconditional cleanup**

Wrap COM consumption in `try/finally` and securely delete the material. Preserve existing local artifact open/insert operations.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "VisMockupDocumentLifecycleTests|TeamcenterReadOnlyRuntimeTests"`

- [ ] **Step 6: Commit**

Commit: `feat(teamcenter): open or insert online visualization`

### Task 4: Governed capability contracts

**Files:**
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `backend/tests/test_connector_runtime_control_plane.py`
- Modify relevant governance tests under: `backend/tests/acceptance/`

**Interfaces:**
- Produces `simulation.teamcenter.revision_rule.search.request@1`.
- Upgrades search request to use `teamcenter.product.search@2` while retaining the old atomic v1 advertisement.
- Produces `simulation.teamcenter.visualization.insert.request@1` with user confirmation.

- [ ] **Step 1: Write failing registry and execution-plan tests**

Assert exact schemas, operation ids and hashes, READ risk for rules/search, WRITE plus user confirmation for open/insert, and renderer allowlisting.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest backend/tests/test_connector_runtime_control_plane.py -q`

- [ ] **Step 3: Register the minimal contracts and operation mappings**

Do not add generic Teamcenter invocation. Resource selectors remain bound to the current Connector and online source identity.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest backend/tests/test_connector_runtime_control_plane.py -q`

- [ ] **Step 5: Commit**

Commit: `feat(simulation): govern Teamcenter search and insert actions`

### Task 5: Frontend domain helpers and login dialog

**Files in frontend worktree:**
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_online_source.js`
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_online_source.test.js`
- Create: `packages/sim-plugin/web/cad_sim/teamcenter_session.js`
- Create: `packages/sim-plugin/web/cad_sim/teamcenter_session.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/index.html`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`

**Interfaces:**
- `projectSelector(projectNumber, revisionRule, configurationDate)` returns the fixed Item/Revision query.
- `search(requestConnector, query)` invokes the governed v2 search.
- `TeamcenterSessionController` owns status, login modal, and logout.

- [ ] **Step 1: Write failing helper and session tests**

Assert `W10 -> W10-ENG0001 / 00;1`, reject already suffixed input, exact placeholder copy, status restoration, logout, and password field clearing.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
node packages/sim-plugin/web/cad_sim/teamcenter_online_source.test.js
node --test packages/sim-plugin/web/cad_sim/teamcenter_session.test.js
```

- [ ] **Step 3: Implement pure helpers and the independent login modal**

Keep password values local to the modal and set them to an empty string before removal on every close path.

- [ ] **Step 4: Run tests and verify GREEN**

Run the same two commands and require zero failures.

- [ ] **Step 5: Commit**

Commit: `feat(teamcenter): add retained login and selection helpers`

### Task 6: Project/search selector and explicit VisMockup actions

**Files in frontend worktree:**
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify: `packages/sim-plugin/web/cad_sim/index.html`
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_online_source.js`
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_online_source.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_entry_assets.test.js`
- Create: `packages/sim-plugin/web/cad_sim/teamcenter_source_dialog.test.js`

**Interfaces:**
- `openOnline(requestConnector, document)` queues the existing launch request.
- `insertOnline(requestConnector, document)` queues the new insert request.
- `_addTeamcenterSource()` observes and persists only; it never calls either action.

- [ ] **Step 1: Write failing DOM and workflow tests**

Tests assert two tabs, revision-rule select, editable date, search result selection, no automatic launch after persistence, and both model-row buttons invoking the correct capability.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --test packages/sim-plugin/web/cad_sim/teamcenter_source_dialog.test.js packages/sim-plugin/web/cad_sim/teamcenter_entry_assets.test.js`

- [ ] **Step 3: Implement the minimal dialog and buttons**

Use DOM `textContent` for server-returned names. Disable insert while no active VisMockup document is known, but recheck in Connector as the authority.

- [ ] **Step 4: Run focused and existing CAD simulation tests and verify GREEN**

Run: `node --test packages/sim-plugin/web/cad_sim/*.test.js`

- [ ] **Step 5: Commit**

Commit: `feat(teamcenter): separate selection from VisMockup actions`

### Task 7: Generated governance artifacts and full verification

**Files:**
- Generated by scripts: `docs/capabilities/catalog.v2.json`
- Generated by scripts: `docs/capabilities/openapi-fragment.v2.json`
- Generated by scripts: `docs/capabilities/mcp-tools.v2.json`
- Generated by scripts: `docs/capabilities/agent-tools.v2.json`
- Generated by scripts: `docs/governance/capability-catalog-release.json`
- Generated by scripts: affected `docs/capabilities/simulation/*.md`

**Interfaces:**
- Produces release-ready governance evidence without asserting real-runtime verification.

- [ ] **Step 1: Run catalog generators**

Run:

```powershell
python backend/scripts/build_capability_catalog.py
python backend/scripts/generate_capability_docs.py
```

- [ ] **Step 2: Run generator checks and acceptance**

Run:

```powershell
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/run_capability_v2_acceptance.py
```

- [ ] **Step 3: Run full relevant backend and frontend suites**

Run:

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj
python -m pytest backend/tests/test_connector_runtime_control_plane.py backend/tests/acceptance -q
node --test packages/core/electron/connector_host_teamcenter.test.js packages/sim-plugin/web/cad_sim/*.test.js
npm run build:web
```

- [ ] **Step 4: Inspect diffs and security invariants**

Search changed files for credential values, VVI body logging, generic SOA invocation, hand-edited generated data, and accidental changes outside the two feature worktrees.

- [ ] **Step 5: Commit generated evidence in backend**

Commit: `docs(capabilities): publish Teamcenter search action contracts`

- [ ] **Step 6: Record real-runtime status accurately**

If live Teamcenter/VisMockup verification was not run, record `runtime_verified=false` and list the exact manual scenarios still pending. Never infer runtime readiness from unit tests.
