# Simulation Domain Environment and Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the AI00-side governed capabilities that compose a reproducible VisMockup environment, dispatch materialization and reverse-process capture runs, and attach each captured artifact to its owning Craft operation.

**Architecture:** The Simulation domain owns immutable environment manifests and run state. Craft, Knowledge, Digital Model, and Device remain authoritative for their own data and are consumed only through versioned capabilities or ports; a fake Connector completes the server-side vertical slice before the Windows implementation begins.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, MySQL/OceanBase-compatible SQL, Capability V2 Gateway, pytest, vanilla JavaScript for the existing web plugin.

**Spec:** `docs/superpowers/specs/2026-09-03-simulation-ai00-connector-governance-design.md`

## Global Constraints

- Preserve `simulation.environment.create@1`; add `simulation.environment.compose@1` instead of changing the stable `@1` contract.
- Cross-domain reads and writes go through governed capabilities/registered ports; Simulation must not query Craft, Knowledge, Digital Model, or Device tables.
- Environment manifests and execution plans use canonical UTF-8 JSON with sorted keys, no insignificant whitespace, and `sha256:`-prefixed lowercase hashes.
- Compose is all-or-nothing: unresolved or ambiguous product/resource bindings create no environment row.
- Capture order is `(sequence DESC, operation_id DESC)`; products are cumulative through the current sequence and resources are current-operation only.
- Every write has a Gateway idempotency key; every external outcome-unknown state is reconciled before retry.
- `machine_passed`, `human_approved`, and `runtime_verified` remain independent; fake Connector tests never set `runtime_verified=true`.
- The web browser never connects directly to AI00 Connector and never receives a device secret.

---

## File Map

- `backend/contracts/connector_execution_plan_v1.py`: cross-language immutable Connector plan and result models.
- `backend/tests/fixtures/connector_execution_plan_v1.json`: canonical cross-language test vector.
- `plugins/knowledge/knowledge_backend/capabilities/resource_model_mapping.py`: Knowledge-owned typed resource-code resolver.
- `plugins/craft/craft_backend/capabilities/process_screenshot.py`: Craft-owned idempotent screenshot association.
- `plugins/device/device_backend/capabilities/connector_runtime.py`: Device-owned health/compatibility projection and plan queue boundary.
- `plugins/simulation/simulation_backend/domain/environment_manifest.py`: pure manifest construction and scene derivation.
- `plugins/simulation/simulation_backend/data/environment_repository.py`: Simulation-only persistence.
- `plugins/simulation/simulation_backend/capabilities/environment_composition.py`: compose and preflight handlers.
- `plugins/simulation/simulation_backend/capabilities/capture_runs.py`: materialize/capture/cancel/retry handlers.
- `plugins/simulation/simulation_backend/application/capture_worker.py`: durable cross-domain workflow and reconciliation.
- `dist/packages/sim-plugin/web/cad_sim/`: current browser UI for Connector selection, preflight, environment and capture progress.

### Task 1: Freeze Connector ExecutionPlan V1

**Files:**
- Create: `backend/contracts/connector_execution_plan_v1.py`
- Create: `backend/tests/fixtures/connector_execution_plan_v1.json`
- Create: `backend/tests/test_connector_execution_plan_v1.py`
- Modify: `backend/domain_ports/local_integration.py`
- Create: `docs/contracts/connector.execution-plan.v1.md`

**Interfaces:**
- Produces: `ConnectorExecutionPlanV1`, `ConnectorStepV1`, `ConnectorStepResultV1`, `ConnectorPlanOutcomeV1`, `canonical_hash(value) -> str`.
- Consumes: existing `FrozenModel`, `IDENTITY_PATTERN`, and local-operation signature helpers.

- [ ] **Step 1: Write failing canonical-contract tests**

```python
def test_plan_hash_matches_checked_in_vector():
    raw = json.loads(VECTOR.read_text(encoding="utf-8"))
    plan = ConnectorExecutionPlanV1.model_validate(raw["plan"])
    assert plan.plan_hash == raw["plan_hash"]

def test_plan_rejects_duplicate_step_ids():
    raw = valid_plan()
    raw["steps"].append(raw["steps"][0])
    with pytest.raises(ValidationError, match="duplicate_step_id"):
        ConnectorExecutionPlanV1.model_validate(raw)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest backend/tests/test_connector_execution_plan_v1.py -q`

