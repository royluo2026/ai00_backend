# Capability Governance Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a test-only Capability Governance Center that assigns stable snowflake identities, scans and relates all product Capability implementations, detects cross-domain defects, exposes governed query and analysis operations to agents, supports reviewed release governance, and proves that no governance test component enters production artifacts.

**Architecture:** Code Descriptors and the Product Catalog remain authoritative. A test-only Base-owned control plane produces immutable snapshots and normalized projections, then deterministic rules, optional AI advisory analysis, tests, review workflows, and a fail-closed release gate consume those snapshots. Test loads a separate Governance Catalog Extension beside the Product Catalog; production loads the Product Catalog only and validates a signed attestation.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, PyMySQL, OceanBase CE 4.3.5.1 in MySQL 5.7 compatibility mode, Vanilla JavaScript, jsdom, Vite 4, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-capability-governance-center-design.md`

## Global Constraints

- Work in `E:/Projects/ai00_v3/.worktrees/capability-v2-implementation` for backend and deployed `dist` changes and `E:/Projects/ai00/workmanship-web` for frontend source; do not create another worktree.
- Preserve all unrelated dirty files. Every commit in this plan stages exact paths only.
- Do not push, merge, or modify the legacy service without explicit authorization.
- Do not edit or delete Capability contracts through the governance database or UI.
- Code Descriptor plus Product Catalog Release is the sole contract authority.
- All governance primary identities use `backend.platform_sdk.ids.next_gid()` and are transported to JavaScript/JSON as decimal strings.
- Product Catalog and Governance Catalog Extension remain separate; UI counts and release reports must distinguish them.
- Full governance packages, UI, migrations, Provider, routes, fixtures, and Catalog Extension are test-only and must be physically absent from production artifacts.
- Governance SQL must pass `assert_oceanbase_ddl_policy`; use `LONGTEXT` for canonical JSON payloads and do not rely on storage-engine clauses or JSON-column indexing.
- Scanners accept repository-relative allowlisted roots only; no arbitrary path, shell, SQL, environment-file, browser-profile, DBeaver, SSH, or user-directory access.
- AI output is advisory only and must be redacted, hash-bound, and human/deterministically confirmed.
- Frequent health probes are read-only. Real writes and full OceanBase E2E run explicitly before formal release.
- Runtime governance-account access is exact table-level SELECT/INSERT/UPDATE; ordinary hard DELETE and DDL are forbidden.
- Use TDD for every task. Do not turn a failing unrelated test into an expected failure or skip.

---

## File and Responsibility Map

### Backend core changes

- `backend/utils/gid.py` — deployment-assigned snowflake machine ID and collision-safe generator initialization.
- `backend/config.py` — test-governance profile settings without secrets in repr/logs.
- `backend/capability_v2/bootstrap.py` — optional test extension registration; product path remains unchanged.
- `backend/capability_v2/catalog_overlay.py` — collision-checked Product + Governance Catalog composition.
- `backend/routers/deps.py` — four governance permissions and explicit grant projection.
- `backend/scripts/check_frontend_deployment.py` — deployed test-governance asset checks.

### Test-only backend package

- `backend/capability_governance_test/config.py` — fail-closed profile and allowlists.
- `backend/capability_governance_test/contracts.py` — governance Capability specs and schemas.
- `backend/capability_governance_test/provider.py` — Base-owned registration and handler boundary.
- `backend/capability_governance_test/models.py` — immutable domain records and query types.
- `backend/capability_governance_test/store.py` — memory and OceanBase persistence ports.
- `backend/capability_governance_test/identity_projection.py` — stable logical/Major GID projection.
- `backend/capability_governance_test/scanner.py` — bounded repository/registry scanner.
- `backend/capability_governance_test/graph.py` — implementation nodes, bindings, and relations.
- `backend/capability_governance_test/fingerprint.py` — canonical Finding and Snapshot hashes.
- `backend/capability_governance_test/rules.py` — deterministic release-authoritative checks.
- `backend/capability_governance_test/analysis.py` — bounded candidate analysis orchestration.
- `backend/capability_governance_test/evidence.py` — evidence freshness and coverage.
- `backend/capability_governance_test/health.py` — healthy/degraded/broken/unverified/stale calculation.
- `backend/capability_governance_test/test_runner.py` — fast and release-E2E profiles.
- `backend/capability_governance_test/workflow.py` — Proposal, Review, Waiver, and stale transitions.
- `backend/capability_governance_test/release_gate.py` — pinned fail-closed evaluation and attestation.
- `backend/capability_governance_test/retention.py` — bounded technical-detail retention planning.
- `backend/capability_governance_test/audit.py` — append-only audit events.
- `backend/capability_governance_test/redaction.py` — field and text redaction.
- `backend/capability_governance_test/ai_advisory.py` — governed Agent-domain advisory port.
- `backend/capability_governance_test/prompting.py` — evidence-bound repair prompt.
- `backend/capability_governance_test/service.py` — application service used by all handlers.
- `backend/capability_governance_test/worker.py` — leased Analysis/Test worker.

### Test-only migrations and generated governance artifacts

- `backend/db/migrations/test_governance/0001_identity_snapshot_graph.sql`
- `backend/db/migrations/test_governance/0002_analysis_evidence_health.sql`
- `backend/db/migrations/test_governance/0003_workflow_release_audit.sql`
- `backend/scripts/migrate_capability_governance_test.py`
- `backend/scripts/generate_capability_governance_grants.py`
- `backend/scripts/build_capability_governance_catalog.py`
- `backend/scripts/run_capability_governance_scan.py`
- `backend/scripts/run_capability_governance_release_acceptance.py`
- `backend/scripts/check_production_governance_exclusion.py`
- `backend/scripts/build_capability_v2_production_artifact.py`
- `docs/governance/test-extension/capability-governance-catalog-release.json`
- `docs/governance/test-extension/production-artifact-allowlist.json`

### Frontend source

- `web/admin/capability_governance/index.html` — test-only shell.
- `web/admin/capability_governance/governance_api.js` — Gateway API adapter.
- `web/admin/capability_governance/governance_model.js` — pure state, filters, and permissions.
- `web/admin/capability_governance/governance_controller.js` — DOM and actions.
- `web/admin/capability_governance/governance.css` — high-contrast responsive UI.
- `web/admin/capability_governance/governance_model.test.js` — jsdom-independent model tests.
- `web/admin/capability_governance/governance_controller.test.js` — jsdom interaction tests.
- `web/admin_hub/index.html` — test-only navigation entry.
- `web/tests/run_tests.js` — invokes focused governance frontend tests.
- `vite.config.js` — explicit `test-governance` versus `production` build profiles.
- `scripts/test_capability_governance_build_profiles.js` — physical-exclusion assertions.

---

### Task 1: Harden snowflake identity configuration

**Files:**
- Modify: `backend/utils/gid.py`
- Modify: `backend/config.py`
- Create: `backend/capability_governance_test/__init__.py`
- Create: `backend/capability_governance_test/config.py`
- Create: `backend/tests/test_capability_governance_gid.py`
- Create: `backend/tests/test_capability_governance_config.py`

**Interfaces:**
- Consumes: process environment and existing `SnowflakeGID.next_id()`.
- Produces: `machine_id_from_environment(environ: Mapping[str, str]) -> int`, `configure_gid_generator(machine_id: int) -> SnowflakeGID`, and `GovernanceSettings.from_environ(environ) -> GovernanceSettings`.

- [ ] **Step 1: Write failing machine-ID and transport tests**

```python
def test_formal_governance_profile_requires_machine_id():
    with pytest.raises(RuntimeError, match="AI00_GID_MACHINE_ID"):
        machine_id_from_environment({"AI00_DEPLOYMENT_PROFILE": "test-governance"})

