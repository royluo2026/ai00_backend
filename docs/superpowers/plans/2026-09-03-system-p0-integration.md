# System P0 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the reviewed Agent and Simulation code into the authoritative local `test` branches and add a two-layer P0 verification path for runtime recovery and functional smoke testing.

**Architecture:** Keep backend `test@6144cc14+` as the already-integrated Agent/Simulation source, synchronize only the final reviewed Simulation web assets into the authoritative frontend `test@7613b66`, and add one live-database integration module that composes the production Agent lifecycle and Simulation projection worker. Keep Orchestration, Ontology, Catalog, freeze, acceptance, approval, and release evidence outside this integration.

**Tech Stack:** Python 3.12, pytest, FastAPI TestClient, PyMySQL/OceanBase-compatible SQL, Node.js, Vite, .NET 8 xUnit, Git worktrees.

**Spec:** `docs/superpowers/specs/2026-09-03-system-p0-integration-design.md`

## Global Constraints

- Backend authority is `E:/Projects/ai00_v3/.worktrees/capability-v2-implementation` branch `test`.
- Frontend authority is `E:/Projects/ai00/workmanship-web` branch `test`.
- Do not merge either Orchestration branch; its Agent migration IDs conflict and Capability Gate 0 is incomplete.
- Do not merge Ontology work.
- Do not refresh Catalog, provider freeze, generated Capability docs, acceptance manifests, Snapshots, approvals, or signed release evidence.
- Preserve untracked files and never force-remove a dirty worktree.
- A P0 must prevent a reviewed functional flow, corrupt/duplicate data, break identity/authentication, leak a runtime resource indefinitely, or block an existing database upgrade.
- Report `machine_passed`, `human_approved`, and `runtime_verified` separately; AI remains advisory.

---

### Task 1: Synchronize the reviewed Simulation frontend boundary

**Files:**
- Create: `E:/Projects/ai00/workmanship-web/scripts/test_simulation_p0_boundary.js`
- Modify: `E:/Projects/ai00/workmanship-web/package.json`
- Modify: `E:/Projects/ai00/workmanship-web/packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `E:/Projects/ai00/workmanship-web/packages/sim-plugin/web/cad_sim/index.html`
- Create/Modify: `E:/Projects/ai00/workmanship-web/web/simulation_connector/pair.html`
- Create/Modify: `E:/Projects/ai00/workmanship-web/web/simulation_connector/pair.js`
- Create/Modify: `E:/Projects/ai00/workmanship-web/web/simulation_connector/pair.css`

**Interfaces:**
- Consumes: reviewed packaged files under backend `dist/packages/sim-plugin/web/cad_sim/` and `dist/web/simulation_connector/` at backend `test` tip.
- Produces: authoritative frontend source with no active production localhost Bridge call and a `test:simulation-p0-boundary` command.

- [ ] **Step 1: Create an isolated frontend worktree from authoritative `test`**

Run:

```powershell
git -C E:/Projects/ai00/workmanship-web check-ignore .worktrees
git -C E:/Projects/ai00/workmanship-web worktree add E:/Projects/ai00/workmanship-web/.worktrees/system-p0-integration-web -b codex/system-p0-integration-web test
```

Expected: the worktree is created from `7613b66` or the then-current local `test`, with no tracked changes.

- [ ] **Step 2: Write the failing frontend boundary test**

Create a standard-library Node test that reads `cad_sim.js` and asserts:

```javascript
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'packages', 'sim-plugin', 'web', 'cad_sim', 'cad_sim.js'),
  'utf8',
);
assert(!source.includes('http://127.0.0.1:'), 'production cad_sim must not call localhost Bridge');
assert(!source.includes('/bridge/'), 'production cad_sim must not expose Bridge routes');
assert(source.includes('_captureOpSequenceGoverned'), 'governed capture flow must remain wired');
assert(source.includes('_cadSimCapture'), 'cross-panel governed capture entry must remain wired');
console.log('simulation P0 boundary: PASS');
```

Add `"test:simulation-p0-boundary": "node scripts/test_simulation_p0_boundary.js"` and include it once in `npm test`/`test:all`/`test:integration` without adding a dependency.

- [ ] **Step 3: Run the test and verify RED**

Run:

```powershell
npm run test:simulation-p0-boundary
```

Expected: FAIL because the authoritative frontend still contains `127.0.0.1:7654` and `/bridge/` calls.

- [ ] **Step 4: Apply only the reviewed Simulation web delta**

Copy the reviewed backend packaged `cad_sim.js`, `index.html`, and `web/simulation_connector/pair.*` content into the matching frontend source files. Inspect `git diff` and reject any change outside the listed Simulation paths and `package.json`/the new test.

- [ ] **Step 5: Run focused frontend verification**

Run:

```powershell
npm run test:simulation-p0-boundary
node --check packages/sim-plugin/web/cad_sim/cad_sim.js
node --check web/simulation_connector/pair.js
npm test
npm run build:web
```

Expected: all commands exit `0`; the production build contains the same reviewed Simulation source hashes.

- [ ] **Step 6: Commit the frontend synchronization**

```powershell
git add package.json scripts/test_simulation_p0_boundary.js packages/sim-plugin/web/cad_sim web/simulation_connector
git commit -m "fix(simulation): align governed connector web runtime"
```

---

### Task 2: Add the cross-domain live recovery integration module

**Files:**
- Create: `backend/tests/integration/test_agent_simulation_runtime_recovery.py`
- Modify: `backend/tests/integration/conftest.py`

**Interfaces:**
- Consumes: `backend.main.app`, Agent `AgentCapabilityOutboxRepository`, production `agent.capability-outbox` lifecycle, `SimulationConnectorRepository`, `ConnectorProjectionWorker`, `GovernedSimulationRuntimeClient`, and existing live-DB opt-in variables.
- Produces: two `pytest.mark.integration` recovery tests gated by `AI00_ALLOW_LIVE_DB_TESTS=1`, `AI00_BASE_DB_URL`, `AI00_AGENT_DB_URL`, and `AI00_SIMULATION_TEST_DB_URL`.

- [ ] **Step 1: Create an isolated backend implementation worktree**

Run from outside the current backend worktree:

```powershell
git -C E:/Projects/ai00_v3/workmanship-backend worktree add E:/Projects/ai00_v3/.worktrees/system-p0-integration -b codex/system-p0-integration-backend test
```

Expected: the new worktree starts from the design commit and includes Agent/Simulation P0 code.

- [ ] **Step 2: Add live Agent and Simulation DB fixtures**

Extend `backend/tests/integration/conftest.py` with fixtures using the existing `_db_factory`:

```python
@pytest.fixture
def base_db():
    return _db_factory("AI00_BASE_DB_URL")