Expected: collection fails because `backend.contracts.connector_execution_plan_v1` does not exist.

- [ ] **Step 3: Implement closed Pydantic models and canonical hashing**

```python
class ConnectorStepV1(FrozenModel):
    step_id: str = Field(pattern=IDENTITY_PATTERN)
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]+@1$")
    contract_hash: str = Field(pattern=HASH_PATTERN)
    depends_on: tuple[str, ...] = ()
    payload: Mapping[str, Any]
    payload_hash: str = Field(pattern=HASH_PATTERN)
    timeout_seconds: int = Field(ge=1, le=900)

class ConnectorExecutionPlanV1(FrozenModel):
    protocol: Literal["ai00.connector.execution-plan.v1"]
    plan_id: str
    tenant_id: str
    user_id: str
    device_id: str
    capability_version_gid: str
    business_definition_hash: str = Field(pattern=HASH_PATTERN)
    adapter_id: str
    adapter_major: Literal[1]
    steps: tuple[ConnectorStepV1, ...]
    issued_at: datetime
    expires_at: datetime
    plan_hash: str = Field(pattern=HASH_PATTERN)
```

Validators must reject duplicate steps, forward/missing dependencies, naive timestamps, expiry before issue, incorrect payload hashes, and an incorrect plan hash computed with `plan_hash` omitted.

- [ ] **Step 4: Add the exact JSON vector and Python/.NET-facing contract document**

The vector must contain one `vismockup.application.probe@1` step and its literal expected hashes. The document must freeze timestamp format, property ordering, UTF-8 encoding, number handling, hash prefix, status values, and stable errors.

```json
{
  "protocol": "ai00.connector.execution-plan.v1",
  "adapter_id": "ai00.vismockup",
  "adapter_major": 1,
  "steps": [{"step_id": "step-1", "operation_id": "vismockup.application.probe@1", "depends_on": []}]
}
```

- [ ] **Step 5: Run focused and existing protocol tests**

Run: `python -m pytest backend/tests/test_connector_execution_plan_v1.py backend/tests/test_local_operation_protocol_v2.py backend/tests/test_device_runtime_protocol.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/contracts/connector_execution_plan_v1.py backend/domain_ports/local_integration.py backend/tests/fixtures/connector_execution_plan_v1.json backend/tests/test_connector_execution_plan_v1.py docs/contracts/connector.execution-plan.v1.md
git commit -m "feat(connector): freeze execution plan v1 contract"
```

### Task 2: Add the Knowledge Resource-to-Model Resolver

**Files:**
- Create: `backend/db/migrations/domains/knowledge/0004_resource_model_mappings.sql`
- Create: `plugins/knowledge/knowledge_backend/capabilities/resource_model_mapping.py`
- Create: `backend/tests/test_knowledge_resource_model_mapping.py`
- Modify: `plugins/knowledge/knowledge_backend/capabilities/__init__.py`
- Modify: `backend/governance/domain_table_ownership.json`

**Interfaces:**
- Produces: `knowledge.resource_model_mapping.resolve@1` with input `{items: [{resource_type, code}], as_of?}` and output `{resolved, unresolved, ambiguous, mapping_snapshot_hash}`.
- Consumes: immutable Digital Model references shaped as `{model_id, version_id, snapshot_hash, artifact_ref}`.

- [ ] **Step 1: Write failing resolver tests**

```python
def test_resolve_returns_typed_version_pinned_models(provider, context):
    result = provider.resolve({"items": [{"resource_type": "tool", "code": "T-01"}]}, context)
    assert result.data["resolved"][0]["model_ref"]["version_id"] == "v3"
    assert result.data["unresolved"] == []

def test_resolve_reports_ambiguity_without_picking_a_model(provider, context):
    result = provider.resolve({"items": [{"resource_type": "fixture", "code": "F-01"}]}, context)
    assert result.data["resolved"] == []
    assert result.data["ambiguous"][0]["code"] == "F-01"
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest backend/tests/test_knowledge_resource_model_mapping.py -q`