def test_gid_is_safe_signed_bigint_and_serialized_as_string():
    generator = SnowflakeGID(machine_id=41)
    value = generator.next_id()
    assert 0 < value < 2**63
    assert gid_to_json(value) == str(value)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest backend/tests/test_capability_governance_gid.py backend/tests/test_capability_governance_config.py -q`

Expected: FAIL because environment-driven configuration and `GovernanceSettings` do not exist.

- [ ] **Step 3: Implement explicit generator and governance settings**

```python
def machine_id_from_environment(environ: Mapping[str, str]) -> int:
    profile = str(environ.get("AI00_DEPLOYMENT_PROFILE", "local")).strip()
    raw = str(environ.get("AI00_GID_MACHINE_ID", "")).strip()
    if not raw and profile in {"test-governance", "production"}:
        raise RuntimeError("AI00_GID_MACHINE_ID is required")
    machine_id = int(raw or "1")
    if not 0 <= machine_id <= SnowflakeGID.MAX_MACHINE_ID:
        raise RuntimeError("AI00_GID_MACHINE_ID must be in 0..1023")
    return machine_id

def gid_to_json(value: int) -> str:
    if not 0 < value < 2**63:
        raise ValueError("gid_out_of_signed_bigint_range")
    return str(value)
```

Remove singleton behavior from ordinary `SnowflakeGID(...)` instances so tests and explicitly configured generators cannot silently reuse a generator created with a different machine ID. Keep one module-level configured generator behind `next_gid`. `GovernanceSettings` must require `AI00_DEPLOYMENT_PROFILE=test-governance`, resolve the repository root internally, expose immutable allowlisted relative roots, and redact all database-like values from `repr`.

- [ ] **Step 4: Run focused and existing GID tests**

Run: `python -m pytest backend/tests/test_capability_governance_gid.py backend/tests/test_capability_governance_config.py backend/tests/test_runtime_settings.py -q`

Expected: PASS, with the default local generator behavior preserved and formal profiles fail-closed.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/utils/gid.py backend/config.py backend/capability_governance_test/__init__.py backend/capability_governance_test/config.py backend/tests/test_capability_governance_gid.py backend/tests/test_capability_governance_config.py
git commit -m "feat: harden governance snowflake identities"
```

### Task 2: Add the separate Governance Catalog Extension

**Files:**
- Create: `backend/capability_v2/catalog_overlay.py`
- Create: `backend/capability_governance_test/contracts.py`
- Create: `backend/capability_governance_test/provider.py`
- Modify: `backend/capability_v2/bootstrap.py`
- Create: `backend/scripts/build_capability_governance_catalog.py`
- Create: `backend/tests/test_capability_governance_catalog.py`
- Create: `backend/tests/test_capability_catalog_overlay.py`
- Create: `docs/governance/test-extension/capability-governance-catalog-release.json`

**Interfaces:**
- Consumes: `CatalogRelease`, `CapabilityRegistry`, Base `register_capability()`.
- Produces: `compose_catalogs(product: CatalogRelease, extension: CatalogRelease) -> EffectiveCatalog`, `register_governance_capabilities(registry, service_port)`, and 14 exact test-only descriptors.

- [ ] **Step 1: Write failing collision and separation tests**

```python
def test_overlay_rejects_duplicate_capability_major():
    with pytest.raises(ValueError, match="catalog_overlay_capability_collision"):
        compose_catalogs(product_release("base.x", 1), extension_release("base.x", 1))

def test_product_registry_is_unchanged_without_test_extension():
    product = build_capability_registry(ROOT)
    test = build_capability_registry(ROOT, include_test_governance=True)
    assert ("base.capability_registry.search", 1) not in product.keys()
    assert ("base.capability_registry.search", 1) in test.keys()
```

- [ ] **Step 2: Run the Catalog tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_catalog.py backend/tests/test_capability_catalog_overlay.py -q`

Expected: FAIL because overlay and governance descriptors are absent.

- [ ] **Step 3: Define the exact extension contracts**

Register these read/analyze operations:

```python
READ_IDS = (
    "base.capability_registry.search",
    "base.capability_registry.get",
    "base.capability_graph.get",
    "base.capability_finding.search",
    "base.capability_analysis.get",
)
ANALYZE_IDS = (
    "base.capability_analysis.run",
    "base.capability_repair_prompt.generate",
)
GOVERN_IDS = (
    "base.capability_scan.run",
    "base.capability_test.run",
    "base.capability_proposal.submit",
    "base.capability_review.decide",
    "base.capability_waiver.grant",
    "base.capability_waiver.revoke",
)
RELEASE_IDS = ("base.capability_release_gate.evaluate",)
```

Every input schema must set `additionalProperties: false`, every collection must have a declared maximum, every GID field must be a decimal-string schema, and write operations must require idempotency and governed confirmation.

- [ ] **Step 4: Implement collision-checked overlay and optional registration**

```python
@dataclass(frozen=True)
class EffectiveCatalog:
    product: CatalogRelease
    extension: CatalogRelease
    effective: CatalogRelease

def compose_catalogs(product: CatalogRelease, extension: CatalogRelease) -> EffectiveCatalog:
    product_keys = {(d.id, d.major_version) for d in product.descriptors}
    extension_keys = {(d.id, d.major_version) for d in extension.descriptors}
    if product_keys & extension_keys:
        raise ValueError("catalog_overlay_capability_collision")
    if {p.plugin_id for p in product.provider_artifacts} & {p.plugin_id for p in extension.provider_artifacts}:
        raise ValueError("catalog_overlay_provider_collision")
    return EffectiveCatalog(product, extension, build_release(
        (*product.descriptors, *extension.descriptors),
        (*product.provider_artifacts, *extension.provider_artifacts),
    ))
```

`build_capability_registry(..., include_test_governance=False)` must not import the test package on the normal path. The true branch registers the extension after official domains.

- [ ] **Step 5: Generate and verify the extension release**

Run: `python backend/scripts/build_capability_governance_catalog.py --write`

Run: `python backend/scripts/build_capability_governance_catalog.py --check`

Expected: both succeed; the generated extension contains only Base-owned governance descriptors and one test Provider Artifact.

- [ ] **Step 6: Run Catalog regression tests**

Run: `python -m pytest backend/tests/test_capability_governance_catalog.py backend/tests/test_capability_catalog_overlay.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_bootstrap.py -q`

Expected: PASS; normal Product Catalog hash remains unchanged.

- [ ] **Step 7: Commit Task 2**

```bash
git add backend/capability_v2/catalog_overlay.py backend/capability_v2/bootstrap.py backend/capability_governance_test/contracts.py backend/capability_governance_test/provider.py backend/scripts/build_capability_governance_catalog.py backend/tests/test_capability_governance_catalog.py backend/tests/test_capability_catalog_overlay.py docs/governance/test-extension/capability-governance-catalog-release.json
git commit -m "feat: add test governance catalog extension"
```

### Task 3: Create the OceanBase governance schema and test-only migration runner

**Files:**
- Create: `backend/db/migrations/test_governance/0001_identity_snapshot_graph.sql`
- Create: `backend/db/migrations/test_governance/0002_analysis_evidence_health.sql`
- Create: `backend/db/migrations/test_governance/0003_workflow_release_audit.sql`
- Create: `backend/scripts/migrate_capability_governance_test.py`
- Create: `backend/scripts/generate_capability_governance_grants.py`
- Create: `backend/tests/test_capability_governance_migrations.py`
- Modify: `backend/tests/test_oceanbase_compatibility.py`
- Modify: `backend/governance/domain_table_ownership.json`

**Interfaces:**
- Consumes: `split_sql`, `normalize_oceanbase_sql`, `assert_oceanbase_ddl_policy`, `AI00_BASE_DDL_DB_URL` only in an explicit test-governance migration command.
- Produces: the exact 20 governance entity tables from the spec, a separate migration ledger `workmanship_base_capability_governance_migrations`, `migrate(connection) -> tuple[str, ...]`, and an exact table-level runtime GRANT script.

- [ ] **Step 1: Write a failing schema contract test**

```python
EXPECTED_TABLES = {
    "workmanship_base_capability_entries",
    "workmanship_base_capability_versions",
    "workmanship_base_capability_scan_runs",
    "workmanship_base_capability_snapshots",
    "workmanship_base_capability_snapshot_entries",
    "workmanship_base_capability_implementation_nodes",
    "workmanship_base_capability_bindings",
    "workmanship_base_capability_implementation_relations",
    "workmanship_base_capability_evidence",
    "workmanship_base_capability_test_runs",
    "workmanship_base_capability_test_results",
    "workmanship_base_capability_health_rollups",
    "workmanship_base_capability_analysis_runs",
    "workmanship_base_capability_findings",
    "workmanship_base_capability_finding_subjects",
    "workmanship_base_capability_change_proposals",
    "workmanship_base_capability_reviews",
    "workmanship_base_capability_waivers",
    "workmanship_base_capability_release_reports",
    "workmanship_base_capability_audit_events",
}

