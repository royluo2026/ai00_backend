# Agent Runtime Capability Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the final four Agent REST groups with bounded, tenant-safe runtime Capabilities and reduce the canonical structural remainder to zero.

**Architecture:** Reuse the existing canvas executor behind one Agent-owned production runtime adapter. Synchronous option/node-test operations stay bounded; start/resume use durable run state, idempotency, reconciliation, and lifecycle health.

**Tech Stack:** Python 3.12, asyncio, pytest, JavaScript, Node.js, Vite, Agent runtime, Capability Gateway V2.

**Spec:** `docs/superpowers/specs/2026-08-31-agent-runtime-capability-closure-design.md`

## Global Constraints

- No arbitrary source, import path, environment, credential, or unrestricted tool identifier crosses the contract.
- Every runtime call is actor/team scoped and bounded by graph, input, output, time, retry, and concurrency limits.
- Start/resume are confirmed idempotent writes with durable terminal or reconcilable outcomes.
- Runtime composition fails closed when the production adapter is absent.
- This plan reduces the canonical remainder from 4 groups / 5 occurrences to 0 / 0.

---

### Task 1: Define exact Agent runtime contracts and production port

**Files:**
- Modify: `plugins/agent/agent_backend/capabilities/contracts.py`
- Modify: `plugins/agent/agent_backend/capabilities/descriptors.py`
- Modify: `plugins/agent/agent_backend/capabilities/provider.py`
- Modify: `plugins/agent/agent_backend/application/service.py`
- Create: `plugins/agent/agent_backend/application/canvas_runtime.py`
- Create: `plugins/agent/tests/test_agent_canvas_runtime_contracts.py`

**Interfaces:**
- Produces: `AgentCanvasRuntime` with `test_node`, `resolve_options`, `start`, and `resume`; four exact capability contracts from the design spec.
- Consumes: existing `ai_assistant/canvas_executor.py` through finite typed arguments.

- [ ] **Step 1: Add failing contract and adapter-composition tests**

```python
class AgentCanvasRuntime(Protocol):
    async def test_node(self, request: NodeTestRequest, principal: RunPrincipal) -> NodeTestResult: ...
    async def resolve_options(self, request: CanvasOptionsRequest, principal: RunPrincipal) -> CanvasOptionsResult: ...
    async def start(self, request: CanvasStartRequest, principal: RunPrincipal) -> RuntimeDispatch: ...
    async def resume(self, request: CanvasResumeRequest, principal: RunPrincipal) -> RuntimeDispatch: ...
```

Test closed schemas, forbidden fields, bounds, mandatory principal, and fail-closed production composition.

- [ ] **Step 2: Run red**

Run: `python -m pytest plugins/agent/tests/test_agent_canvas_runtime_contracts.py -q`

- [ ] **Step 3: Implement the typed port and descriptor registration**

Reuse existing executor functions only through bounded request dataclasses. Do not add a second executor or generic dynamic dispatch registry.

- [ ] **Step 4: Run green and commit**

Commit: `feat: define governed Agent canvas runtime`

### Task 2: Implement bounded node test and option resolution

**Files:**
- Modify: `plugins/agent/agent_backend/application/canvas_runtime.py`
- Modify: `plugins/agent/agent_backend/application/service.py`
- Create: `plugins/agent/tests/test_agent_canvas_queries.py`

**Interfaces:**
- Produces: terminal closed outputs for `agent.workflow.node.test.execute@1` and `agent.canvas.options.resolve@1`.

- [ ] **Step 1: Add failing runtime tests**

Cover same-team success, cross-team denial, absent adapter, timeout, graph/input/output caps, deterministic option ordering, and canonical secret redaction in response/evidence.

- [ ] **Step 2: Run red**

Run: `python -m pytest plugins/agent/tests/test_agent_canvas_queries.py -q`

- [ ] **Step 3: Implement bounded wrappers**

Use `asyncio.wait_for` around the existing executor, freeze allowed node kinds, cap collections before and after runtime execution, and project only closed result fields.

- [ ] **Step 4: Run green and commit**

Commit: `feat: add bounded Agent canvas queries`

### Task 3: Implement durable canvas start and resume