Expected: import failure for `resource_model_mapping`.

- [ ] **Step 3: Add owned migration with one active mapping per typed code and version**

```sql
CREATE TABLE IF NOT EXISTS workmanship_know_resource_model_mappings (
  gid VARCHAR(64) PRIMARY KEY,
  resource_type VARCHAR(32) NOT NULL,
  normalized_code VARCHAR(255) NOT NULL,
  model_ref_json JSON NOT NULL,
  mapping_version BIGINT NOT NULL,
  valid_from DATETIME(6) NOT NULL,
  valid_to DATETIME(6) NULL,
  content_hash VARCHAR(71) NOT NULL,
  created_by_gid VARCHAR(64) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_know_resource_model_mapping (resource_type, normalized_code, mapping_version)
);
```

- [ ] **Step 4: Implement normalization, bounded batch resolution, schemas, descriptor and errors**

Normalize with Unicode NFKC, strip, and casefold; accept only `tool`, `equipment`, and `fixture`; cap input at 500 unique pairs. Return all candidates for ambiguity and never choose by recency.

Stable errors: `resource_type_invalid`, `mapping_batch_limit_exceeded`, `mapping_snapshot_changed`. The capability is read-only, strongly consistent, confidential, evidence-required, and exposed to worker/plugin/web through Gateway.

```python
def normalize_code(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()

def resolve(payload: dict, context: CapabilityContext) -> CapabilityOutput:
    keys = sorted({(item["resource_type"], normalize_code(item["code"])) for item in payload["items"]})
    if len(keys) > 500:
        raise CapabilityBusinessError("mapping_batch_limit_exceeded", "At most 500 unique mappings are allowed")
    return CapabilityOutput(data=repository.resolve(keys, context))
```

- [ ] **Step 5: Prove no Craft table access and run migration/contract tests**

Run: `python -m pytest backend/tests/test_knowledge_resource_model_mapping.py backend/tests/test_knowledge_data_boundary.py backend/tests/test_domain_table_ownership.py backend/tests/test_versioned_migrations.py -q`

Expected: all tests pass and no SQL references `workmanship_craft_` or `workmanship_bop_` from the Knowledge provider.

- [ ] **Step 6: Commit**

```bash
git add backend/db/migrations/domains/knowledge/0004_resource_model_mappings.sql backend/governance/domain_table_ownership.json plugins/knowledge/knowledge_backend/capabilities backend/tests/test_knowledge_resource_model_mapping.py
git commit -m "feat(knowledge): resolve resource codes to model versions"
```

### Task 3: Complete Craft Execution and Screenshot Boundaries

**Files:**
- Modify: `plugins/craft/craft_backend/capabilities/bop_structure.py`
- Create: `plugins/craft/craft_backend/capabilities/process_screenshot.py`
- Create: `backend/db/migrations/domains/craft/0007_process_screenshots.sql`
- Create: `backend/tests/test_craft_process_screenshot_boundary.py`
- Modify: `plugins/craft/craft_backend/capabilities/__init__.py`
- Modify: `backend/governance/domain_table_ownership.json`

**Interfaces:**
- Produces: complete `craft.execution_plan.get@1` operation records and `craft.process_screenshot.attach@1`.
- Consumes: ArtifactRef generated by Capability Artifact Service; never accepts an arbitrary URL.

- [ ] **Step 1: Write failing execution-plan completeness and screenshot idempotency tests**

```python
def test_execution_plan_projects_products_and_typed_resource_codes(gateway):
    data = invoke(gateway, "craft.execution_plan.get", {"version_gid": "bop-1", "revision": 7})
    op = data["operations"][0]
    assert op["products"] == [{"product_ref": "P-01", "action": "install"}]
    assert op["resources"] == [{"resource_type": "tool", "code": "T-01"}]

def test_attach_same_run_operation_is_idempotent(gateway):
    first = attach(gateway, run_id="run-1", operation_id="op-1")
    second = attach(gateway, run_id="run-1", operation_id="op-1")
    assert second["screenshot_gid"] == first["screenshot_gid"]
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest backend/tests/test_craft_process_screenshot_boundary.py -q`

