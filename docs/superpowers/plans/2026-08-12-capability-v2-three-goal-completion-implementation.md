# Capability V2 Three-Goal Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Repository policy prohibits subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Plans 02–15 so Plugin and Agent consume governed Capabilities, all eleven domains own independent code and databases, and domains share capabilities only through Gateway calls or durable domain events.

**Architecture:** Keep the approved coverage review, Capability IDs, ownership and Foundation Plan 01 frozen. Deliver one independently testable vertical slice per domain, finalize central manifests serially, then cut every consumer to Catalog + Gateway and require a zero-debt release-candidate gate. Synchronous sharing uses `DomainCapabilityClient`; asynchronous sharing uses transactional Outbox/Inbox.

**Tech Stack:** Python 3, FastAPI, Pydantic, pytest, MySQL/OceanBase SQL, Capability V2 Catalog/Gateway/Provider contracts, JSON governance manifests, PowerShell execution on Windows.

## Global Constraints

- Do not repeat capability discovery or change frozen function dispositions, Capability IDs, owners or exposure decisions without a separately approved decision record.
- Treat `docs/governance/capability-coverage-review/generated/summary.json` and its five generated views as immutable implementation input.
- The target is exactly eleven first-class domains: Base Platform, Project Management, Factory, Craft, Knowledge, Ontology, Agent, Integration, Local Runtime, Digital Model and Simulation.
- Plugin Platform belongs to Base Platform and is not a twelfth business domain.
- A stable Descriptor has exactly one production Provider; Catalog is the only discovery source and Gateway is the only consumer and cross-domain business execution path.
- Every domain owns its code, runtime credential, DDL credential, database, migration ledger, Provider tests, deployment and rollback.
- No cross-domain SQL, JOIN, foreign key, ORM relation, Router/Repository/ORM/database-helper/concrete-Service import or shared mutable business table is permitted.
- Do not introduce dual writes. Shadow reads are allowed only for side-effect-free comparison before one-way cutover.
- Central governance files are frozen by the single inline integrator on current HEAD; a stale HEAD or manifest digest fails closed.
- Plugin and Agent RC evidence must cross real consumer, Gateway and Provider process boundaries and use real database grants.
- RC requires zero cross-domain SQL, zero internal imports, zero business bypasses, zero failures and zero skips.
- Preserve `CODEX-DESKTOP-HANDOFF.md` and the two untracked review documents unchanged and uncommitted.

## Authoritative Inputs

- Design: `docs/superpowers/specs/2026-08-12-capability-v2-three-goal-completion-design.md`
- Detailed architecture: `docs/superpowers/specs/2026-08-11-capability-v2-domain-rearchitecture-design.md`
- Ordering: `docs/superpowers/plans/2026-08-11-capability-v2-domain-rearchitecture-roadmap.md`
- Frozen review: `docs/governance/capability-coverage-review/generated/`
- Domain manifests: `backend/capability_v2/official_domains.json`
- Current debt: `backend/governance/boundary_baseline.json`
- Table/database ownership: `backend/governance/table_inventory.json` and `docs/governance/capability-coverage-review/generated/database-ownership-migrations.md`

The starting debt snapshot is 338 boundary violations: 332 cross-domain SQL findings and 6 internal implementation imports. These are burn-down inputs, not accepted final-state waivers.

The frozen coverage snapshot contains 752 stable user functions, 87 reviewed candidate Capabilities, 102 current Descriptors and a proposed final total of 173 Capabilities. Tasks consume these generated records directly; no task performs a new inventory or changes the counts to make implementation easier.

## Target File Map

| Plan | Primary implementation roots | Primary tests |
|---|---|---|
| Common gates | `backend/capability_v2/completion.py`, `backend/scripts/check_capability_v2_completion.py`, `backend/governance/capability_v2_completion.json` | `backend/tests/test_capability_v2_completion.py` |
| 02 Base | `backend/base/`, `backend/plugin_platform/`, `backend/db/migrations/domains/base/` | `backend/tests/test_base_capability_contracts.py`, `backend/tests/test_plugin_platform_next.py` |
| 03 Project Management | `plugins/project_management/`, `backend/db/migrations/domains/project_management/` | `plugins/project_management/tests/`, `backend/tests/test_projects_router.py` |
| 04 Factory | `plugins/factory/`, `backend/db/migrations/domains/factory/` | `plugins/factory/tests/`, `backend/tests/test_craft_data_boundary.py` |
| 05 Knowledge | `plugins/knowledge/`, `backend/db/migrations/domains/knowledge/` | `plugins/knowledge/tests/`, `backend/tests/test_knowledge_capability_contracts.py` |
| 06 Ontology | `plugins/ontology/`, `backend/db/migrations/domains/ontology/` | `plugins/ontology/tests/`, `backend/tests/test_ontology_concept_capabilities.py` |
| 07–09 Craft | `plugins/craft/craft_backend/`, `backend/db/migrations/domains/craft/` | `plugins/craft/tests/`, `backend/tests/test_craft_*` |
| 10 Digital Model | `plugins/digital_model/`, `backend/db/migrations/domains/digital_model/` | `plugins/digital_model/tests/`, `backend/tests/test_digital_model_capabilities.py` |
| 11 Simulation | `plugins/simulation/`, `backend/db/migrations/domains/simulation/` | `plugins/simulation/tests/`, `backend/tests/test_simulation_reproducibility.py` |
| 12 Integration | `plugins/integration/`, `backend/db/migrations/domains/integration/` | `plugins/integration/tests/`, `backend/tests/test_external_service_ownership.py` |
| 13 Local Runtime | `plugins/device/device_backend/`, `backend/db/migrations/domains/local_runtime/` | `plugins/device/tests/`, `backend/tests/test_local_operation_protocol_v2.py` |
| 14 Agent | `plugins/agent/agent_backend/`, `backend/db/migrations/domains/agent/` | `plugins/agent/tests/`, `backend/tests/test_agent_consumer_catalog.py` |
| 15 Cutover/RC | `backend/routers/`, `backend/scripts/`, `backend/tests/acceptance/` | consumer, boundary and acceptance suites |

## Serial Domain Finalization Procedure

After the domain-code commit in every Plan 02–14 task, the inline integrator runs this exact procedure before starting a dependent domain. The working tree must contain no unrelated staged files.