**Files:**
- Modify: `plugins/agent/agent_backend/application/service.py`
- Modify: `plugins/agent/agent_backend/infrastructure/repository.py`
- Modify: `plugins/agent/agent_backend/capabilities/provider.py`
- Create: `backend/db/migrations/domains/agent/0002_canvas_execution_control.sql`
- Create: `plugins/agent/tests/test_agent_canvas_commands.py`

**Interfaces:**
- Produces: durable `agent.canvas.execution.start@1` and `agent.canvas.execution.resume@1` with opaque run/pause identities and reconcilable states.

- [ ] **Step 1: Add failing transaction/lifecycle tests**

Test one run per idempotency key, changed-payload conflict, cross-team token denial, single-use revision-bound resume, crash before/after dispatch, `outcome_unknown` reclaim with the same invocation, duplicate workers, and terminal replay.

- [ ] **Step 2: Run red**

Run: `python -m pytest plugins/agent/tests/test_agent_canvas_commands.py -q`

- [ ] **Step 3: Add minimal durable state and dispatcher**

Persist run principal, bounded request hash, target state, revision, lease, attempt count, and sanitized result. Atomically claim; restore the per-run principal; invoke the runtime; transactionally transition to terminal or reconcilable state.

- [ ] **Step 4: Register lifecycle health**

Reuse the existing Capability Registry lifecycle health/signal surface added for Integration; do not create an Agent-specific health framework.

- [ ] **Step 5: Run migration/runtime tests and commit**

Commit: `feat: add durable Agent canvas execution`

### Task 4: Migrate Agent Web consumers

**Files:**
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/packages/agent-plugin/web/flow_canvas/flow_editor.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/canvas/types/flow_type.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/packages/agent-plugin/web/wfc_window/wfc_window.js`
- Modify: matching `dist-production` outputs.
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_agent_canvas_capability_migrations.js`

**Interfaces:**
- Consumes: Tasks 1-3 exact capabilities.
- Produces: shipped Web flows with honest terminal/accepted/reconciling UI and no four REST routes.

- [ ] **Step 1: Add failing real-interaction tests**

Assert both node-test occurrences use the exact capability; options/start/resume use their exact IDs; start/resume supply confirmation/idempotency; resume preserves the opaque pause token; accepted/outcome_unknown do not render success.

- [ ] **Step 2: Run red and implement adapters**

Run: `node scripts/test_agent_canvas_capability_migrations.js`

Replace only the four request sites; reuse the shipped capability client and existing UI state model.

- [ ] **Step 3: Run green, build, and commit**

Run Node test, syntax checks, and `npm run build:web`.

Commit: `feat: migrate Agent canvas capabilities`

### Task 5: Freeze zero-remainder governance evidence

**Files:**
- Modify: `backend/scripts/build_craft_agent_project_structural_web_remediation.py`
- Modify: `backend/tests/test_craft_agent_project_structural_remediation_manifest.py`
- Modify: `backend/scripts/check_structural_remediation_plan.py`
- Regenerate: complete governance evidence chain and signed release inputs.
- Create: `.superpowers/sdd/2026-08-31-agent-runtime-capability-closure/final-report.md`

**Interfaces:**
- Consumes: committed Project, Craft, Agent backend/frontend heads.
- Produces: 14/14 groups and 17/17 occurrences resolved, canonical unresolved 0/0, strict acceptance report, and inputs for controlled runtime signing.

- [ ] **Step 1: Add failing zero-remainder assertions**

Assert exact identities, no 14 route literals, Project 3/3 capability-migrated, Craft 2/2 capability-migrated plus 5/5 decommissioned, Agent 4/5 capability-migrated, Base/Integration counts unchanged, and global unresolved 0/0.

- [ ] **Step 2: Freeze frontend and regenerate all evidence**

Generate deployable scan, wrapper contracts, route inventory, root-cause ledger, atomic contracts, all remediation manifests, structural plan, provider trust, Catalog, docs, user-function registry, and acceptance manifest in dependency order.

- [ ] **Step 3: Run final verification**

Run Project/Craft/Agent/Integration/Base suites, migration and dependency gates, Web behavior/build, all generator checks, and strict offline acceptance on a clean commit. Report `stable_functions` and reviewed-disposition debt separately; do not suppress them.

- [ ] **Step 4: Commit and request whole-program review**

Commit: `docs: close remaining structural capability governance`