Expected: missing fields/capability failures.

- [ ] **Step 3: Add the screenshot history table**

```sql
CREATE TABLE IF NOT EXISTS workmanship_craft_process_screenshots (
  gid VARCHAR(64) PRIMARY KEY,
  bop_version_gid VARCHAR(64) NOT NULL,
  operation_id VARCHAR(255) NOT NULL,
  capture_run_id VARCHAR(64) NOT NULL,
  artifact_ref_json JSON NOT NULL,
  artifact_sha256 CHAR(64) NOT NULL,
  created_by_gid VARCHAR(64) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_craft_process_capture (bop_version_gid, operation_id, capture_run_id)
);
```

- [ ] **Step 4: Extend execution-plan projection and implement screenshot attach**

Execution-plan output must remain canonical `(sequence, operation_id)` ascending and include closed `products[]` and `resources[]`. Attach validates the BOP version and operation, validates the ArtifactRef through the artifact store, inserts history idempotently, and updates the existing `process_flow_pic` projection/current pointer in the same Craft transaction.

```python
def attach_process_screenshot(payload: dict, context: CapabilityContext) -> CapabilityOutput:
    artifact = artifact_port.require(payload["artifact_ref"], context)
    row = repository.attach_screenshot(
        payload["bop_version_gid"], payload["operation_id"], payload["capture_run_id"], artifact, context
    )
    return CapabilityOutput(data=row, evidence=(EvidenceRef(kind="craft.process_screenshot", reference=f"craft-screenshot:{row['gid']}", digest="sha256:" + artifact["sha256"]),))
```

- [ ] **Step 5: Run Craft ownership, permission, transaction and contract tests**

Run: `python -m pytest backend/tests/test_craft_process_screenshot_boundary.py backend/tests/test_craft_simulation_contract.py backend/tests/test_craft_write_capabilities.py backend/tests/test_domain_table_ownership.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add plugins/craft/craft_backend/capabilities backend/db/migrations/domains/craft/0007_process_screenshots.sql backend/governance/domain_table_ownership.json backend/tests/test_craft_process_screenshot_boundary.py
git commit -m "feat(craft): govern process screenshot association"
```

### Task 4: Upgrade the Device Control Plane for AI00 Connector

**Files:**
- Create: `plugins/device/device_backend/capabilities/connector_runtime.py`
- Modify: `plugins/device/device_backend/capabilities/contracts.py`
- Modify: `plugins/device/device_backend/capabilities/__init__.py`
- Modify: `plugins/device/device_backend/control_plane.py`
- Modify: `backend/routers/device_runtime.py`
- Create: `backend/tests/test_connector_runtime_control_plane.py`

**Interfaces:**
- Produces: `ConnectorHealth`, `AdapterAdvertisement`, `queue_connector_plan(plan, context) -> OperationRef`, and reconciliation by signed `ConnectorPlanOutcomeV1`.
- Consumes: `ConnectorExecutionPlanV1` from Task 1.

- [ ] **Step 1: Write failing single-user and compatibility tests**

```python
def test_heartbeat_records_adapter_contract_hashes(client, device_headers):
    response = client.post("/api/v1/connector/heartbeat", headers=device_headers, json=healthy_heartbeat())
    assert response.status_code == 200
    assert get_device()["adapters"][0]["operations"][0]["contract_hash"].startswith("sha256:")

def test_queue_rejects_second_session_host(control_plane):
    control_plane.heartbeat(device="d1", user="u1", session_id="s1", adapters=VISMOCKUP)
    with pytest.raises(ConnectorError, match="interactive_session_conflict"):
        control_plane.heartbeat(device="d1", user="u1", session_id="s2", adapters=VISMOCKUP)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest backend/tests/test_connector_runtime_control_plane.py -q`

Expected: new route/model failures.

- [ ] **Step 3: Implement closed heartbeat and compatibility selection**

Heartbeat fields are `connector_version`, `protocol_versions`, `bound_user_id`, `session_id`, `user_session_present`, `session_host_ready`, `system_awake`, `adapters[]`, and `reported_at`. Store only the latest advertisement plus history audit; reject another user/session while the lease is fresh.