```powershell
$integrationHead = git rev-parse HEAD
$manifestDigest = "sha256:" + (Get-FileHash backend/capability_v2/official_domains.json -Algorithm SHA256).Hash.ToLowerInvariant()
python backend/scripts/freeze_official_domains.py --expected-head $integrationHead --expected-manifest-sha256 $manifestDigest
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
python backend/scripts/build_capability_acceptance_manifest.py --write
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/build_user_function_registry.py --strict
python backend/scripts/check_domain_dependencies.py
python backend/scripts/audit_domain_boundaries.py
git add -- backend/capability_v2/official_domains.json docs/governance/capability-catalog-release.json docs/capabilities backend/tests/acceptance/fixtures/case-manifest.json
git commit -m "chore: freeze capability release"
```

If any command fails, do not commit central artifacts and do not begin the dependent task.

---

### Task 1: Add a Machine-Enforced Three-Goal Completion Gate

**Files:**
- Create: `backend/capability_v2/completion.py`
- Create: `backend/scripts/check_capability_v2_completion.py`
- Create: `backend/governance/capability_v2_completion.json`
- Create: `backend/governance/capability_v2_production_paths.json`
- Create: `backend/tests/test_capability_v2_completion.py`
- Create: `backend/tests/capability_completion_support.py`
- Modify: `backend/scripts/run_capability_v2_acceptance.py`

**Interfaces:**
- Consumes: `DomainManifestSet`, frozen coverage `summary.json`, `boundary_baseline.json`, Catalog release and consumer exposure records.
- Produces: `FrozenCoverageReview`, `CompletionReport`, `evaluate_completion(root: Path, mode: Literal["progress", "strict"]) -> CompletionReport`, `registered_descriptor_ids(module_name: str) -> set[str]`, `assert_database_denied(connection: Any, sql: str) -> None`, a validated production-path registry and a CLI that returns nonzero when strict completion is false.

- [ ] **Step 1: Write failing contract tests**

```python
def test_strict_completion_requires_all_three_goals(repo_copy):
    report = evaluate_completion(repo_copy, mode="strict")
    assert set(report.domains) == {
        "base", "project_management", "factory", "craft", "knowledge",
        "ontology", "agent", "integration", "local_runtime",
        "digital_model", "simulation",
    }
    assert report.plugin_agent_gateway_only is True
    assert report.independent_domains == 11
    assert report.sync_production_paths >= 1
    assert report.async_production_paths >= 1
    assert report.cross_domain_sql == 0
    assert report.internal_imports == 0
    assert report.consumer_bypasses == 0
```

- [ ] **Step 2: Verify the test fails against the current repository**

Run: `python -m pytest backend/tests/test_capability_v2_completion.py -q`

Expected: FAIL because Factory, Integration and Agent are absent from `official_domains.json`, production sharing evidence is absent, and the boundary baseline is nonzero.

- [ ] **Step 3: Implement the report and immutable contract**

```python
@dataclass(frozen=True)
class CompletionReport:
    domains: tuple[str, ...]
    plugin_agent_gateway_only: bool
    independent_domains: int
    sync_production_paths: int
    async_production_paths: int
    cross_domain_sql: int
    internal_imports: int
    consumer_bypasses: int
    failed: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.failed
```

Store the eleven domain IDs, three goal predicates, frozen input paths and required RC evidence keys in `capability_v2_completion.json`. `progress` reports unmet predicates without weakening them; `strict` exits 1 unless every predicate passes. Do not store waivers in this file.

Create `capability_v2_production_paths.json` with schema version 1 and initially empty `sync` and `async` arrays. Each later entry requires a stable path ID, caller/producer, callee/consumer, Capability or event contract, production source module and exact E2E pytest node ID. `evaluate_completion` rejects missing modules, missing test nodes, duplicate IDs and test-only source modules.

`FrozenCoverageReview` loads the generated coverage documents read-only and exposes `capability_ids(owner: str) -> frozenset[str]`. `registered_descriptor_ids` imports the official module into an isolated registry and returns the registered IDs. `assert_database_denied` executes the supplied SQL and passes only for the database driver's access-denied error code; connection or syntax errors must fail the test.

- [ ] **Step 4: Integrate the strict report into acceptance**

Add the completion report to release-candidate output. Offline mode reports progress but does not claim RC completion. Release-candidate mode fails if `complete` is false or any required evidence is missing/skipped.

- [ ] **Step 5: Run the gate tests**

Run: `python -m pytest backend/tests/test_capability_v2_completion.py backend/tests/acceptance/test_acceptance_runner.py -q`

Expected: PASS for report behavior; an explicit strict invocation against the current repository returns nonzero and lists exact unmet predicates.

- [ ] **Step 6: Commit**

```powershell
git add -- backend/capability_v2/completion.py backend/scripts/check_capability_v2_completion.py backend/governance/capability_v2_completion.json backend/governance/capability_v2_production_paths.json backend/tests/test_capability_v2_completion.py backend/tests/capability_completion_support.py backend/scripts/run_capability_v2_acceptance.py
git commit -m "feat: enforce capability v2 three-goal completion"
```

### Task 2: Plan 02 — Complete Base Platform and Plugin Platform

**Files:**
- Modify: `backend/base/contracts.py`
- Modify: `backend/base/operations.py`
- Modify: `backend/base/provider.py`
- Modify: `backend/base/official_provider.py`
- Modify: `backend/plugin_platform/`
- Create: `backend/db/migrations/domains/base/0001_base_platform.sql`
- Modify: `backend/tests/test_base_capability_contracts.py`
- Modify: `backend/tests/test_plugin_platform_next.py`
- Modify: `backend/tests/test_system_shared_capabilities.py`

**Interfaces:**
- Consumes: frozen Base candidate/exposure rows and Foundation Provider/Database contracts.
- Produces: Base Descriptors and Provider for Tenant, Approval, Notification, Workspace, Plugin Platform and System search/lineage/impact; Base-owned event projections used by later domains.

- [ ] **Step 1: Write failing Base completeness and isolation tests**

```python
def test_base_provider_matches_frozen_review(frozen_review):
    expected = frozen_review.capability_ids(owner="base")
    actual = registered_descriptor_ids("backend.base.official_provider")
    assert actual == expected

def test_base_runtime_grant_cannot_read_knowledge(base_runtime_db):
    assert_database_denied(
        base_runtime_db, "SELECT * FROM workmanship_know_documents"
    )
```

- [ ] **Step 2: Run the focused tests and capture failures**

Run: `python -m pytest backend/tests/test_base_capability_contracts.py backend/tests/test_plugin_platform_next.py backend/tests/test_system_shared_capabilities.py -q`