def test_test_governance_schema_is_complete_and_oceanbase_safe():
    compiled = compile_governance_migrations(ROOT)
    assert set(compiled.tables) == EXPECTED_TABLES
    assert " ENGINE=" not in compiled.normalized_sql.upper()
    assert " JSON " not in compiled.normalized_sql.upper()
```

- [ ] **Step 2: Run migration tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_migrations.py -q`

Expected: FAIL because the migrations and runner do not exist.

- [ ] **Step 3: Write the migrations with exact key rules**

Every entity table uses a signed `BIGINT` snowflake primary key. Use this shape for identity tables and repeat the spec fields exactly for the remaining tables:

```sql
CREATE TABLE workmanship_base_capability_entries (
  capability_gid BIGINT NOT NULL,
  capability_id VARCHAR(128) NOT NULL,
  owner_domain VARCHAR(64) NOT NULL,
  current_major_version INT NOT NULL,
  current_lifecycle_status VARCHAR(32) NOT NULL,
  first_seen_at DATETIME(6) NOT NULL,
  last_seen_at DATETIME(6) NOT NULL,
  row_version BIGINT NOT NULL DEFAULT 1,
  PRIMARY KEY (capability_gid),
  UNIQUE KEY uq_capability_entry_id (capability_id)
);

CREATE TABLE workmanship_base_capability_versions (
  capability_version_gid BIGINT NOT NULL,
  capability_gid BIGINT NOT NULL,
  major_version INT NOT NULL,
  semantic_class VARCHAR(32) NOT NULL,
  business_effect VARCHAR(1000) NOT NULL,
  lifecycle_status VARCHAR(32) NOT NULL,
  first_seen_snapshot_gid BIGINT NULL,
  latest_snapshot_gid BIGINT NULL,
  retired_at DATETIME(6) NULL,
  row_version BIGINT NOT NULL DEFAULT 1,
  PRIMARY KEY (capability_version_gid),
  UNIQUE KEY uq_capability_version (capability_gid, major_version),
  CONSTRAINT fk_capability_version_entry FOREIGN KEY (capability_gid)
    REFERENCES workmanship_base_capability_entries (capability_gid)
);
```

All JSON documents are `LONGTEXT NOT NULL`; all hashes are `VARCHAR(71)`; query indexes cover status, owner domain, snapshot GID, capability-version GID, Finding fingerprint, expiry, and event time. Do not add cascade delete.

- [ ] **Step 4: Implement the profile-locked migration runner**

The script must refuse unless `AI00_DEPLOYMENT_PROFILE=test-governance`, must never print a URL/password, must apply each UTF-8 migration with checksums and an advisory lock, and must support `--check` without DDL.

- [ ] **Step 5: Run static migration and schema tests**

Run: `python -m pytest backend/tests/test_capability_governance_migrations.py backend/tests/test_oceanbase_compatibility.py backend/tests/test_schema_compiler.py -q`

Expected: PASS; Product Catalog schema compilation does not include `test_governance` migrations.

- [ ] **Step 6: Run migration against the authorized test DDL connection**

Run: `python backend/scripts/migrate_capability_governance_test.py --apply`

Expected: three migration IDs applied or already verified, passwords absent from output, and exact table count confirmed.

- [ ] **Step 7: Generate and verify exact runtime grants**

Run: `python backend/scripts/generate_capability_governance_grants.py --principal ai00_test_base --output .runtime/capability-governance-runtime-grants.sql`

Expected: the script contains SELECT/INSERT/UPDATE on the 20 governance entity tables, SELECT on the existing Catalog Release table, no DELETE/DDL/system-table grant, no password, and no wildcard table grant.

- [ ] **Step 8: Commit Task 3**

```bash
git add backend/db/migrations/test_governance backend/scripts/migrate_capability_governance_test.py backend/scripts/generate_capability_governance_grants.py backend/tests/test_capability_governance_migrations.py backend/tests/test_oceanbase_compatibility.py backend/governance/domain_table_ownership.json
git commit -m "feat: add capability governance schema"
```

### Task 4: Implement immutable persistence and stable identity projection

**Files:**
- Create: `backend/capability_governance_test/models.py`
- Create: `backend/capability_governance_test/store.py`
- Create: `backend/capability_governance_test/identity_projection.py`
- Create: `backend/capability_governance_test/fingerprint.py`
- Create: `backend/tests/test_capability_governance_store.py`
- Create: `backend/tests/test_capability_identity_projection.py`

**Interfaces:**
- Consumes: Product/extension descriptors and `next_gid()`.
- Produces: `SnapshotDocument`, `CapabilityProjection`, `GovernanceStore`, `MemoryGovernanceStore`, `SqlGovernanceStore`, and `project_snapshot(store, document) -> SnapshotRecord`.

- [ ] **Step 1: Write failing identity/idempotency tests**

```python
def test_repeat_projection_reuses_logical_and_major_gid():
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    first = project_snapshot(store, snapshot("craft.bop.version.list", 1))
    second = project_snapshot(store, snapshot("craft.bop.version.list", 1))
    assert first.entries[0].capability_gid == second.entries[0].capability_gid
    assert first.entries[0].capability_version_gid == second.entries[0].capability_version_gid

def test_snapshot_is_insert_only():
    store = MemoryGovernanceStore()
    saved = store.save_snapshot(snapshot("base.project.search", 1))
    with pytest.raises(ImmutableRecordError):
        store.replace_snapshot(saved.snapshot_gid, snapshot("base.project.create", 1))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_store.py backend/tests/test_capability_identity_projection.py -q`

Expected: FAIL because model/store interfaces do not exist.

- [ ] **Step 3: Define immutable model contracts**