`queue_connector_plan` must compare protocol, adapter major, target-product range, every operation ID, and every contract hash before creating a command.

```python
def require_compatible(plan: ConnectorExecutionPlanV1, health: ConnectorHealth) -> None:
    adapter = next((item for item in health.adapters if item.adapter_id == plan.adapter_id), None)
    if adapter is None:
        raise ConnectorError("adapter_unavailable")
    for step in plan.steps:
        if adapter.contract_hash(step.operation_id) != step.contract_hash:
            raise ConnectorError("adapter_contract_mismatch")
```

- [ ] **Step 4: Add v1 Connector routes while retaining v2 Local Runtime compatibility routes**

Add `/api/v1/connector/activate`, `/heartbeat`, `/plans/lease`, `/plans/{plan_id}/complete`, `/plans/{plan_id}/artifacts/...`. Existing `/device-runtime/*` routes remain during migration and must not receive new operation types.

```python
@router.post("/connector/heartbeat")
def connector_heartbeat(body: ConnectorHeartbeatBody, device=Depends(_device_auth)):
    control_plane.record_connector_heartbeat(device["gid"], body)
    return {"success": True}
```

- [ ] **Step 5: Run device, protocol and authorization tests**

Run: `python -m pytest backend/tests/test_connector_runtime_control_plane.py backend/tests/test_device_capabilities.py backend/tests/test_device_domain_boundary.py backend/tests/test_device_runtime_protocol.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add plugins/device/device_backend backend/routers/device_runtime.py backend/tests/test_connector_runtime_control_plane.py
git commit -m "feat(device): add AI00 Connector control plane"
```

### Task 5: Build Immutable Environment Manifests

**Files:**
- Create: `plugins/simulation/simulation_backend/domain/environment_manifest.py`
- Create: `plugins/simulation/simulation_backend/data/environment_repository.py`
- Create: `backend/db/migrations/domains/simulation/0002_connector_environments.sql`
- Create: `backend/tests/test_simulation_environment_manifest.py`
- Modify: `backend/governance/domain_table_ownership.json`

**Interfaces:**
- Produces: `compose_manifest(execution_plan, document_snapshot, model_mappings, capture_profile) -> SimulationEnvironmentManifestV1` and `scene_for(operation_id) -> SceneStateV1`.
- Consumes: exact Task 2/3 outputs and Connector document snapshot contract.

- [ ] **Step 1: Write failing deterministic composition tests**

```python
def test_manifest_is_independent_of_input_collection_order():
    left = compose_manifest(**fixture(order="forward"))
    right = compose_manifest(**fixture(order="reversed"))
    assert left.manifest_hash == right.manifest_hash

def test_reverse_scene_uses_cumulative_products_current_resources_only():
    manifest = compose_manifest(**fixture())
    scene = manifest.scene_for("op-20")
    assert scene.visible_products == ("bom-node-10", "bom-node-20")
    assert scene.visible_resources == ("resource-node-tool-20",)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest backend/tests/test_simulation_environment_manifest.py -q`

Expected: module import failure.

- [ ] **Step 3: Implement pure frozen models, complete binding diagnostics and canonical hash**

```python
class BindingProblem(FrozenModel):
    kind: Literal["not_found", "ambiguous"]
    source_type: Literal["product", "tool", "equipment", "fixture"]
    source_code: str
    candidates: tuple[str, ...] = ()

class CompositionResult(FrozenModel):
    manifest: SimulationEnvironmentManifestV1 | None
    problems: tuple[BindingProblem, ...]
```

Sort every set-like collection before hashing. Return all problems and persist nothing unless `problems == ()`.

- [ ] **Step 4: Add additive Simulation-owned tables and repository**

Create manifest, binding, materialization-run, capture-run, capture-step and artifact-reference tables with owner/team scope, immutable version/hash uniqueness, state checks, and no cross-domain foreign keys.