Expected: FAIL on missing frozen Base outcomes and direct access to non-Base tables.

- [ ] **Step 3: Implement Base vertical slices**

Keep domain state in `ai00_base`; use the Base runtime connection only. Implement pending Approval lookup by `subject_ref`, idempotent per-approval cancellation with expected pending state, Notification, Workspace, Plugin installation/grant/revoke and manifest-driven `system.search`. Remove health, echo, retry and transport pseudo-capabilities from business Descriptors.

```python
def register_capabilities(registry: CapabilityRegistry) -> None:
    register_tenant_capabilities(registry)
    register_approval_capabilities(registry)
    register_notification_capabilities(registry)
    register_workspace_capabilities(registry)
    register_plugin_platform_capabilities(registry)
    register_system_shared_capabilities(registry)
```

- [ ] **Step 4: Prove Plugin discovery and denial use Catalog + Gateway**

Add E2E tests that install a real test plugin, discover its allowed Catalog subset, invoke one permitted Base Capability, reject one ungranted Capability and match both results to audit records. Assert the plugin adapter imports no Base application or repository module.

- [ ] **Step 5: Run Base, Plugin and database tests**

Run: `python -m pytest backend/tests/test_base_capability_contracts.py backend/tests/test_plugin_platform_next.py backend/tests/test_plugin_authority_boundary.py backend/tests/test_domain_database_config.py -q`

Expected: PASS.

- [ ] **Step 6: Commit domain code, then serially freeze central artifacts**

```powershell
git add -- backend/base backend/plugin_platform backend/db/migrations/domains/base backend/tests/test_base_capability_contracts.py backend/tests/test_plugin_platform_next.py backend/tests/test_system_shared_capabilities.py
git commit -m "feat: complete base platform capability provider"
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
```

Run the Serial Domain Finalization Procedure with domain label `base`.

### Task 3: Plan 03 — Extract Project Management

**Files:**
- Create: `plugins/project_management/project_management_backend/domain/`
- Create: `plugins/project_management/project_management_backend/application/`
- Expand: `plugins/project_management/project_management_backend/capabilities/`
- Create: `plugins/project_management/project_management_backend/infrastructure/`
- Create: `plugins/project_management/project_management_backend/api/compatibility.py`
- Create: `backend/db/migrations/domains/project_management/0001_project_management.sql`
- Modify: `plugins/project_management/tests/test_project_capabilities.py`
- Create: `plugins/project_management/tests/test_database_isolation.py`

**Interfaces:**
- Consumes: Base Tenant/Approval/Notification contracts and frozen Project Management rows.
- Produces: Project, Member, Task, Issue, List, Follow, Collaboration and Share Link Capabilities; `project_management.search` export.

- [ ] **Step 1: Add failing Provider, ownership and grant tests**

```python
def test_project_provider_is_complete(frozen_review):
    actual = registered_descriptor_ids(
        "project_management_backend.capabilities"
    )
    assert actual == frozen_review.capability_ids(owner="project_management")

def test_project_credential_cannot_read_craft(project_db):
    assert_database_denied(
        project_db, "SELECT * FROM workmanship_bop_pbom_versions"
    )
```

- [ ] **Step 2: Run the tests and verify missing aggregates fail**

Run: `python -m pytest plugins/project_management/tests backend/tests/test_projects_router.py -q`

Expected: FAIL until every frozen Project Management result has a native Provider path.

- [ ] **Step 3: Move Project Management behavior and data ownership**

Implement domain/application/repository slices in the new package. Compatibility routes must construct an `InvocationEnvelope` and invoke Gateway; they must contain no SQL. Move all `workmanship_proj_*` and reviewed `workmanship_work_*` ownership into the new migration and runtime credential.

- [ ] **Step 4: Delete Craft and Base implementations of moved behavior**

Remove Project/List/Share/Collaboration business logic from `plugins/craft/craft_backend/routers/` and direct Project table reads from `backend/routers/` and `backend/platform_sdk/`. Keep only temporary Gateway adapters named in the cutover test.

- [ ] **Step 5: Run Project and boundary tests**

Run: `python -m pytest plugins/project_management/tests backend/tests/test_projects_router.py backend/tests/test_craft_projects_boundary.py backend/tests/test_craft_lists_boundary.py backend/tests/test_craft_collab_boundary.py -q`

Expected: PASS with Project-specific boundary debt removed.

- [ ] **Step 6: Commit and finalize**

Commit domain code as `feat: extract project management domain`, then regenerate/freeze DomainManifest, Catalog, registry and boundary artifacts on current HEAD in a separate `chore: freeze project management capability release` commit.

### Task 4: Plan 04 — Build the Independent Factory Domain

**Files:**
- Create: `plugins/factory/factory_backend/domain/`
- Create: `plugins/factory/factory_backend/application/`
- Create: `plugins/factory/factory_backend/capabilities/descriptors.py`
- Create: `plugins/factory/factory_backend/capabilities/contracts.py`
- Create: `plugins/factory/factory_backend/capabilities/provider.py`
- Create: `plugins/factory/factory_backend/infrastructure/`
- Create: `plugins/factory/factory_backend/bootstrap.py`
- Create: `backend/db/migrations/domains/factory/0001_factory.sql`
- Create: `plugins/factory/tests/test_factory_provider.py`
- Create: `plugins/factory/tests/test_database_isolation.py`

**Interfaces:**
- Consumes: Base common refs and frozen Factory ownership.
- Produces: physical Factory/Site/Area/Line/Station, Resource Catalog and physical Asset Provider used by Craft BOP through Gateway.

- [ ] **Step 1: Write failing physical-model and isolation tests**

```python
def test_factory_has_one_official_provider(official_domains):
    factory = official_domains.require("factory")
    assert factory.artifact.module == "factory_backend.capabilities"
    assert factory.database.database_name == "ai00_factory"

def test_factory_model_excludes_bop_plan_nodes(factory_model):
    assert not hasattr(factory_model, "line_process")
    assert not hasattr(factory_model, "station_process")
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest plugins/factory/tests backend/tests/test_official_domain_entrypoints.py -q`

Expected: FAIL because Factory is not yet an official loadable domain.

- [ ] **Step 3: Implement Factory Provider and database**

Keep only physical topology, resource catalog and assets in Factory. Enforce immutable IDs and optimistic concurrency. Do not add production scheduling or BOP plan structures. Register the new artifact only after its Provider loads and its Descriptor owner is `factory`.

- [ ] **Step 4: Remove Factory logic and tables from Craft**