@pytest.fixture
def agent_db():
    return _db_factory("AI00_AGENT_DB_URL")

@pytest.fixture
def simulation_db():
    return _db_factory("AI00_SIMULATION_TEST_DB_URL")
```

- [ ] **Step 3: Write the failing Agent lifespan recovery test**

The test must:

1. Insert uniquely named Base `outcome_unknown` and Agent `pending` outbox rows using the real schemas.
2. Start `TestClient(backend.main.app)` so the official Registry lifecycle starts.
3. Poll with a bounded deadline until the Agent row is `delivered` and Base outcome is `completed`.
4. Assert one Base outcome row and one audit-outbox event for the operation.
5. Exit `TestClient`, assert lifecycle health is stopped, and delete only rows containing the generated UUID.

Run:

```powershell
$env:AI00_ALLOW_LIVE_DB_TESTS='1'
python -m pytest backend/tests/integration/test_agent_simulation_runtime_recovery.py::test_agent_lifespan_reconciles_committed_outbox_once -q
```

Expected before completing fixtures/composition: FAIL at the first missing integration helper or lifecycle assertion, not skip.

- [ ] **Step 4: Implement the minimum Agent test setup and verify GREEN**

Reuse production migrations and repositories; do not create a second dispatcher implementation. Poll for at most 10 seconds with a 100 ms interval. Cleanup uses exact generated IDs in `finally`.

Run the same command. Expected: `1 passed` against the configured disposable databases.

- [ ] **Step 5: Write the failing Simulation projection recovery test**

The test must:

1. Insert one uniquely named completed Connector plan plus its pending projection intent in the real Simulation database.
2. Compose `ConnectorProjectionWorker(SimulationConnectorRepository(), GovernedSimulationRuntimeClient(get_default_gateway()), ...)` exactly as the CLI does.
3. Force the first target call to fail through a test-owned Gateway provider/adapter boundary, assert retry state, expire/reclaim the lease, then allow the target call.
4. Run the worker again and assert outbox completion and exactly one projected business result.
5. Replay once and assert no duplicate projection.

Run:

```powershell
python -m pytest backend/tests/integration/test_agent_simulation_runtime_recovery.py::test_simulation_projection_recovers_without_duplicate_effect -q
```

Expected before the test setup is complete: FAIL at the recovery/duplicate assertion, not skip.

- [ ] **Step 6: Implement the minimum Simulation setup and verify GREEN**

Reuse the production `ConnectorProjectionWorker`, `GovernedSimulationRuntimeClient`, and existing test adapter factory. Do not copy claim/retry logic into the test.

Run:

```powershell
python -m pytest backend/tests/integration/test_agent_simulation_runtime_recovery.py -q
```

Expected: `2 passed` when all live DB variables are configured; otherwise each missing external dependency is reported as `skipped` with its exact variable name.

- [ ] **Step 7: Commit the backend integration module**

```powershell
git add backend/tests/integration/conftest.py backend/tests/integration/test_agent_simulation_runtime_recovery.py
git commit -m "test: cover agent and simulation p0 recovery"
```

---

### Task 3: Run the deterministic P0 gate and fix only confirmed P0 regressions

**Files:**
- Modify only when a test demonstrates a P0: the owner-domain implementation and its failing regression test.
- Do not modify generated governance artifacts.

**Interfaces:**
- Consumes: Tasks 1–2 commits.
- Produces: a green deterministic gate or an exact P0 failure report.

- [ ] **Step 1: Run backend focused P0 tests**

```powershell
python -m pytest backend/tests/test_agent_interaction_chat_change_boundary.py backend/tests/test_agent_runtime_config_capability_boundary.py backend/tests/test_agent_outbox_migration_upgrade.py backend/tests/test_connector_runtime_control_plane.py backend/tests/test_simulation_connector_pairing_capabilities.py backend/tests/test_simulation_connector_projection_worker.py backend/tests/test_domain_migration_runner.py -q
python backend/scripts/run_domain_migrations.py --domain agent --check
python backend/scripts/run_domain_migrations.py --domain simulation --check
python backend/scripts/check_domain_dependencies.py
```

Expected: no assertion failures; environment ACL failures are reported separately and retried once with a writable explicit pytest basetemp.

- [ ] **Step 2: Run .NET Connector verification from source**

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore
```