```python
@dataclass(frozen=True)
class CapabilityProjection:
    capability_gid: int
    capability_version_gid: int
    capability_id: str
    major_version: int
    owner_domain: str
    semantic_class: str
    business_effect: str
    lifecycle_status: str
    descriptor_hash: str

@dataclass(frozen=True)
class SnapshotDocument:
    product_release_id: str
    extension_release_id: str | None
    code_revision: str
    snapshot_hash: str
    capabilities: tuple[ScannedCapability, ...]
    nodes: tuple[ImplementationNode, ...]
    bindings: tuple[CapabilityBinding, ...]
    relations: tuple[ImplementationRelation, ...]
```

All JSON conversion methods return GIDs as strings.

- [ ] **Step 4: Implement transactionally consistent SQL persistence**

`SqlGovernanceStore.import_snapshot()` must:

1. select identities by unique business key;
2. allocate missing logical and Major GIDs;
3. insert the immutable snapshot and entries;
4. insert graph nodes/bindings/relations;
5. update only `latest_snapshot_gid`, lifecycle projection, `last_seen_at`, and `row_version` on mutable projections;
6. commit once or roll back everything.

Use parameterized SQL only. Duplicate-key recovery must re-read and compare identity instead of silently choosing a new GID.

- [ ] **Step 5: Run memory, SQL-mock, and serialization tests**

Run: `python -m pytest backend/tests/test_capability_governance_store.py backend/tests/test_capability_identity_projection.py -q`

Expected: PASS, including concurrent duplicate-key recovery and JavaScript-safe GID strings.

- [ ] **Step 6: Commit Task 4**

```bash
git add backend/capability_governance_test/models.py backend/capability_governance_test/store.py backend/capability_governance_test/identity_projection.py backend/capability_governance_test/fingerprint.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_identity_projection.py
git commit -m "feat: persist immutable capability governance snapshots"
```

### Task 5: Build the bounded scanner and implementation graph

**Files:**
- Create: `backend/capability_governance_test/scanner.py`
- Create: `backend/capability_governance_test/graph.py`
- Create: `backend/scripts/run_capability_governance_scan.py`
- Create: `backend/tests/test_capability_governance_scanner.py`
- Create: `backend/tests/fixtures/capability_governance_scan/valid/`
- Create: `backend/tests/fixtures/capability_governance_scan/invalid_provider/`

**Interfaces:**
- Consumes: exact Registry snapshot, Product Catalog, optional Governance Extension, official-domain manifests, and repository root from trusted settings.
- Produces: `GovernanceScanner.scan(code_revision: str) -> SnapshotDocument` and deterministic implementation nodes/relations.

- [ ] **Step 1: Write failing scanner-boundary and graph tests**

```python
def test_scanner_rejects_caller_supplied_absolute_path(settings):
    with pytest.raises(ScanPolicyError, match="scan_path_not_allowlisted"):
        GovernanceScanner(settings).scan_path(Path("C:/Users"))

def test_graph_links_write_from_gateway_to_table(valid_fixture):
    result = scan_fixture(valid_fixture)
    assert result.has_path(
        "craft.bop.factory.create@1",
        ["gateway", "provider", "domain_port", "repository", "database_table"],
    )
```

- [ ] **Step 2: Run scanner tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_scanner.py -q`

Expected: FAIL because scanner and graph builder are absent.

- [ ] **Step 3: Implement allowlisted parsers**

Use Python AST and existing structured manifests; never import scanned modules except the already constructed Registry. Recognize exact node types from the spec and canonicalize keys as:

```python
def node_key(node_type: str, owner: str, path: str, symbol: str = "") -> str:
    return f"{node_type}:{owner}:{PurePosixPath(path)}:{symbol}"
```

Route and SQL table discovery must be conservative: unresolved dynamic expressions become explicit `unresolved_binding` evidence, not guessed edges.

- [ ] **Step 4: Implement deterministic snapshot hashing**

Sort descriptors by `(id, major)`, nodes by canonical key, and relations by `(from_key, type, to_key)`. Hash canonical UTF-8 JSON with SHA-256. Timestamps and generated GIDs are excluded from the snapshot hash.

- [ ] **Step 5: Run focused scanner and domain-boundary tests**

Run: `python -m pytest backend/tests/test_capability_governance_scanner.py backend/tests/test_official_domain_entrypoints.py backend/tests/test_domain_table_ownership.py backend/tests/test_no_registry_consumer_bypass.py -q`

Expected: PASS.

- [ ] **Step 6: Run an offline full-repository scan**

Run: `python backend/scripts/run_capability_governance_scan.py --offline --output .runtime/capability-governance-scan.json`

Expected: one immutable report with 11 official domains, 267 Product descriptors for the pinned baseline, separate extension count, no secret values, and no arbitrary-path warnings.

- [ ] **Step 7: Commit Task 5**

```bash
git add backend/capability_governance_test/scanner.py backend/capability_governance_test/graph.py backend/scripts/run_capability_governance_scan.py backend/tests/test_capability_governance_scanner.py backend/tests/fixtures/capability_governance_scan
git commit -m "feat: scan capability implementation graph"
```

### Task 6: Implement deterministic Findings and bounded cross-domain analysis

**Files:**
- Create: `backend/capability_governance_test/rules.py`
- Create: `backend/capability_governance_test/analysis.py`
- Create: `backend/tests/test_capability_governance_rules.py`
- Create: `backend/tests/test_capability_cross_domain_analysis.py`
- Create: `backend/tests/fixtures/capability_governance_analysis/cases.json`

**Interfaces:**
- Consumes: immutable `SnapshotDocument` and graph.
- Produces: `FindingCandidate`, `AnalysisRequest`, `AnalysisResult`, `run_deterministic_analysis(snapshot, request)`, and stable `finding_fingerprint()`.

- [ ] **Step 1: Write failing rule tests for the historical defect class**

```python
def test_strong_write_without_transactional_provider_blocks_release():
    findings = analyze(snapshot_with_strong_write(transactional=False))
    finding = require_finding(findings, "transaction_participant_missing")
    assert finding.severity == "blocking"

def test_cross_domain_conflict_has_multiple_subjects():
    findings = analyze(snapshot_with_conflicting_searches())
    finding = require_finding(findings, "cross_domain_conflict")
    assert {s.capability_id for s in finding.subjects} == {
        "craft.resource.search", "factory.resource.search"
    }
```

- [ ] **Step 2: Run analysis tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_rules.py backend/tests/test_capability_cross_domain_analysis.py -q`

Expected: FAIL because rule engine and Finding contracts are absent.

- [ ] **Step 3: Implement the release-authoritative rule set**

Implement named pure rules for:

```python
RULES = (
    descriptor_without_provider,
    provider_without_descriptor,
    exposure_without_capability,
    strong_write_without_transactional_provider,
    repository_table_migration_mismatch,
    permission_policy_mismatch,
    confirmation_policy_mismatch,
    catalog_schema_drift,
    required_test_missing,
    stale_evidence,
    lifecycle_incompatibility,
    production_governance_artifact_present,
)
```

Each returns evidence GIDs/keys, subject roles, severity, stable code, and remediation boundary.

- [ ] **Step 4: Implement bounded semantic candidate generation**

Block by normalized business object, operation family, schema signature, side-effect level, consistency policy, and permission family before calculating similarity. Enforce `max_candidates <= 5000` and `max_subjects_per_finding <= 20`; return `analysis_budget_exceeded` instead of truncating silently.

- [ ] **Step 5: Run rule, graph, and performance tests**

Run: `python -m pytest backend/tests/test_capability_governance_rules.py backend/tests/test_capability_cross_domain_analysis.py -q`

Expected: PASS; the 267-descriptor fixture finishes deterministic candidate generation within the test's fixed operation-count budget rather than a wall-clock assertion.

- [ ] **Step 6: Commit Task 6**