Replace `plugins/craft/craft_backend/routers/factory.py` and `_bop/factory.py` business access with Gateway adapters. Craft may retain exact `ResourceRef` bindings but cannot query Factory tables.

- [ ] **Step 5: Run tests and finalize**

Run: `python -m pytest plugins/factory/tests backend/tests/test_craft_data_boundary.py backend/tests/test_domain_provider_loader.py -q`

Expected: PASS. Commit domain code as `feat: establish factory domain`, then freeze central artifacts separately.

### Task 5: Plan 05 — Rebuild Knowledge as an Independent Domain

**Files:**
- Create: `plugins/knowledge/knowledge_backend/domain/`
- Create: `plugins/knowledge/knowledge_backend/application/`
- Create: `plugins/knowledge/knowledge_backend/capabilities/`
- Create: `plugins/knowledge/knowledge_backend/infrastructure/`
- Create: `plugins/knowledge/knowledge_backend/bootstrap.py`
- Create: `backend/db/migrations/domains/knowledge/0001_knowledge.sql`
- Create: `plugins/knowledge/tests/test_knowledge_provider.py`
- Create: `plugins/knowledge/tests/test_publication_outbox.py`

**Interfaces:**
- Consumes: Base Tenant, Approval, ArtifactRef and event contracts.
- Produces: Space, Document, immutable Revision, ACL, favorite, pin, Proposal and publication Capabilities; versioned `knowledge.document.published.v1` events.

- [ ] **Step 1: Write failing immutable revision and Outbox tests**

```python
def test_publish_writes_revision_and_outbox_atomically(uow, service):
    result = service.publish(document_id="doc-1", expected_revision=3)
    assert uow.revisions.get(result.revision_ref).immutable is True
    assert uow.outbox.one(event_type="knowledge.document.published.v1").subject_ref == "doc-1"
```

- [ ] **Step 2: Run existing and new Knowledge tests**

Run: `python -m pytest plugins/knowledge/tests backend/tests/test_knowledge_capability_contracts.py backend/tests/test_knowledge_document_capabilities.py -q`

Expected: FAIL until the native Knowledge Provider replaces legacy Entry/Hub paths.

- [ ] **Step 3: Implement the Knowledge package and migration**

Build Document/Revision as the authority. Write the immutable revision and Outbox row in the same `ai00_knowledge` transaction. Move ACL/favorite/pin/proposal behavior into the Knowledge application layer.

- [ ] **Step 4: Remove legacy direct SQL and publish workers**

Delete or convert `backend/routers/knowledge.py`, `backend/routers/knowledge_hub.py`, `backend/platform_sdk/knowledge.py` and `backend/capabilities/outbox_worker_next.py` into Gateway/transport adapters with no Knowledge SQL.

- [ ] **Step 5: Run tests and finalize**

Run: `python -m pytest plugins/knowledge/tests backend/tests/test_knowledge_data_boundary.py backend/tests/test_knowledge_hub_access_boundary.py backend/tests/test_knowledge_publication_saga.py -q`

Expected: PASS. Commit `feat: rebuild knowledge domain`, then freeze central artifacts separately.

### Task 6: Plan 06 — Rebuild Ontology as an Independent Domain

**Files:**
- Create: `plugins/ontology/ontology_backend/domain/`
- Create: `plugins/ontology/ontology_backend/application/`
- Create: `plugins/ontology/ontology_backend/capabilities/`
- Create: `plugins/ontology/ontology_backend/infrastructure/`
- Create: `plugins/ontology/ontology_backend/bootstrap.py`
- Create: `backend/db/migrations/domains/ontology/0001_ontology.sql`
- Create: `plugins/ontology/tests/test_ontology_provider.py`
- Create: `plugins/ontology/tests/test_database_isolation.py`

**Interfaces:**
- Consumes: Base Approval/Artifact contracts and Revision Kernel public contracts.
- Produces: Concept reads, Proposal/Review, Release/Activation and impact events; no direct schema CRUD surface.

- [ ] **Step 1: Add failing lifecycle and dependency tests**

```python
def test_activation_requires_approved_release(service, pending_release):
    with pytest.raises(ApprovalRequired):
        service.activate(pending_release.ref)

def test_ontology_package_has_no_backend_internal_imports(import_graph):
    assert import_graph.for_domain("ontology").internal_cross_domain == set()
```

- [ ] **Step 2: Verify failures**

Run: `python -m pytest plugins/ontology/tests backend/tests/test_ontology_proposal_capabilities.py backend/tests/test_ontology_release_capabilities.py -q`

Expected: FAIL on the new package and current six-import baseline contributions.

- [ ] **Step 3: Implement Ontology and remove internal imports**

Move persistence behind Ontology outbound ports. Replace `backend.utils.gid`, `backend.core.ois_storage` and `backend.db.connection` imports with injected public infrastructure protocols. Activation remains a distinct high-risk Capability.

- [ ] **Step 4: Remove direct schema CRUD and Craft Ontology SQL**

Convert compatibility routes to Gateway and change Craft rule checks to exact Ontology Capability calls or immutable release refs. Delete dynamic `entity_table` access.

- [ ] **Step 5: Run tests and finalize**

Run: `python -m pytest plugins/ontology/tests backend/tests/test_ontology_concept_capabilities.py backend/tests/test_craft_ontology_boundary.py backend/tests/test_domain_independence_v2.py -q`

Expected: PASS with Ontology internal-import debt at zero. Commit `feat: rebuild ontology domain`, then freeze central artifacts separately.

### Task 7: Plan 07 — Complete Craft PBOM

**Files:**
- Create: `plugins/craft/craft_backend/domain/pbom.py`
- Create: `plugins/craft/craft_backend/application/pbom.py`
- Create: `plugins/craft/craft_backend/capabilities/pbom_descriptors.py`
- Create: `plugins/craft/craft_backend/infrastructure/repositories/pbom.py`
- Create: `plugins/craft/tests/test_pbom_provider.py`
- Modify: `plugins/craft/craft_backend/routers/ebom.py`
- Modify: `backend/db/migrations/domains/craft/`

**Interfaces:**
- Consumes: Project refs, Knowledge revision refs, Ontology release refs and Revision Kernel.
- Produces: PBOM draft/version/import/part Capabilities and `CraftPbomRevisionAdapter` with no eBOM aliases.

- [ ] **Step 1: Write failing naming, immutability and Provider tests**