Expected: all Connector tests pass from the current source tree.

- [ ] **Step 3: Run frontend focused and full tests**

```powershell
npm run test:simulation-p0-boundary
npm run test:agent-canvas-capabilities
npm test
npm run build:web
```

Expected: all commands exit `0`.

- [ ] **Step 4: Classify failures before editing**

For each failure, record whether it is a P0 by the design rule. Fix only confirmed P0s using a new failing regression assertion first. Report stale Catalog/evidence, missing approval, missing live DB URL, and unavailable VisMockup as separate non-code states.

- [ ] **Step 5: Commit any demonstrated P0 fix**

Stage only the failing test and the owner-domain implementation. Use `fix(agent): ...`, `fix(simulation): ...`, or `fix(base): ...` according to ownership.

---

### Task 4: Merge locally and verify the merged tips

**Files:**
- No new files unless conflict resolution is required within the approved paths.

**Interfaces:**
- Consumes: `codex/system-p0-integration-backend` and `codex/system-p0-integration-web`.
- Produces: local backend and frontend `test` tips with verified P0 integration commits.

- [ ] **Step 1: Verify branch scope before merging**

```powershell
git diff --name-status test...codex/system-p0-integration-backend
git diff --name-status test...codex/system-p0-integration-web
```

Expected: backend contains only the design/plan and integration test work; frontend contains only Simulation source, its test, and package/build output changes. Orchestration, Ontology, Catalog, freeze, and acceptance paths are absent.

- [ ] **Step 2: Merge backend locally**

Fast-forward or merge `codex/system-p0-integration-backend` into backend `test`, then rerun the backend focused P0 tests and live integration module.

- [ ] **Step 3: Merge frontend locally**

Fast-forward or merge `codex/system-p0-integration-web` into authoritative frontend `test`, rebuild `dist-production`, and rerun `npm test` plus `test:simulation-p0-boundary`.

- [ ] **Step 4: Preserve or clean worktrees safely**

Remove only clean worktrees whose commits are ancestors of the merged `test`. If a worktree contains uncommitted files, list it and preserve it. Keep all Orchestration and Ontology worktrees.

---

### Task 5: Execute Layer 2 live functional smoke

**Files:**
- No tracked files unless a real P0 is reproduced and first captured by a failing test.

**Interfaces:**
- Consumes: merged backend/frontend `test`, disposable test databases, Connector pairing, and VisMockup.
- Produces: an advisory runtime report separating verified flows from environment blockers.

- [ ] **Step 1: Run environment preflight**

Verify without printing secrets:

- Backend, Base, Agent, and Simulation database URLs are present.
- Connector Gateway URL and signing key ID/secret are present.
- `C:/ProgramData/AI00/Connector/device.credential` and `operation.keys` exist after pairing.
- Connector, SessionHost, projection worker, and VisMockup processes can start.

- [ ] **Step 2: Run Agent functional smoke**

Use the existing local super-admin session without sending an external model message. Verify settings read/test response, assistant panel open, normal stream, cancellation, timeout, successful write, failed write rollback, final in-flight count zero, and Agent outbox delivery.

- [ ] **Step 3: Run Simulation functional smoke**

Complete browser pairing, start Connector/SessionHost/projection worker/VisMockup, invoke governed capture from the production page, and verify plan creation, lease, execution, outcome, projection, artifact, and UI completion.

- [ ] **Step 4: Inspect browser network and system state**

Assert the governed capture produces Capability Gateway calls and zero localhost Bridge calls. Confirm no pending/stuck outbox row remains for the generated request IDs.

- [ ] **Step 5: Report final states**

Report exact commands, passed/failed/skipped counts, generated request IDs, P0 findings, environment blockers, and:

```text
machine_passed=<true|false for scoped P0 gate>
human_approved=unverified
runtime_verified=<true|false|partial>
advisory=true
```