```bash
git add backend/capability_governance_test/rules.py backend/capability_governance_test/analysis.py backend/tests/test_capability_governance_rules.py backend/tests/test_capability_cross_domain_analysis.py backend/tests/fixtures/capability_governance_analysis/cases.json
git commit -m "feat: detect capability governance findings"
```

### Task 7: Add evidence, health, and explicit release-E2E profiles

**Files:**
- Create: `backend/capability_governance_test/evidence.py`
- Create: `backend/capability_governance_test/health.py`
- Create: `backend/capability_governance_test/test_runner.py`
- Create: `backend/tests/test_capability_governance_evidence.py`
- Create: `backend/tests/test_capability_governance_health.py`
- Create: `backend/tests/test_capability_governance_test_profiles.py`

**Interfaces:**
- Consumes: Snapshot, Findings, registered test cases, and redacted runtime results.
- Produces: `EvidenceRecord`, `HealthRollup`, `TestProfile`, `run_fast_profile()`, `run_release_e2e_profile()`, and `compute_health()`.

- [ ] **Step 1: Write failing health truthfulness tests**

```python
def test_contract_only_evidence_is_unverified():
    result = compute_health(required={"contract", "gateway"}, evidence={passed("contract")})
    assert result.status == "unverified"

def test_changed_provider_hash_makes_runtime_evidence_stale():
    result = compute_health(snapshot_hash="new", evidence={passed("runtime_e2e", source_hash="old")})
    assert result.status == "stale"

def test_periodic_profile_refuses_write_cases():
    with pytest.raises(TestPolicyError, match="write_probe_forbidden"):
        run_fast_profile([write_case()])
```

- [ ] **Step 2: Run evidence tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_evidence.py backend/tests/test_capability_governance_health.py backend/tests/test_capability_governance_test_profiles.py -q`

Expected: FAIL because evidence and health services are absent.

- [ ] **Step 3: Implement the seven evidence levels and five health states**

```python
EVIDENCE_LEVELS = (
    "contract", "provider", "repository_codec", "gateway",
    "technical_exposure", "runtime_probe", "runtime_e2e",
)
HEALTH_STATES = ("healthy", "degraded", "broken", "unverified", "stale")
```

Health calculation must be deterministic and include evidence age, dependency hashes, required levels, blocking findings, and latest test status.

- [ ] **Step 4: Implement profile policy**

Fast profile accepts only read operations and static checks. Release E2E requires explicit `release_candidate_gid`, isolated fixture IDs, exact cleanup plan, and a caller with `system.capability.release`. It records failures but never downgrades them to skipped.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest backend/tests/test_capability_governance_evidence.py backend/tests/test_capability_governance_health.py backend/tests/test_capability_governance_test_profiles.py backend/tests/test_capability_evidence_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 7**

```bash
git add backend/capability_governance_test/evidence.py backend/capability_governance_test/health.py backend/capability_governance_test/test_runner.py backend/tests/test_capability_governance_evidence.py backend/tests/test_capability_governance_health.py backend/tests/test_capability_governance_test_profiles.py
git commit -m "feat: evaluate capability evidence and health"
```

### Task 8: Expose governed UI and Agent interfaces with explicit permissions

**Files:**
- Create: `backend/capability_governance_test/service.py`
- Create: `backend/capability_governance_test/worker.py`
- Modify: `backend/capability_governance_test/provider.py`
- Modify: `backend/routers/deps.py`
- Create: `backend/tests/test_capability_governance_provider.py`
- Create: `backend/tests/test_capability_governance_permissions.py`
- Create: `backend/tests/test_capability_governance_worker.py`
- Modify: `backend/tests/test_agent_consumer_catalog.py`

**Interfaces:**
- Consumes: `GovernanceStore`, scanner, analysis, evidence, and Gateway identity.
- Produces: `CapabilityGovernanceService` methods matching all Task 2 handlers and delegated Agent access.

- [ ] **Step 1: Write failing permission and bounded-output tests**

```python
def test_analyst_can_search_but_cannot_review(gateway, analyst_identity):
    assert invoke(gateway, analyst_identity, "base.capability_registry.search", {"limit": 20}).ok
    denied = invoke(gateway, analyst_identity, "base.capability_review.decide", review_payload())
    assert denied.error.code == "permission_denied"

def test_graph_requires_depth_and_node_limit(service):
    with pytest.raises(CapabilityBusinessError, match="invalid_input"):
        service.graph_get({"capability_version_gid": "100"}, context())
```

- [ ] **Step 2: Run provider tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_permissions.py -q`

Expected: FAIL because service bindings and permissions do not exist.

- [ ] **Step 3: Add explicit permission grants**

Grant mapping:

```python
_GRANT_PERMISSIONS.update({
    "capability_analyst": {"system.capability.read", "system.capability.analyze"},
    "capability_governor": {"system.capability.read", "system.capability.analyze", "system.capability.govern"},
    "capability_release_manager": {
        "system.capability.read", "system.capability.analyze",
        "system.capability.govern", "system.capability.release",
    },
})
```

`super_admin` receives all four in the test-governance profile. Other roles do not receive cross-domain governance implicitly. Agent/MCP access still requires a valid delegation with exact Capability scopes.

- [ ] **Step 4: Implement service handlers**

Search must cap `limit` at 200. Graph must require `max_depth <= 4` and `max_nodes <= 500`. Analysis must pin `snapshot_gid`. Every mutating operation requires idempotency and current `row_version` or `expected_resource_version` where applicable.

- [ ] **Step 5: Implement the leased Analysis and Test worker**

The worker must acquire a database-backed lease by `analysis_run_gid` or `test_run_gid`, renew it while active, make completion idempotent, and return an expired lease to `queued`. Two workers must never execute the same live run concurrently.

- [ ] **Step 6: Run Gateway, worker, catalog, and delegation tests**

Run: `python -m pytest backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_permissions.py backend/tests/test_capability_governance_worker.py backend/tests/test_agent_consumer_catalog.py backend/tests/test_capability_gateway_pipeline.py backend/tests/test_mcp_gateway_identity.py -q`

Expected: PASS; agent sees only delegated governance operations.

- [ ] **Step 7: Commit Task 8**

```bash
git add backend/capability_governance_test/service.py backend/capability_governance_test/worker.py backend/capability_governance_test/provider.py backend/routers/deps.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_permissions.py backend/tests/test_capability_governance_worker.py backend/tests/test_agent_consumer_catalog.py
git commit -m "feat: expose capability governance operations"
```

### Task 9: Implement Proposal, Review, Waiver, Audit, and fail-closed release gate

**Files:**
- Create: `backend/capability_governance_test/workflow.py`
- Create: `backend/capability_governance_test/audit.py`
- Create: `backend/capability_governance_test/release_gate.py`
- Create: `backend/capability_governance_test/retention.py`
- Create: `backend/tests/test_capability_governance_workflow.py`
- Create: `backend/tests/test_capability_governance_audit.py`
- Create: `backend/tests/test_capability_governance_release_gate.py`
- Create: `backend/tests/test_capability_governance_retention.py`

**Interfaces:**
- Consumes: snapshot/evidence/test hashes, permissions, expected row version, and idempotency key.
- Produces: `ProposalService`, `WaiverService`, `AuditSink`, `ReleaseGate.evaluate(candidate) -> ReleaseReport`.

- [ ] **Step 1: Write failing stale and fail-closed tests**