```python
def test_craft_contains_no_ebom_identifiers(repository_text):
    assert "ebom" not in repository_text.lower()

def test_published_pbom_version_is_immutable(service, published_version):
    with pytest.raises(ImmutableVersionError):
        service.change_part(published_version.ref, part="P-2")
```

- [ ] **Step 2: Run PBOM tests and verify failure**

Run: `python -m pytest plugins/craft/tests/test_pbom_provider.py backend/tests/test_craft_capability_contracts.py -q`

Expected: FAIL while eBOM surfaces and incomplete native Provider registration remain.

- [ ] **Step 3: Implement native PBOM slices and delete aliases**

Use only PBOM names in code, routes, migrations, tests, generated docs and governance records. Provider calls application services; published versions are immutable and record exact external refs.

- [ ] **Step 4: Run tests and finalize**

Run: `python -m pytest plugins/craft/tests/test_pbom_provider.py backend/tests/test_craft_write_capabilities.py backend/tests/test_native_capability_registration.py -q`

Expected: PASS. Commit `feat: complete native pbom capabilities`, then freeze central artifacts separately.

### Task 8: Plan 08 — Complete Craft BOP and the Production Synchronous Sharing Path

**Files:**
- Create: `plugins/craft/craft_backend/domain/bop.py`
- Create: `plugins/craft/craft_backend/application/bop.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_structure.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_versions.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_writes.py`
- Create: `plugins/craft/craft_backend/infrastructure/domain_clients.py`
- Create: `plugins/craft/tests/test_bop_domain_sharing.py`
- Modify: `backend/governance/capability_v2_production_paths.json`

**Interfaces:**
- Consumes: PBOM exact CommitRef, Factory ResourceRef and Ontology release through `DomainCapabilityClient.invoke(...)`.
- Produces: six-level BOP plan, typed draft changes, publish/execution-plan Capabilities and `CraftBopRevisionAdapter`.

- [ ] **Step 1: Write a failing real synchronous-path test**

```python
async def test_bop_binding_uses_gateway(domain_client, gateway_trace, bop_service):
    await bop_service.bind_factory_resource(
        bop_ref="bop-1", resource_ref="factory:station:ST-1"
    )
    assert gateway_trace.last.consumer == "domain:craft"
    assert gateway_trace.last.provider_owner == "factory"
    assert gateway_trace.last.capability_id == "factory.resource.read"
```

- [ ] **Step 2: Verify current direct access fails the test**

Run: `python -m pytest plugins/craft/tests/test_bop_domain_sharing.py backend/tests/test_domain_capability_client.py -q`

Expected: FAIL until Craft calls Factory through DomainCapabilityClient/Gateway.

- [ ] **Step 3: Implement BOP and replace all cross-domain reads**

Enforce `BOP Version -> LineProcess -> StationProcess -> WorkPosition -> Process -> Operation`. Bind exact PBOM CommitRef and immutable Ontology release refs. Resolve mutable Factory references only through the domain client; do not cache Factory rows.

```python
result = await self._domain_client.invoke(
    DomainInvocation(
        capability_id="factory.resource.read",
        major_version=1,
        payload={"resource_ref": resource_ref},
    ),
    identity=domain_identity,
    correlation=correlation,
    deadline=deadline,
)
```

- [ ] **Step 4: Test errors, timeout and authorization**

Add assertions for authorization denial, deadline exceeded, stale PBOM ref and missing Factory resource. Each public error must map to the declared BOP Capability error without leaking Provider internals.

Register path ID `craft-factory-resource-binding` with caller `craft`, callee `factory`, contract `factory.resource.read`, production module `craft_backend.infrastructure.domain_clients` and E2E node `plugins/craft/tests/test_bop_domain_sharing.py::test_bop_binding_uses_gateway`.

- [ ] **Step 5: Run tests and finalize**

Run: `python -m pytest plugins/craft/tests/test_bop_domain_sharing.py backend/tests/test_craft_bop_version_capabilities.py backend/tests/test_craft_execution_structure_capabilities.py backend/tests/test_bop_line_permissions.py -q`

Expected: PASS and completion progress reports one production synchronous path. Commit `feat: complete bop domain sharing`, then freeze central artifacts separately.

### Task 9: Plan 09 — Complete Craft GBOP and Rules

**Files:**
- Create: `plugins/craft/craft_backend/domain/gbop.py`
- Create: `plugins/craft/craft_backend/domain/rules.py`
- Create: `plugins/craft/craft_backend/application/gbop.py`
- Create: `plugins/craft/craft_backend/application/rules.py`
- Create: `plugins/craft/craft_backend/capabilities/gbop_descriptors.py`
- Create: `plugins/craft/craft_backend/capabilities/rule_descriptors.py`
- Create: `plugins/craft/tests/test_gbop_rule_provider.py`
- Modify: `plugins/craft/craft_backend/rule_engine/`

**Interfaces:**
- Consumes: published BOP/PBOM refs, Knowledge documents and Ontology releases.
- Produces: GBOP draft/release, rule release, validation and waiver Capabilities plus lineage edges.

- [ ] **Step 1: Write failing release and waiver tests**

```python
def test_rule_waiver_does_not_mutate_published_release(service, release):
    waiver = service.waive(release.ref, violation="V-1", reason="approved")
    assert waiver.release_ref == release.ref
    assert service.get_release(release.ref) == release
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest plugins/craft/tests/test_gbop_rule_provider.py backend/tests/test_craft_validation_policy.py -q`

Expected: FAIL until GBOP/Rule native Providers and immutable releases exist.

- [ ] **Step 3: Implement native Providers and remove dynamic Ontology SQL**

Rules evaluate immutable inputs and return Evidence. Replace rule-engine table-name lookup with Ontology Capability outputs or exact release artifacts. Waivers are separate governed records and never rewrite published BOP/PBOM/GBOP.

- [ ] **Step 4: Run tests and finalize**

Run: `python -m pytest plugins/craft/tests/test_gbop_rule_provider.py backend/tests/test_craft_validation_policy.py backend/tests/test_craft_compare_pbom_gbop_capabilities.py backend/tests/test_craft_ontology_boundary.py -q`

Expected: PASS. Commit `feat: complete gbop and rule capabilities`, then freeze central artifacts separately.

### Task 10: Plan 10 — Finalize Digital Model

**Files:**
- Modify: `plugins/digital_model/digital_model_backend/capabilities/`
- Create: `plugins/digital_model/digital_model_backend/domain/`
- Create: `plugins/digital_model/digital_model_backend/application/`
- Create: `backend/db/migrations/domains/digital_model/0001_digital_model.sql`
- Create: `plugins/digital_model/tests/test_domain_completion.py`

