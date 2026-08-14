# Web Compatibility Write Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every authenticated first-party legacy web route backed by Capability V2 can complete governed writes without individual page-specific `confirm → invoke` rewrites or repeated `422 confirmation_required` failures.

**Architecture:** Add one server-side trusted-web compatibility bridge that invokes the Gateway, detects only `confirmation_required`, obtains a short-lived approval for the exact server-derived envelope, supplies a stable request-scoped idempotency key, and retries once. Project, Factory, Ontology, and Simulation legacy adapters use this bridge; generic Capability, agent, MCP, and plugin Mount APIs keep their explicit approval protocols unchanged.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, pytest, Capability V2 Gateway, Vanilla JavaScript deployment artifacts.

## Global Constraints

- Do not add a worktree or use subagents.
- Do not push or merge.
- Do not weaken authentication, role checks, tenant derivation, provider isolation, or explicit approval on generic Capability, agent, MCP, or plugin Mount APIs.
- Retry only `confirmation_required`, at most once, using the exact server-derived payload and identity.
- Preserve existing uncommitted deployment files and review artifacts.
- Test first, observe the intended failure, then implement.

---

### Task 1: Trusted web compatibility confirmation bridge

**Files:**
- Create: `backend/capability_v2/web_compatibility.py`
- Create: `backend/tests/test_web_compatibility_confirmation.py`

**Interfaces:**
- Consumes: `CapabilityGatewayService.invoke(envelope)`, `CapabilityGatewayService.request_approval(envelope)`, `InvocationEnvelope.model_copy`.
- Produces: `invoke_trusted_web_compatibility(gateway, envelope) -> GatewayResult`.

- [ ] **Step 1: Write the failing behavioral tests**

Create a recording Gateway that returns `confirmation_required` on the first write invocation, issues `approval-1`, and succeeds only when the retry carries that token. Assert two invocations, one approval request, identical identity/payload, and `idempotency_key == request_id` when the legacy caller omitted one. Add read and non-confirmation-error cases proving there is no retry.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest backend/tests/test_web_compatibility_confirmation.py -q`

Expected: collection/import failure because `invoke_trusted_web_compatibility` does not exist.

- [ ] **Step 3: Implement the minimal bridge**

Implement the following behavior without catching unrelated errors:

```python
async def invoke_trusted_web_compatibility(gateway, envelope):
    result = await gateway.invoke(envelope)
    if result.ok or not result.error or result.error.code != "confirmation_required":
        return result
    challenge_envelope = envelope.model_copy(update={
        "idempotency_key": envelope.idempotency_key or envelope.request_id,
    })
    issued = await gateway.request_approval(challenge_envelope)
    return await gateway.invoke(challenge_envelope.model_copy(update={
        "approval_reference": issued.token,
    }))
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest backend/tests/test_web_compatibility_confirmation.py -q`

Expected: all tests pass.

### Task 2: Route every current web compatibility adapter through the bridge

**Files:**
- Modify: `plugins/project_management/project_management_backend/api/compatibility.py`
- Modify: `plugins/factory/factory_backend/api/compatibility.py`
- Modify: `plugins/craft/craft_backend/routers/ontology.py`
- Modify: `plugins/simulation/simulation_backend/routers/environments.py`
- Test: `plugins/project_management/tests/test_compatibility_gateway.py`
- Test: `plugins/factory/tests/test_factory_provider.py`
- Test: `backend/tests/test_ontology_capability_adapter.py`
- Test: `backend/tests/test_simulation_environment_capability_routes.py`

**Interfaces:**
- Consumes: `invoke_trusted_web_compatibility(gateway, envelope)` from Task 1.
- Produces: unchanged HTTP request/response shapes for all legacy adapters.

- [ ] **Step 1: Add route-level failing tests**

For one write route in each adapter family, use a confirmation-aware recording Gateway and issue the legacy HTTP request without an approval header/body. Assert the route succeeds, the exact payload is preserved, and the Gateway receives a single approved retry. Existing read tests must continue to assert one invocation and zero approval requests.

- [ ] **Step 2: Run route-focused tests and verify RED**

Run:

```powershell
python -m pytest plugins/project_management/tests/test_compatibility_gateway.py plugins/factory/tests/test_factory_provider.py backend/tests/test_ontology_capability_adapter.py backend/tests/test_simulation_environment_capability_routes.py -q
```

Expected: new write tests fail with the unapproved result.

- [ ] **Step 3: Replace direct compatibility `gateway.invoke` calls**

Project and Factory `invoke_compatibility` delegate to the shared bridge. Ontology and Simulation invoke the shared bridge directly. Do not alter generic Gateway routers.

- [ ] **Step 4: Run route-focused tests and verify GREEN**

Run the Task 2 command; expect all tests to pass.

### Task 3: Regression gate and whole-system verification

**Files:**
- Modify generated Capability artifacts only if freeze/check scripts report drift.
- Deploy: `dist/` only through the existing build/sync process if source artifacts changed.

**Interfaces:**
- Consumes: completed Tasks 1–2.
- Produces: evidence that all current legacy Capability V2 web adapter families use the shared governed bridge.

- [ ] **Step 1: Run the adapter inventory check**

Search all backend/plugin routers for direct `gateway.invoke` calls. Manually classify generic Capability, agent, MCP, plugin Mount, worker, and web compatibility callers. The only web compatibility direct calls after Task 2 must be inside the shared bridge.

- [ ] **Step 2: Run focused and full backend tests**

Run: `python -m pytest -q`

Expected: zero failures.

- [ ] **Step 3: Run Capability generation and strict offline acceptance checks**

Run catalog/docs/acceptance manifest checks and `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`. Expect zero failed and zero skipped cases.

- [ ] **Step 4: Restart only `AI00Backend-CapabilityV2` and execute live compatibility smoke tests**

Using `http://pc-pc2l7vve:8094`, call representative legacy writes without confirmation tokens for Project and Factory, plus safe route tests for Ontology/Simulation where fixtures exist. Verify create/update/delete or archive, then clean exact IDs and confirm zero residuals.

- [ ] **Step 5: Commit intentionally without pushing**

Commit backend source/tests and any required frozen artifacts. Preserve unrelated modified/untracked files.

## Self-Review

- Spec coverage: central bridge, all four current web adapter families, no generic API weakening, idempotency, bounded retry, route and live tests are covered.
- Placeholder scan: no deferred implementation placeholders remain.
- Type consistency: all tasks use `invoke_trusted_web_compatibility(gateway, envelope)` and `InvocationEnvelope.model_copy` consistently.