```python
def test_code_hash_change_stales_approved_proposal():
    proposal = approved_proposal(base_hash="sha256:a")
    assert refresh_proposal(proposal, current_hash="sha256:b").status == "stale"

def test_release_gate_fails_when_required_runner_is_unavailable():
    report = evaluate(candidate(test_status="unavailable"))
    assert report.conclusion == "fail"
    assert "required_test_unavailable" in report.blockers

def test_waiver_must_expire():
    with pytest.raises(WorkflowError, match="waiver_expiry_required"):
        grant_waiver(expires_at=None)

def test_governance_capability_cannot_self_approve():
    proposal = proposal_for("base.capability_review.decide", submitted_by="agent-1")
    with pytest.raises(WorkflowError, match="independent_reviewer_required"):
        approve(proposal, reviewer_gid="agent-1")
```

- [ ] **Step 2: Run workflow tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_workflow.py backend/tests/test_capability_governance_audit.py backend/tests/test_capability_governance_release_gate.py -q`

Expected: FAIL because workflow/gate services are absent.

- [ ] **Step 3: Implement exact state machines**

Use the Capability, Proposal, and Finding states from the spec. State transitions are table-driven and reject every unlisted edge. Review decisions bind `proposal_gid`, `base_snapshot_gid`, descriptor hash, evidence snapshot, reviewer GID, and decision time.

When a new Snapshot changes a Capability descriptor or governed implementation hash, create or update a `detected` Proposal bound to the old/new hashes. Governance Capability changes require independent Base-owner and platform-release stages; the submitter and AI advisory identity cannot satisfy either independent review automatically.

- [ ] **Step 4: Implement immutable release reports**

```python
@dataclass(frozen=True)
class ReleaseCandidate:
    code_revision: str
    product_catalog_release_id: str
    snapshot_gid: int
    test_run_gid: int

@dataclass(frozen=True)
class ReleaseReport:
    release_report_gid: int
    candidate: ReleaseCandidate
    conclusion: Literal["pass", "fail", "expired"]
    blockers: tuple[str, ...]
    report_hash: str
    signing_key_id: str
    signature: str
```

Sign canonical report bytes with the existing signing primitives and a release-only key loaded from the authorized secret path. Never generate, print, or commit the private key. Any changed pinned input expires a prior pass. Missing data, unavailable dependencies, blocking Findings, expired Waivers, stale evidence, or incomplete approvals fail closed.

- [ ] **Step 5: Verify audit completeness**

Tests must assert one append-only Audit Event for scan, analysis, confirmation/rejection, proposal, review, waiver, test, gate, prompt generation, and Agent invocation; redacted details must not contain values matching password/token/URL secret patterns.

- [ ] **Step 6: Implement and test bounded retention planning**

`plan_retention(now)` may select only expired non-release Snapshot detail, Test Result detail older than 180 days, Health Rollups older than one year, and expired AI summaries. It must never select Entry, Version, Finding history, Proposal, Review, Waiver history, Release Report, or Audit Event. Actual cleanup requires an explicit maintenance command and is not available through runtime Capabilities.

- [ ] **Step 7: Run focused tests**

Run: `python -m pytest backend/tests/test_capability_governance_workflow.py backend/tests/test_capability_governance_audit.py backend/tests/test_capability_governance_release_gate.py backend/tests/test_capability_governance_retention.py -q`

Expected: PASS.

- [ ] **Step 8: Commit Task 9**

```bash
git add backend/capability_governance_test/workflow.py backend/capability_governance_test/audit.py backend/capability_governance_test/release_gate.py backend/capability_governance_test/retention.py backend/tests/test_capability_governance_workflow.py backend/tests/test_capability_governance_audit.py backend/tests/test_capability_governance_release_gate.py backend/tests/test_capability_governance_retention.py
git commit -m "feat: govern capability changes and release gates"
```

### Task 10: Connect the built-in Agent advisory path and repair-prompt generator

**Files:**
- Create: `backend/domain_ports/capability_governance_ai.py`
- Create: `backend/capability_governance_test/redaction.py`
- Create: `backend/capability_governance_test/ai_advisory.py`
- Create: `backend/capability_governance_test/prompting.py`
- Modify: `backend/capability_governance_test/service.py`
- Create: `backend/tests/test_capability_governance_redaction.py`
- Create: `backend/tests/test_capability_governance_ai.py`
- Create: `backend/tests/test_capability_repair_prompt.py`

**Interfaces:**
- Consumes: bounded candidate package and governed `DomainCapabilityClient` path to the Agent domain.
- Produces: `GovernanceAdvisorPort.review(package) -> AdvisoryResult` and `build_repair_prompt(finding, evidence, boundary) -> RedactedPrompt`.

- [ ] **Step 1: Write failing redaction and advisory-authority tests**

```python
def test_redactor_removes_urls_tokens_passwords_and_business_payloads():
    result = redact({"db_url": "mysql://u:p@host/db", "token": "secret", "summary": "safe"})
    assert result == {"db_url": "[REDACTED]", "token": "[REDACTED]", "summary": "safe"}

def test_ai_result_cannot_confirm_finding():
    result = advisory_result(status="confirmed")
    with pytest.raises(AdvisoryContractError, match="candidate_only"):
        validate_advisory(result)
```

- [ ] **Step 2: Run AI tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_redaction.py backend/tests/test_capability_governance_ai.py backend/tests/test_capability_repair_prompt.py -q`

Expected: FAIL because advisory and redaction modules do not exist.

- [ ] **Step 3: Implement a governed Agent-domain port**

The adapter invokes the reviewed Agent domain through `DomainCapabilityClient`, never a raw model HTTP client. The package contains only IDs, business effects, schema summaries, policies, evidence summaries, model policy version, and hashes. Set hard input/output byte limits and a deadline.

- [ ] **Step 4: Implement candidate-only result validation**

```python
class AdvisoryFinding(FrozenModel):
    finding_type: Literal[
        "duplicate", "semantic_overlap", "conflict", "gap",
        "non_atomic_facade", "lifecycle_pair_gap"
    ]
    subject_version_gids: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    evidence_keys: tuple[str, ...]
    recommendation: str
    status: Literal["candidate"] = "candidate"
```

- [ ] **Step 5: Implement repair prompt sections and hashing**

The generated prompt contains exact sections: snapshot identity, Capability identities, observed contract, implementation evidence, Finding, allowed change boundary, forbidden changes, required tests, and acceptance criteria. Store only prompt hash and redacted summary; return prompt text only to an authorized caller.

- [ ] **Step 6: Run advisory, gateway, and audit tests**

Run: `python -m pytest backend/tests/test_capability_governance_redaction.py backend/tests/test_capability_governance_ai.py backend/tests/test_capability_repair_prompt.py backend/tests/test_capability_governance_audit.py -q`

Expected: PASS; no raw secret or arbitrary prompt reaches the Agent port.

- [ ] **Step 7: Commit Task 10**

```bash
git add backend/domain_ports/capability_governance_ai.py backend/capability_governance_test/redaction.py backend/capability_governance_test/ai_advisory.py backend/capability_governance_test/prompting.py backend/capability_governance_test/service.py backend/tests/test_capability_governance_redaction.py backend/tests/test_capability_governance_ai.py backend/tests/test_capability_repair_prompt.py
git commit -m "feat: add governed capability analysis advisor"
```

### Task 11: Build the test-only governance UI in the frontend source repository

**Files:**
- Create: `web/admin/capability_governance/index.html`
- Create: `web/admin/capability_governance/governance_api.js`
- Create: `web/admin/capability_governance/governance_model.js`
- Create: `web/admin/capability_governance/governance_controller.js`
- Create: `web/admin/capability_governance/governance.css`
- Create: `web/admin/capability_governance/governance_model.test.js`
- Create: `web/admin/capability_governance/governance_controller.test.js`
- Modify: `web/admin_hub/index.html`
- Modify: `web/tests/run_tests.js`