**Interfaces:**
- Consumes: Base ArtifactRef and Project refs.
- Produces: immutable Model Version, trusted component extraction and exact model-version refs for Simulation.

- [ ] **Step 1: Write failing Model Version tests**

```python
def test_published_model_version_is_immutable(service, published_version):
    with pytest.raises(ImmutableVersionError):
        service.replace_component(
            version_ref=published_version.ref,
            component_ref="component:C-2",
        )
```

- [ ] **Step 2: Run the Digital Model suite**

Run: `python -m pytest plugins/digital_model/tests backend/tests/test_digital_model_capabilities.py -q`

Expected: FAIL on incomplete package boundaries and mutable version behavior.

- [ ] **Step 3: Complete the Digital Model vertical slice**

Use one `Model Version` term, immutable versions and trusted extraction Evidence. Provider and Repository use only the Digital Model database credential.

- [ ] **Step 4: Run tests and finalize**

Run: `python -m pytest plugins/digital_model/tests backend/tests/test_digital_model_capabilities.py backend/tests/test_domain_independence_v2.py -q`

Expected: PASS. Commit `feat: complete digital model domain`, then freeze central artifacts separately.

### Task 11: Plan 11 — Finalize Simulation

**Files:**
- Modify: `plugins/simulation/simulation_backend/capabilities/`
- Create: `plugins/simulation/simulation_backend/domain/`
- Create: `plugins/simulation/simulation_backend/application/`
- Create: `backend/db/migrations/domains/simulation/0001_simulation.sql`
- Create: `plugins/simulation/tests/test_domain_completion.py`

**Interfaces:**
- Consumes: exact BOP and Model Version refs through governed Capability contracts.
- Produces: reproducible Environment, separate Run/Operation and comparable Result Evidence.

- [ ] **Step 1: Write a failing reproducibility test**

```python
def test_simulation_replay_uses_exact_inputs(service, completed_run):
    replay = service.replay(completed_run.run_ref)
    assert replay.input_refs == completed_run.input_refs
    assert replay.environment_ref == completed_run.environment_ref
```

- [ ] **Step 2: Run the Simulation suite**

Run: `python -m pytest plugins/simulation/tests backend/tests/test_simulation_reproducibility.py -q`

Expected: FAIL until Run/Operation separation and exact environment refs exist.

- [ ] **Step 3: Complete the Simulation vertical slice**

Separate user-visible Run from asynchronous Operation. Persist exact input refs and environment digest; comparison consumes Result refs, not mutable rows. Repository access uses only the Simulation credential.

- [ ] **Step 4: Run tests and finalize**

Run: `python -m pytest plugins/simulation/tests backend/tests/test_simulation_domain_boundary.py backend/tests/test_simulation_reproducibility.py -q`

Expected: PASS. Commit `feat: complete simulation domain`, then freeze central artifacts separately.

### Task 12: Plan 12 — Build Integration Core and Target Adapters

**Files:**
- Create: `plugins/integration/integration_backend/domain/`
- Create: `plugins/integration/integration_backend/application/`
- Create: `plugins/integration/integration_backend/capabilities/`
- Create: `plugins/integration/integration_backend/infrastructure/`
- Create: `plugins/integration/integration_backend/bootstrap.py`
- Create: `backend/db/migrations/domains/integration/0001_integration.sql`
- Create: `plugins/integration/tests/test_integration_provider.py`
- Create: `plugins/integration/tests/test_target_gateway_writes.py`

**Interfaces:**
- Consumes: target-domain Capability contracts through DomainCapabilityClient.
- Produces: Connector, mapping and sync orchestration Capabilities; target adapters that never write target tables directly.

- [ ] **Step 1: Write failing target-write and network-policy tests**

```python
async def test_import_writes_target_through_gateway(sync_service, gateway_trace):
    await sync_service.apply_batch(mapping="M-1", target_domain="knowledge")
    assert gateway_trace.last.consumer == "domain:integration"
    assert gateway_trace.last.provider_owner == "knowledge"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest plugins/integration/tests backend/tests/test_external_service_ownership.py -q`

Expected: FAIL because Integration is not an official Provider and legacy external datasource routes own mixed behavior.

- [ ] **Step 3: Implement Core and safe adapters**

Store connector secrets only through secret storage; enforce scheme/host allowlist, DNS/IP recheck, timeout and response-size limits. Map external records to declared target Capability inputs. Target adapters invoke Gateway and cannot import target repositories or SQL.

- [ ] **Step 4: Delete mixed Base/Craft integration paths**

Remove business SQL from `backend/routers/ext_datasource.py` and `plugins/craft/craft_backend/services/bitable_sync.py`; retain only protocol adapters that call Integration Capabilities.

- [ ] **Step 5: Run tests and finalize**

Run: `python -m pytest plugins/integration/tests backend/tests/test_external_service_ownership.py backend/tests/test_domain_independence_v2.py -q`

Expected: PASS. Commit `feat: establish integration domain`, then freeze central artifacts separately.

### Task 13: Plan 13 — Complete Local Runtime

**Files:**
- Create: `plugins/device/device_backend/domain/`
- Create: `plugins/device/device_backend/application/`
- Modify: `plugins/device/device_backend/capabilities/`
- Create: `plugins/device/device_backend/infrastructure/`
- Create: `backend/db/migrations/domains/local_runtime/0001_local_runtime.sql`
- Create: `plugins/device/tests/test_local_runtime_provider.py`
- Modify: `backend/tests/test_local_operation_protocol_v2.py`

**Interfaces:**
- Consumes: Base identity/authorization and immutable Digital Model refs.
- Produces: Device enrollment/revocation, signed local Operation control and explicit VisMockup Capabilities owned only by `local_runtime`.

- [ ] **Step 1: Write failing owner, signature and replay tests**

```python
def test_local_runtime_has_no_legacy_owner(manifests):
    domain = manifests.require("local_runtime")
    assert domain.allowed_owners == ("local_runtime",)

def test_replayed_operation_is_rejected(control_plane, signed_operation):
    control_plane.accept(signed_operation)
    with pytest.raises(ReplayDetected):
        control_plane.accept(signed_operation)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest plugins/device/tests backend/tests/test_local_operation_protocol_v2.py backend/tests/test_device_domain_boundary.py -q`

Expected: FAIL while the `local_integration` owner alias remains.

- [ ] **Step 3: Implement Local Runtime boundaries**