```sql
CREATE TABLE IF NOT EXISTS workmanship_sim_environment_manifests (
  environment_id VARCHAR(64) NOT NULL,
  environment_version BIGINT NOT NULL,
  manifest_hash VARCHAR(71) NOT NULL,
  manifest_json JSON NOT NULL,
  owner_gid VARCHAR(64) NOT NULL,
  team_gid VARCHAR(64) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (environment_id, environment_version),
  UNIQUE KEY uq_sim_manifest_hash (environment_id, manifest_hash)
);
```

- [ ] **Step 5: Run domain and migration tests**

Run: `python -m pytest backend/tests/test_simulation_environment_manifest.py backend/tests/test_simulation_domain_boundary.py plugins/simulation/tests/test_domain_completion.py backend/tests/test_domain_table_ownership.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add plugins/simulation/simulation_backend/domain plugins/simulation/simulation_backend/data backend/db/migrations/domains/simulation/0002_connector_environments.sql backend/governance/domain_table_ownership.json backend/tests/test_simulation_environment_manifest.py
git commit -m "feat(simulation): add immutable connector environment manifests"
```

### Task 6: Register Compose and Preflight Capabilities

**Files:**
- Create: `plugins/simulation/simulation_backend/capabilities/environment_composition.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Modify: `backend/domain_ports/craft.py`
- Modify: `backend/domain_ports/knowledge.py`
- Modify: `backend/domain_ports/digital_model.py`
- Create: `backend/tests/test_simulation_environment_composition_capabilities.py`

**Interfaces:**
- Produces: `simulation.environment.compose@1`, `simulation.environment.manifest.get@1`, `.search@1`, `.archive@1`, and `simulation.environment.preflight@1`.
- Consumes: Task 2 resolver, Task 3 execution plan, Task 4 Connector health/snapshot operation, Task 5 manifest builder.

- [ ] **Step 1: Write failing Gateway tests for success and all-or-nothing failure**

```python
def test_compose_persists_one_manifest_when_all_bindings_resolve(gateway):
    output = invoke(gateway, "simulation.environment.compose", compose_payload(), idempotency_key="compose-1")
    assert output["status"] == "composed"
    assert output["manifest_hash"].startswith("sha256:")

def test_compose_returns_every_problem_and_persists_nothing(gateway, repository):
    output = invoke(gateway, "simulation.environment.compose", unresolved_payload(), idempotency_key="compose-2")
    assert {item["source_code"] for item in output["problems"]} == {"P-X", "T-X"}
    assert repository.count_manifests() == 0

def test_manifest_get_does_not_change_legacy_environment_get_schema(gateway):
    manifest = invoke(gateway, "simulation.environment.manifest.get", {"environment_id": "env-1", "environment_version": 1})
    legacy = invoke(gateway, "simulation.environment.get", {"environment_id": "legacy-env-1"})
    assert "manifest_hash" in manifest
    assert set(legacy) == {"environment_id", "name", "status", "source"}
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest backend/tests/test_simulation_environment_composition_capabilities.py -q`

Expected: catalog cannot resolve the new capability.

- [ ] **Step 3: Implement composition through ports and immutable references**

The handler must fetch sources through injected ports, verify returned version/hash values against request pins, call the pure Task 5 builder, and persist once. It must never import another domain's repository.

Manifest get/search are read-only and bounded; archive changes only the environment identity lifecycle and preserves every version. Preflight is read-only and returns exact missing protocol/adapter/operation/version/hash items; it does not queue a plan.

```python
def compose(payload: dict, context: CapabilityContext) -> CapabilityOutput:
    execution = craft_port.get_execution_plan(payload["execution_plan_ref"], context)
    document = connector_port.get_document_snapshot(payload["device_id"], context)
    mappings = knowledge_port.resolve_resource_models(execution["resources"], context)
    result = compose_manifest(execution, document, mappings, payload["capture_profile"])
    if result.problems:
        return CapabilityOutput(data={"status": "unresolved", "problems": [item.model_dump() for item in result.problems]})
    repository.insert_manifest(result.manifest, context)
    return CapabilityOutput(data=result.manifest.model_dump(mode="json"))