**Interfaces:**
- Consumes: existing authenticated `_cloudFetch` and the Task 8 Capability Gateway operations.
- Produces: overview, inventory, Finding center, change/review, tests/health, release gate, audit, and detail drawer without contract edit/delete.

- [ ] **Step 1: Write failing pure-model tests**

```javascript
assert.equal(normalizeGid(1953048035824070656n), '1953048035824070656');
assert.deepEqual(actionsFor(['system.capability.read']), ['view', 'export']);
assert.ok(!actionsFor(['system.capability.govern']).includes('edit-contract'));
assert.equal(filterRows(rows, { domain: 'craft', query: '创建工厂' }).length, 1);
assert.equal(mergeLoadFailure(previousRows, new Error('offline')).rows, previousRows);
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run from `E:/Projects/ai00/workmanship-web`: `node web/tests/run_tests.js`

Expected: FAIL because governance modules/tests are not present.

- [ ] **Step 3: Implement the API adapter**

```javascript
async function invoke(capabilityId, payload, options = {}) {
  return window.parent._cloudFetch(`/api/v1/capabilities/${capabilityId}:invoke`, {
    method: 'POST',
    body: JSON.stringify({
      version: 1,
      payload,
      idempotency_key: options.idempotencyKey,
      expected_resource_version: options.expectedResourceVersion,
      confirmation_token: options.confirmationToken,
    }),
  });
}
```

Never coerce a GID to Number. All collection requests set explicit limits.

- [ ] **Step 4: Implement pure state and controller**

State contains `selectedSnapshotGid`, Product and extension releases/counts, filters, rows, selected entity, stale-data flag, busy action keys, and last error. Rejected refresh preserves previous successful data. Busy keys suppress duplicate actions. Hash navigation supports all seven sections.

- [ ] **Step 5: Implement the approved high-contrast UI**

Use the real 11 domains. Separate Product and Governance Extension counts. Render status with text and icon as well as color. Detail views display contract fields as non-editable text. Governance buttons are permission-derived and never include contract edit/delete.

- [ ] **Step 6: Add focused jsdom controller tests**

Tests cover search, filters, real domain list, row detail, cross-domain multi-subject Finding, stale proposal disabled actions, old-data retention on refresh failure, duplicate-click suppression, GID strings, permission matrix, and absence of native `alert`, `confirm`, and `prompt`.

- [ ] **Step 7: Run full frontend tests and build**

Run: `npm test`

Run: `npm run build:web`

Expected: PASS; test build contains `dist/web/admin/capability_governance/index.html`.

- [ ] **Step 8: Commit frontend Task 11 in the frontend repository**

```bash
git add web/admin/capability_governance web/admin_hub/index.html web/tests/run_tests.js
git commit -m "feat: add capability governance center UI"
```

### Task 12: Enforce production physical exclusion in both repositories

**Files:**
- Modify: `E:/Projects/ai00/workmanship-web/vite.config.js`
- Modify: `E:/Projects/ai00/workmanship-web/package.json`
- Create: `E:/Projects/ai00/workmanship-web/scripts/test_capability_governance_build_profiles.js`
- Create: `docs/governance/test-extension/production-artifact-allowlist.json`
- Create: `backend/scripts/check_production_governance_exclusion.py`
- Create: `backend/scripts/build_capability_v2_production_artifact.py`
- Create: `backend/tests/test_production_governance_exclusion.py`
- Modify: `backend/scripts/check_frontend_deployment.py`
- Modify: `backend/tests/test_frontend_deployment_check.py`

**Interfaces:**
- Consumes: Vite output and backend packaging root.
- Produces: `npm run build:web:test-governance`, `npm run build:web:production`, and `check_production_artifact(root) -> ExclusionReport`.

- [ ] **Step 1: Write failing build-profile and backend exclusion tests**

```javascript
assert.ok(exists('dist-test-governance/web/admin/capability_governance/index.html'));
assert.ok(!exists('dist-production/web/admin/capability_governance/index.html'));
assert.ok(!walk('dist-production').some(p => /capability_governance|test-extension/.test(p)));
```

```python
def test_production_artifact_rejects_governance_provider(tmp_path):
    write(tmp_path / "backend/capability_governance_test/provider.py")
    report = check_production_artifact(tmp_path)
    assert report.status == "failed"
    assert "governance_backend_present" in report.errors
```

- [ ] **Step 2: Run exclusion tests and verify failure**

Run frontend: `node scripts/test_capability_governance_build_profiles.js`

Run backend: `python -m pytest backend/tests/test_production_governance_exclusion.py backend/tests/test_frontend_deployment_check.py -q`

Expected: FAIL because build profiles and allowlist checker are absent.

- [ ] **Step 3: Implement explicit Vite profiles**

Use `AI00_WEB_BUILD_PROFILE` with allowed values `test-governance` and `production`. `production` excludes the governance HTML from Rollup entries, removes the `TEST_GOVERNANCE_START/END` Admin Hub navigation block during HTML transformation, and excludes the entire governance directory from copied assets. Any other formal value fails the build. Output directories are distinct so one profile cannot leave stale files in the other.

- [ ] **Step 4: Implement backend production allowlist verification**

The checked-in allowlist names permitted backend top-level packages, migrations, frontend prefixes, Catalog files, and Provider modules. `build_capability_v2_production_artifact.py` copies only allowlisted files into a newly created output directory, verifies the signed release report, then runs the exclusion checker. The checker rejects governance package, migrations, routes, Provider, Catalog extension, fixtures, UI, and temporary identities by both exact path and forbidden marker scan.

- [ ] **Step 5: Build and verify both profiles**

Run frontend:

```bash
npm run build:web:test-governance
npm run build:web:production
node scripts/test_capability_governance_build_profiles.js
```

Run backend:

```bash
python backend/scripts/build_capability_v2_production_artifact.py --frontend-root E:/Projects/ai00/workmanship-web/dist-production --release-report .runtime/capability-governance-release-report.json --output .runtime/capability-v2-production-artifact
python backend/scripts/check_production_governance_exclusion.py --root .runtime/capability-v2-production-artifact
```

Expected: test build includes the center; production build and report contain zero governance test components.

- [ ] **Step 6: Commit frontend profile changes**

```bash
git add vite.config.js package.json scripts/test_capability_governance_build_profiles.js
git commit -m "build: exclude governance center from production"
```

- [ ] **Step 7: Commit backend exclusion controls**

```bash
git add docs/governance/test-extension/production-artifact-allowlist.json backend/scripts/build_capability_v2_production_artifact.py backend/scripts/check_production_governance_exclusion.py backend/tests/test_production_governance_exclusion.py backend/scripts/check_frontend_deployment.py backend/tests/test_frontend_deployment_check.py
git commit -m "build: verify governance production exclusion"
```

### Task 13: Run full test-environment release acceptance and deploy only the test artifact

**Files:**
- Create: `backend/scripts/run_capability_governance_release_acceptance.py`
- Create: `backend/tests/test_capability_governance_acceptance.py`
- Modify: `backend/scripts/check_capability_v2_completion.py`
- Modify: `backend/scripts/check_frontend_deployment.py`
- Create: `docs/governance/capability-governance-operations.md`
- Update generated test frontend files under `dist/web/admin/capability_governance/`
- Update generated test Catalog extension and acceptance reports under `docs/governance/test-extension/`

**Interfaces:**
- Consumes: Tasks 1–12, authorized OceanBase test credentials, Capability V2 Gateway, test-governance frontend build, and `AI00Backend-CapabilityV2`.
- Produces: one machine-readable acceptance report with zero failed/skipped mandatory checks and deployed test-governance UI on the existing Capability V2 service.

- [ ] **Step 1: Write failing acceptance manifest test**

```python
MANDATORY_SECTIONS = {
    "identity", "catalog_separation", "migration", "snapshot", "graph",
    "deterministic_findings", "permissions", "agent_delegation", "health",
    "workflow", "release_gate", "ai_redaction", "ui", "production_exclusion",
}