Allow only enumerated, signed operations with nonce/expiry, device revocation and result reconciliation. Replace generic local commands with explicit VisMockup actions. Change all Descriptor owners to `local_runtime` and remove the alias.

- [ ] **Step 4: Run tests and finalize**

Run: `python -m pytest plugins/device/tests backend/tests/test_local_operation_protocol_v2.py backend/tests/test_device_capabilities.py backend/tests/test_device_runtime_protocol.py -q`

Expected: PASS. Commit `feat: complete local runtime domain`, then freeze central artifacts separately.

### Task 14: Plan 14 — Complete Agent and Catalog-Generated Tools

**Files:**
- Create: `plugins/agent/agent_backend/domain/`
- Create: `plugins/agent/agent_backend/application/`
- Create: `plugins/agent/agent_backend/capabilities/`
- Create: `plugins/agent/agent_backend/infrastructure/`
- Create: `backend/db/migrations/domains/agent/0001_agent.sql`
- Create: `plugins/agent/agent_backend/ai_assistant/catalog_tools.py`
- Modify: `plugins/agent/agent_backend/ai_assistant/tool_registry.py`
- Modify: `plugins/agent/agent_backend/ai_assistant/tool_executor.py`
- Delete after parity: `plugins/agent/agent_backend/ai_assistant/tool_handlers/`
- Delete after parity: `backend/ai_assistant/tool_registry.py`
- Delete after parity: `backend/ai_assistant/tool_handlers/`
- Create: `plugins/agent/tests/test_agent_provider.py`
- Create: `plugins/agent/tests/test_catalog_tool_e2e.py`

**Interfaces:**
- Consumes: Catalog Descriptor bundles, Gateway, Base Approval and all exposed domain Capabilities.
- Produces: Definition, Flow, Skill, Session, Run, Memory and Trace Capabilities plus `tool_name_for(capability_id: str, major_version: int) -> str` and deterministic Catalog-generated Agent tools.

- [ ] **Step 1: Write failing tool-generation and no-import tests**

```python
def test_agent_tools_equal_catalog_exposure(tool_registry, catalog):
    expected = {
        tool_name_for(d.id, d.major_version)
        for d in catalog.descriptors
        if d.exposure.agent
    }
    assert set(tool_registry.names()) == expected

def test_agent_has_no_business_domain_imports(import_graph):
    assert import_graph.for_domain("agent").internal_cross_domain == set()
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest plugins/agent/tests backend/tests/test_agent_consumer_catalog.py backend/tests/test_agent_data_boundaries.py -q`

Expected: FAIL while handwritten tools and Agent internal imports remain.

- [ ] **Step 3: Implement Agent aggregates and official Provider**

Persist Agent state only in `ai00_agent`. Generate tool name, description, input schema, risk, approval and output projection from the pinned Catalog release. Tool execution always constructs a Gateway envelope with Agent/Run/Session/Tenant/Subject/Trace context.

`tool_name_for` returns `cap__{capability_id with each dot replaced by two underscores}__v{major_version}` and rejects names longer than 128 characters. The reverse mapping is stored with the generated tool record; execution never infers a Capability ID from arbitrary model text.

- [ ] **Step 4: Implement approval cancellation and delete handlers**

Before `system.job.cancel` completes a Run cancellation, cancel every pending ApprovalRequest with that Run as subject. Replace each legacy business handler with Catalog execution, prove parity, then delete the handler directory and raw user-token forwarding.

- [ ] **Step 5: Run Agent E2E and finalize**

Run: `python -m pytest plugins/agent/tests backend/tests/test_agent_consumer_catalog.py backend/tests/test_agent_capability_adapters.py backend/tests/test_agent_domain_clients.py backend/tests/test_agent_flow_boundary.py -q`

Expected: PASS and Agent internal-import debt is zero. Commit `feat: complete agent domain and catalog tools`, then freeze central artifacts separately.

### Task 15: Deliver the Production Asynchronous Sharing Path

**Files:**
- Create: `backend/capability_v2/event_transport.py`
- Create: `backend/base/inbox.py`
- Modify: `backend/capability_v2/domain_events.py`
- Modify: `backend/capability_v2/official_domains.json`
- Modify: `backend/governance/capability_v2_production_paths.json`
- Create: `backend/tests/test_production_domain_event_path.py`
- Modify: `backend/tests/test_domain_event_contracts.py`

**Interfaces:**
- Consumes: `knowledge.document.published.v1` Outbox records and Base event subscription manifest.
- Produces: durable transport, Base Inbox deduplication and Base search/change-impact projection update.

- [ ] **Step 1: Write the failing transaction, duplicate and replay tests**

```python
def test_knowledge_publication_reaches_base_once(system):
    event = system.knowledge.publish("doc-1")
    system.transport.deliver(event)
    system.transport.deliver(event)
    assert system.base.inbox.count(event.event_id) == 1
    assert system.base.search_projection.count(subject_ref="doc-1") == 1
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest backend/tests/test_production_domain_event_path.py backend/tests/test_domain_event_contracts.py -q`

Expected: FAIL because official subscriptions are empty and no production Inbox handler is registered.

- [ ] **Step 3: Implement durable delivery**

Poll committed Knowledge Outbox rows, publish a versioned envelope, and mark delivery without sharing Knowledge transactions. Base inserts Inbox event ID and updates its local projection in one Base transaction. Unsupported versions fail explicitly; retry is bounded and failed events remain auditable/replayable.

- [ ] **Step 4: Register the exact subscription**

Add only the Base subscription to `knowledge.document.published` major version 1. Assert Producer and Consumer manifests match the event schema and handler. Do not add empty or speculative subscriptions.

Register path ID `knowledge-publication-base-projection` with producer `knowledge`, consumer `base`, event contract `knowledge.document.published.v1`, production modules `backend.capability_v2.event_transport` and `backend.base.inbox`, and E2E node `backend/tests/test_production_domain_event_path.py::test_knowledge_publication_reaches_base_once`.

- [ ] **Step 5: Run failure-recovery tests and commit**

Run: `python -m pytest backend/tests/test_production_domain_event_path.py backend/tests/test_domain_event_contracts.py backend/tests/acceptance/test_failure_recovery.py -q`

Expected: PASS for first delivery, duplicate delivery, transient failure, replay and unsupported version. Commit code as `feat: deliver knowledge publication events`, then freeze the manifest separately.

### Task 16: Plan 15 — Cut Plugin, Agent and Remaining Consumers to Gateway