```

- [ ] **Step 4: Declare descriptors, selectors, errors and exposure**

Compose is a write with confirmation, required idempotency/evidence, and selectors for BOP version/device. Preflight is read-only. Add every stable error from spec section 9 with exact retryability.

```python
CapabilitySpec(
    id="simulation.environment.compose", owner="simulation", risk="write", confirmation="user",
    permissions=("simulation.use",), input_schema=INPUT_SCHEMAS["simulation.environment.compose"],
    output_schema=OUTPUT_SCHEMAS["simulation.environment.compose"],
)
```

- [ ] **Step 5: Run Gateway, cross-domain and contract tests**

Run: `python -m pytest backend/tests/test_simulation_environment_composition_capabilities.py backend/tests/integration/test_cross_domain.py backend/tests/test_capability_gateway_pipeline.py backend/tests/test_simulation_reproducibility.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add plugins/simulation/simulation_backend/capabilities backend/domain_ports backend/tests/test_simulation_environment_composition_capabilities.py
git commit -m "feat(simulation): compose and preflight connector environments"
```

### Task 7: Implement Materialization and Reverse Capture Workflows

**Files:**
- Create: `plugins/simulation/simulation_backend/capabilities/capture_runs.py`
- Create: `plugins/simulation/simulation_backend/application/capture_worker.py`
- Create: `plugins/simulation/simulation_backend/application/connector_plans.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Create: `backend/tests/test_simulation_capture_workflow.py`

**Interfaces:**
- Produces: `simulation.environment.materialize@1`, `simulation.capture_run.start@1`, `.get@1`, `.cancel@1`, and `simulation.capture_step.retry@1`.
- Consumes: Task 1 plans, Task 4 queue/reconcile port, Task 3 screenshot attach, Task 5 repository.

- [ ] **Step 1: Write failing workflow tests with a deterministic fake Connector**

```python
def test_capture_plan_orders_operations_descending(fake_connector, workflow):
    run = workflow.start_capture(environment_id="env-1", device_id="dev-1")
    assert [s.payload["operation_id"] for s in fake_connector.last_plan.steps if s.operation_id == "vismockup.view.capture@1"] == ["op-30", "op-20", "op-10"]

def test_completed_artifact_is_attached_once_before_next_step(workflow, craft_spy):
    workflow.advance("run-1")
    assert craft_spy.calls == [("bop-v1", "op-30", "artifact-30", "run-1")]

def test_outcome_unknown_requires_reconciliation_before_retry(workflow):
    workflow.record_outcome_unknown("run-1", "op-30")
    with pytest.raises(SimulationError, match="local_execution_outcome_unknown"):
        workflow.retry_step("run-1", "op-30")
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest backend/tests/test_simulation_capture_workflow.py -q`

Expected: workflow module/capabilities missing.

- [ ] **Step 3: Implement materialization plan generation**

Generate probe, attach-missing-model, scene-apply and scene-verify steps with explicit dependencies. Freeze the environment manifest hash, active document snapshot hash, Adapter contract hashes and ArtifactRefs into the plan.

```python
steps = [probe_step(manifest)]
steps.extend(attach_step(binding, depends_on=(steps[-1].step_id,)) for binding in manifest.resource_bindings)
steps.append(apply_scene_step(manifest.baseline_scene, depends_on=tuple(step.step_id for step in steps)))
steps.append(verify_scene_step(manifest.baseline_scene.scene_hash, depends_on=(steps[-1].step_id,)))
```

- [ ] **Step 4: Implement capture state machine and compensation rules**

For each reversed operation generate `scene.apply -> scene.verify -> view.capture`; only after artifact integrity confirmation invoke Craft attach. Cancel stops unstarted steps. Retry creates a new attempt only when source hashes match and the previous state is `failed`, never `outcome_unknown`.

```python
for operation in sorted(manifest.operations, key=lambda item: (item.sequence, item.operation_id), reverse=True):
    scene = manifest.scene_for(operation.operation_id)
    apply_id = builder.add("vismockup.scene.apply@1", scene.model_dump())
    verify_id = builder.add("vismockup.scene.verify@1", {"scene_hash": scene.scene_hash}, depends_on=(apply_id,))
    builder.add("vismockup.view.capture@1", capture_profile.model_dump(), depends_on=(verify_id,))
```

- [ ] **Step 5: Register capabilities and run failure-recovery tests**