def test_acceptance_runner_has_no_optional_mandatory_sections():
    report = run_acceptance(FakeEnvironment.healthy())
    assert set(report.sections) == MANDATORY_SECTIONS
    assert report.failed == 0
    assert report.skipped == 0
```

- [ ] **Step 2: Run acceptance unit tests and verify failure**

Run: `python -m pytest backend/tests/test_capability_governance_acceptance.py -q`

Expected: FAIL because the runner is absent.

- [ ] **Step 3: Implement the acceptance runner**

The runner must:

1. verify explicit machine ID and test profile;
2. verify Product/extension separation and collision-free effective Catalog;
3. verify exact OceanBase tables and grants without querying `mysql.user`;
4. run two unchanged scans and compare GIDs/hash;
5. inject controlled fixtures for transaction-provider, drift, cross-domain conflict, and gap Findings;
6. exercise read/analyze/govern/release permission boundaries including delegated Agent identity;
7. run fast tests and explicit release E2E;
8. approve a controlled Proposal, stale it with a changed hash, and verify release failure;
9. run redaction and repair-prompt checks;
10. build/test frontend and perform HTTP asset checks;
11. build production artifact and prove physical exclusion;
12. write a redacted JSON report with report GID and hashes.

- [ ] **Step 4: Run all focused backend suites**

Run:

```bash
python -m pytest backend/tests/test_capability_governance_gid.py backend/tests/test_capability_governance_config.py backend/tests/test_capability_governance_catalog.py backend/tests/test_capability_catalog_overlay.py backend/tests/test_capability_governance_migrations.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_identity_projection.py backend/tests/test_capability_governance_scanner.py backend/tests/test_capability_governance_rules.py backend/tests/test_capability_cross_domain_analysis.py backend/tests/test_capability_governance_evidence.py backend/tests/test_capability_governance_health.py backend/tests/test_capability_governance_test_profiles.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_permissions.py backend/tests/test_capability_governance_workflow.py backend/tests/test_capability_governance_audit.py backend/tests/test_capability_governance_release_gate.py backend/tests/test_capability_governance_redaction.py backend/tests/test_capability_governance_ai.py backend/tests/test_capability_repair_prompt.py backend/tests/test_production_governance_exclusion.py backend/tests/test_capability_governance_acceptance.py -q
```

Expected: PASS with no skip.

- [ ] **Step 5: Run repository-wide validation**

Run backend:

```bash
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/build_capability_governance_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/build_user_function_registry.py --strict
python backend/scripts/check_domain_dependencies.py
python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict
python -m pytest -q
```

Run frontend from `E:/Projects/ai00/workmanship-web`:

```bash
npm test
npm run build:web:test-governance
npm run build:web:production
node scripts/test_capability_governance_build_profiles.js
```

Expected: all commands exit zero; strict Capability acceptance has zero failed and zero skipped mandatory cases.

- [ ] **Step 6: Run real test-governance acceptance**

Run: `python backend/scripts/run_capability_governance_release_acceptance.py --base-url http://127.0.0.1:8094 --strict`

Expected: `status=passed`, mandatory failed/skipped counts zero, secrets absent, and the final report records Product Catalog ID, Governance Extension ID, Snapshot GID, Test Run GID, and Release Report GID.

- [ ] **Step 7: Synchronize only the test-governance frontend build**

Copy the complete `dist-test-governance` output into the backend worktree `dist` using the existing non-destructive deployment sync. Do not copy `dist-production` and do not delete unrelated user files.

- [ ] **Step 8: Restart and inspect only `AI00Backend-CapabilityV2`**

Verify it binds the approved test address, loads Product + Governance Extension, and serves the governance UI. Do not modify the old service. Check the new startup cycle for Traceback, static 404, Gateway 403 caused by missing governance permissions, migration errors, or frontend syntax errors.

- [ ] **Step 9: Perform browser acceptance**

As authorized administrator:

- open all seven governance pages;
- search by Capability ID, business effect, and snowflake GID;
- filter all 11 real domains;
- open a cross-domain Finding with multiple subjects;
- run analysis and generate a redacted repair prompt;
- confirm stale Proposal controls are disabled;
- run the release gate and inspect immutable evidence.

As a delegated analyst Agent identity, verify read/analyze succeeds and govern/release fails. Browser console must contain no error.

- [ ] **Step 10: Write operator documentation**

Document exact commands for migration, scan, fast tests, release E2E, acceptance, retention, waiver expiry, failure recovery, production exclusion, and service rollback. State that the governance UI/database cannot edit or delete contracts.

- [ ] **Step 11: Commit the backend acceptance and deployed test artifact**

```bash
git add backend/scripts/run_capability_governance_release_acceptance.py backend/tests/test_capability_governance_acceptance.py backend/scripts/check_capability_v2_completion.py backend/scripts/check_frontend_deployment.py docs/governance/capability-governance-operations.md docs/governance/test-extension dist/web/admin/capability_governance dist/web/admin_hub/index.html
git commit -m "feat: complete capability governance acceptance"
```

Do not stage `CODEX-DESKTOP-HANDOFF.md`, `docs/superpowers/reviews/`, unrelated `dist` changes, runtime credentials, reports containing secrets, or temporary identities.

---

## Final Verification Checklist

- [ ] Product Catalog remains authoritative and its baseline hash changes only for intentional product contract changes.
- [ ] Governance Catalog Extension is separately generated, counted, stored, and loaded only in the test profile.
- [ ] Exact official domains are `agent`, `base`, `craft`, `device`, `digital_model`, `factory`, `integration`, `knowledge`, `ontology`, `project_management`, and `simulation`.
- [ ] Every logical Capability and Major has stable snowflake GIDs; browser/agent outputs are decimal strings.
- [ ] All governance tables exist in test and are absent from production schema/artifacts.
- [ ] Repeat unchanged scans preserve identities and snapshot hash.
- [ ] Implementation graph covers Descriptor, Provider, exposure, Port, Repository, migration/table, and tests where applicable.
- [ ] Strong writes without transactional participants fail deterministic release checks.
- [ ] Cross-domain Findings retain all subjects and evidence.
- [ ] Contract-only evidence remains unverified.
- [ ] Fast health checks never write business data.
- [ ] Full OceanBase E2E runs explicitly before release with exact cleanup.
- [ ] Stale hashes invalidate Proposal, Review, Waiver, Test, and Release Report evidence.
- [ ] AI results remain candidate-only, bounded, redacted, and audited.
- [ ] Repair prompts contain no secret, token, URL credential, business payload, or arbitrary source content.
- [ ] UI offers governance actions only and no contract edit/delete.
- [ ] Delegated Agent can read/analyze but cannot govern/release without explicit scope and permission.
- [ ] Governance outage leaves business execution available while release gate fails closed.
- [ ] Production artifact physical-exclusion checker passes.
- [ ] Backend full pytest, frontend full tests/builds, strict Capability V2 acceptance, HTTP checks, and browser acceptance all pass.
- [ ] Backend and frontend commits contain exact intended paths only; no push or merge occurred.