**Files:**
- Modify: `backend/routers/plugin_marketplace.py`
- Modify: `backend/routers/agent_capabilities.py`
- Delete after parity: `backend/ai_assistant/tool_registry.py`
- Delete after parity: `backend/ai_assistant/tool_handlers/`
- Modify: `backend/routers/`
- Modify: `backend/tests/test_capability_consumer_e2e.py`
- Modify: `backend/tests/test_no_registry_consumer_bypass.py`
- Modify: `backend/tests/acceptance/test_consumer_parity.py`
- Delete: `backend/capability_v2/v1_adapter.py`

**Interfaces:**
- Consumes: final Catalog release and all eleven official Providers.
- Produces: one consumer path for Web, REST, Plugin, Agent, MCP and Local Runtime; no compatibility business implementation.

- [ ] **Step 1: Expand the failing bypass scanner**

```python
def test_consumers_have_no_business_bypass(repository):
    violations = scan_consumer_bypasses(repository)
    assert violations == []
```

The scanner must reject consumer SQL, concrete Provider/Service/Repository imports, handwritten Agent business tools, V1 adapter calls and REST compatibility handlers containing business logic.

- [ ] **Step 2: Run consumer suites and record exact bypasses**

Run: `python -m pytest backend/tests/test_no_registry_consumer_bypass.py backend/tests/test_capability_consumer_e2e.py backend/tests/acceptance/test_consumer_parity.py -q`

Expected: FAIL with the exact remaining files and symbols.

- [ ] **Step 3: Cut every consumer to the pinned Catalog/Gateway path**

REST adapters perform protocol conversion only. Web SDK, Plugin SDK, Agent tools, MCP tools and Local Runtime contracts come from the same Catalog release. Remove direct Registry/Provider lookups and implicit latest-version fallback.

- [ ] **Step 4: Run real Plugin and Agent E2E**

Exercise discover, permitted invocation, denied invocation, approval-required invocation, timeout/error mapping and audit correlation. Assert the same Capability ID/major/Provider/output contract for both consumers where exposure overlaps.

- [ ] **Step 5: Delete obsolete paths and run parity tests**

Delete V1 adapter, legacy token forwarding, compatibility business handlers, old Capability aliases and unreachable routers only after the E2E proof passes.

Run: `python -m pytest backend/tests/test_capability_v1_retirement.py backend/tests/test_no_registry_consumer_bypass.py backend/tests/test_capability_consumer_e2e.py backend/tests/acceptance/test_consumer_parity.py -q`

Expected: PASS. Commit `refactor: cut all consumers to capability gateway`.

### Task 17: Burn Boundary Debt to Zero and Produce RC Evidence

**Files:**
- Modify: `backend/governance/boundary_baseline.json`
- Modify: `backend/governance/domain-database-ownership.json`
- Modify: `backend/capability_v2/official_domains.json`
- Modify: generated Catalog, docs and acceptance manifests
- Create: `docs/acceptance/capability-v2-three-goal-rc.json`

**Interfaces:**
- Consumes: completed Plans 02–15, eleven databases, final Catalog and all consumer/provider artifacts.
- Produces: strict `CompletionReport.complete == true` and reproducible RC report.

- [ ] **Step 1: Recompute rather than hand-edit the boundary baseline**

Run: `python backend/scripts/audit_domain_boundaries.py --json`

Expected: generated findings contain zero `cross_domain_sql` and zero `internal_import`. If findings remain, return them to the owning domain task; do not add waivers or ignore rules.

After the JSON output proves zero current violations, run `python backend/scripts/audit_domain_boundaries.py --write-baseline` and verify `boundary_baseline.json` contains an empty `violations` array.

- [ ] **Step 2: Prove real database grants**

For each of the eleven runtime credentials, run owner-table CRUD through its Provider and attempt one read plus one write against every other domain database. Owner operations must pass; all 110 cross-domain credential pairs must be denied by the database.

Run: `python -m pytest backend/tests/test_domain_database_config.py backend/tests/test_domain_migration_runner.py backend/tests/test_domain_independence_v2.py -q`

Expected: PASS against the RC database environment.

- [ ] **Step 3: Freeze all generated artifacts on current HEAD**

```powershell
$integrationHead = git rev-parse HEAD
$manifestDigest = "sha256:" + (Get-FileHash backend/capability_v2/official_domains.json -Algorithm SHA256).Hash.ToLowerInvariant()
python backend/scripts/freeze_official_domains.py --expected-head $integrationHead --expected-manifest-sha256 $manifestDigest
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/build_user_function_registry.py --strict
python backend/scripts/check_domain_dependencies.py
```

Expected: every command exits 0 with no drift.

- [ ] **Step 4: Run the complete test suite**

Run: `python -m pytest -q`

Expected: PASS with zero failed, skipped or xfailed tests in mandatory Capability V2 and RC suites.

- [ ] **Step 5: Run strict release-candidate acceptance**

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode release-candidate --strict --report docs/acceptance/capability-v2-three-goal-rc.json`

Expected: status `pass`; all declared cases validated; failed 0; skipped 0; eleven independent domains; Plugin/Agent Gateway-only true; synchronous paths at least 1; asynchronous paths at least 1; boundary and bypass counts 0.

- [ ] **Step 6: Validate the report is reproducible**

Confirm the report records Git commit, Catalog release/hash, DomainManifest digest, all migration versions, environment identity and report ID. Re-run the completion CLI against the report inputs.

Run: `python backend/scripts/check_capability_v2_completion.py --mode strict --report docs/acceptance/capability-v2-three-goal-rc.json`

Expected: exit 0 and `complete: true`.

- [ ] **Step 7: Commit the final freeze and RC evidence**

```powershell
git add -- backend/governance backend/capability_v2/official_domains.json docs/acceptance/capability-v2-three-goal-rc.json
git commit -m "chore: certify capability v2 three-goal release candidate"
```

## Execution Checkpoints

Stop for architecture review after Tasks 2, 4, 8, 14 and 17. At every checkpoint run Catalog drift, strict registry validation, domain dependency checks, the current completion progress report and the full affected-domain test set. A checkpoint fails if it introduces a catch-all Capability, consumer-specific business service, implicit Tenant fallback, shared database credential or second Catalog source.

## Final Completion Statement

Do not report completion before Task 17 produces `complete: true`. Foundation tests, an offline acceptance pass, a populated Catalog or a partially reduced debt baseline are progress evidence only. The final statement must cite the RC report and separately state evidence for: Plugin/Agent governed consumption, 11/11 independent domains, synchronous sharing, asynchronous sharing and zero boundary debt.