Run: `python -m pytest backend/tests/test_simulation_capture_workflow.py backend/tests/acceptance/test_failure_recovery.py backend/tests/test_artifact_operation_protocol.py backend/tests/test_capability_v2_orchestration_audit.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add plugins/simulation/simulation_backend/capabilities plugins/simulation/simulation_backend/application backend/tests/test_simulation_capture_workflow.py
git commit -m "feat(simulation): orchestrate materialization and reverse capture"
```

### Task 8: Add the Web Workflow and Regenerate Governance Artifacts

**Files:**
- Modify: `dist/packages/sim-plugin/web/cad_sim/index.html`
- Modify: `dist/packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `dist/packages/sim-plugin/web/cad_sim/cad_sim.css`
- Create: `dist/packages/sim-plugin/web/cad_sim/capture_workflow.test.js`
- Modify: generated files under `docs/capabilities/` and `docs/governance/` using repository scripts only.

**Interfaces:**
- Consumes: Task 4 device list/health and Tasks 6-7 Gateway capabilities.
- Produces: browser flow for selecting one Connector, preflight, compose, materialize, capture progress, cancel and failed-step retry.

- [ ] **Step 1: Write failing browser contract tests**

```javascript
test('start is disabled until connector preflight passes', async () => {
  const ui = createCaptureWorkflow({ invoke: fakeInvoke({ compatible: false }) });
  await ui.selectConnector('dev-1');
  assert.equal(ui.canStartCapture(), false);
});

test('browser only calls governed gateway capabilities', () => {
  assert.deepEqual(ALLOWED_CALLS, [
    'simulation.environment.preflight', 'simulation.environment.compose',
    'simulation.environment.materialize', 'simulation.capture_run.start',
    'simulation.capture_run.get', 'simulation.capture_run.cancel',
    'simulation.capture_step.retry'
  ]);
});
```

- [ ] **Step 2: Run test and confirm RED**

Run: `node --test dist/packages/sim-plugin/web/cad_sim/capture_workflow.test.js`

Expected: missing workflow module/exports.

- [ ] **Step 3: Implement the minimal browser flow**

Use the existing plugin Gateway wrapper. Display Connector health, binding problems, operation progress and stable error codes. Do not add browser-to-localhost networking, secret storage, polling faster than two seconds, or client-side business ordering.

```javascript
export async function startCapture(api, environmentId, deviceId) {
  await api.invoke('simulation.environment.preflight', { environment_id: environmentId, device_id: deviceId });
  return api.invoke('simulation.capture_run.start', { environment_id: environmentId, device_id: deviceId });
}
```

- [ ] **Step 4: Run browser and focused backend suites**

Run: `node --test dist/packages/sim-plugin/web/cad_sim/capture_workflow.test.js`

Run: `python -m pytest backend/tests/test_knowledge_resource_model_mapping.py backend/tests/test_craft_process_screenshot_boundary.py backend/tests/test_connector_runtime_control_plane.py backend/tests/test_simulation_environment_manifest.py backend/tests/test_simulation_environment_composition_capabilities.py backend/tests/test_simulation_capture_workflow.py -q`

Expected: all tests pass.

- [ ] **Step 5: Rebuild and check governance projections**

Run: `python backend/scripts/build_capability_catalog.py`

Run: `python backend/scripts/generate_capability_docs.py`

Run: `python backend/scripts/build_capability_acceptance_manifest.py`

Run: `python backend/scripts/build_user_function_registry.py --strict`

Run: `python backend/scripts/check_domain_dependencies.py`

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`

Expected: generated files are current; offline report has zero failed cases. Record skipped runtime checks as unverified.

- [ ] **Step 6: Commit**

```bash
git add dist/packages/sim-plugin/web/cad_sim docs/capabilities docs/governance
git commit -m "feat(simulation): expose governed connector capture workflow"
```

## Plan A Completion Gate

Before starting Plan B, prove that the fake Connector vertical slice composes an immutable environment, rejects unresolved bindings, queues version-matched plans, processes reverse captures, uploads ArtifactRefs and attaches each result once through Craft. This gate may set `machine_passed=true` only for the tested Snapshot; `runtime_verified` remains `false`.
