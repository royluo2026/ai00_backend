# Capability V2 Governance Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Make the backend `test` revision `697aac18` and frontend `test` revision `10948bb` satisfy the V2.1 governance audit through one reproducible contract, inventory, atomicity, consumer, and release-evidence pipeline.

**Architecture:** Extend the existing frozen Capability descriptor and Catalog projection so governance metadata has one typed source. Generate atomicity and route inventories as checked-in JSON inputs, then make the existing Catalog audit, completion evaluator, and Release Gate consume those inputs fail-closed. Migrate the confirmed Craft, Knowledge, Project Management and Web/Plugin route families behind Gateway/BFF adapters while retaining only time-bounded compatibility facades.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, JSON Schema, FastAPI routers, existing Capability Gateway/SDK, JavaScript Web/Plugin sources.

**Spec:** `docs/superpowers/specs/2026-08-21-capability-governance-remediation-design.md`

## Global Constraints

- Work only on backend `test` at `697aac18` and frontend `test` at `10948bb`; do not modify `deploy` or production.
- Every new stable Capability has one primary business effect, a stable major version, and all V2.1 governance fields.
- Release evidence is valid only when `code_revision`, `snapshot_gid`, `catalog_release`, `test_run_gid`, and result hashes refer to the same build.
- Legacy REST is allowed only through a checked-in inventory entry with owner, migration target, absolute deadline, allowed consumers, and evidence references.
- Tests must be written before implementation for every new behavior; every task ends with a focused verification command.
- Use existing helpers and dependencies; do not introduce a new framework or database.

---

### Task 1: Add V2.1 descriptor and projection fields

**Files:**
- Modify: `backend/capability_v2/contracts.py` (`DomainErrorContract`, `CapabilityDescriptorV2`)
- Modify: `backend/capability_v2/descriptor_adapter.py`
- Modify: `backend/capability_v2/catalog.py`
- Modify: `backend/capability_v2/projection.py`
- Modify: `backend/capability_v2/docs/generator.py`
- Test: `backend/tests/test_capability_v2_contracts.py`
- Test: `backend/tests/test_capability_catalog_release.py`
- Test: `backend/tests/test_capability_docs_generation.py`

**Interfaces:**
- `DomainErrorContract` produces `error_code`, `message_template`, `is_retryable`, and `is_caller_error` in the public `error_schema` projection.
- `CapabilityDescriptorV2` produces `capability_version_gid`, `error_schema`, `transaction_policy`, `consumer_refs`, `provider_ref`, `api_refs`, `test_refs`, `business_effect`, and `side_effects`.
- `catalog._descriptor_document()` and `docs.generator._machine_item()` emit the same field names and values.

- [ ] **Step 1: Write failing contract tests.** Add a descriptor factory with all new fields and assert `model_dump()` contains them; assert a caller-fix error is not inferred from `retryable`; assert missing `business_effect`/`provider_ref` is rejected for a stable descriptor.
- [ ] **Step 2: Run focused tests to verify failure.**

Run: `python -m pytest backend/tests/test_capability_v2_contracts.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_docs_generation.py -q`

Expected: FAIL because the new fields and error mapping do not exist.
- [ ] **Step 3: Implement the typed fields and validators.** Keep legacy adapter defaults only for `experimental/deprecated/retired`; require complete fields for `stable`. Map `DomainErrorContract.code/meaning/retryable` to the new schema without silently defaulting `is_caller_error`.
- [ ] **Step 4: Update descriptor/catalog/document projections.** Preserve deterministic key ordering and stable JSON serialization.
- [ ] **Step 5: Re-run focused tests.**

Run: `python -m pytest backend/tests/test_capability_v2_contracts.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_docs_generation.py -q`

Expected: PASS.
- [ ] **Step 6: Commit.**

```bash
git add backend/capability_v2/contracts.py backend/capability_v2/descriptor_adapter.py backend/capability_v2/catalog.py backend/capability_v2/projection.py backend/capability_v2/docs/generator.py backend/tests/test_capability_v2_contracts.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_docs_generation.py
git commit -m "feat: add v2.1 capability governance fields"
```

### Task 2: Generate complete Catalog metadata and audit it

**Files:**
- Modify: `backend/scripts/build_capability_catalog.py`
- Modify: `backend/scripts/generate_capability_docs.py`
- Modify: `backend/capability_v2/catalog_audit.py`
- Modify: `backend/tests/test_capability_v2_catalog_audit.py`
- Modify: `backend/tests/acceptance/test_catalog_release.py`
- Generate: `docs/capabilities/catalog.v2.json`

**Interfaces:**
- `CatalogAuditReport` adds `required_field_missing_counts`, `error_schema_invalid_count`, and `test_evidence_not_run_count` while retaining existing serialized keys.
- `audit_catalog(path, atomicity_path=None)` reads stable descriptors and returns deterministic IDs for every violation.

- [ ] **Step 1: Write failing audit tests.** Use a temporary catalog with one missing required field, one malformed `error_schema`, and one `test_refs` item with `result=not_run`; assert each count is non-zero and the serialized report names the Capability.
- [ ] **Step 2: Run the focused audit tests and confirm failure.**

Run: `python -m pytest backend/tests/test_capability_v2_catalog_audit.py backend/tests/acceptance/test_catalog_release.py -q`

Expected: FAIL because the report has no required-field checks.
- [ ] **Step 3: Add the field and evidence checks.** Stable descriptors must contain non-empty references, closed error schemas, and no `not_run/skipped` test evidence.
- [ ] **Step 4: Update the catalog builder/backfill source.** Derive deterministic `capability_version_gid` from the existing descriptor identity/release inputs; derive references from registered Provider/API/test locations, never from the current machine date.
- [ ] **Step 5: Regenerate and validate the official catalog.**

Run: `python backend/scripts/build_capability_catalog.py --check`

Expected: Catalog release check passes and every stable entry has all required fields.
- [ ] **Step 6: Commit the audit and generated projection.**

```bash
git add backend/capability_v2/catalog_audit.py backend/scripts/build_capability_catalog.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/acceptance/test_catalog_release.py docs/capabilities/catalog.v2.json
git commit -m "feat: enforce complete capability catalog evidence"
```

### Task 3: Add atomicity dispositions for all generic stable descriptors

**Files:**
- Create: `docs/governance/capability-atomicity-dispositions.schema.json`
- Create: `docs/governance/capability-atomicity-dispositions.json`
- Create: `backend/capability_v2/atomicity.py`
- Modify: `backend/capability_v2/catalog_audit.py`
- Modify: `backend/capability_v2/release_gate.py`
- Test: `backend/tests/test_capability_v2_atomicity.py`
- Test: `backend/tests/test_capability_v2_release_gate.py`

**Interfaces:**
- `load_atomicity_dispositions(path) -> AtomicityDispositionReport` validates `split`, `justified`, and `retire` entries.
- `audit_generic_operations(catalog, dispositions) -> AtomicityAudit` returns `unclassified_ids`, `expired_justifications`, and `invalid_replacements`.
- `ReleaseGateReport.passed` is false when any of those collections are non-empty.

- [ ] **Step 1: Write failing tests for the disposition schema and Gate.** Cover missing disposition, `justified` without approval/expiry, and `split` without replacement Capabilities.
- [ ] **Step 2: Run tests to verify failure.**

Run: `python -m pytest backend/tests/test_capability_v2_atomicity.py backend/tests/test_capability_v2_release_gate.py -q`

Expected: FAIL because the module and Gate fields do not exist.
- [ ] **Step 3: Implement the validator and audit.** Normalize IDs by `(id, major_version)` and reject duplicate entries.
- [ ] **Step 4: Generate the 34-entry disposition file.** Mark the confirmed Craft, Knowledge, and Project Management merged descriptors as `split`; mark no item `justified` without evidence.
- [ ] **Step 5: Add the Gate condition and run focused tests.**
- [ ] **Step 6: Commit.**

```bash
git add docs/governance/capability-atomicity-dispositions.schema.json docs/governance/capability-atomicity-dispositions.json backend/capability_v2/atomicity.py backend/capability_v2/catalog_audit.py backend/capability_v2/release_gate.py backend/tests/test_capability_v2_atomicity.py backend/tests/test_capability_v2_release_gate.py
git commit -m "feat: gate generic capability operations by atomicity disposition"
```

### Task 4: Make Web route scanning source-only and add inventories

**Files:**
- Modify: `backend/capability_v2/consumer_routes.py`
- Modify: `backend/capability_v2/completion.py`
- Create: `backend/capability_v2/route_inventory.py`
- Create: `docs/governance/legacy-route-inventory.schema.json`
- Create: `docs/governance/legacy_route_inventory.json`
- Create: `docs/governance/bff-route-inventory.schema.json`
- Create: `docs/governance/bff_route_inventory.json`
- Modify: `backend/tests/test_capability_v2_consumer_routes.py`
- Modify: `backend/tests/test_capability_v2_completion.py`
- Create: `backend/tests/test_capability_v2_route_inventory.py`

**Interfaces:**
- `scan_web_routes()` accepts configured source roots and ignores `dist`, `dist-*`, cache, and generated directories.
- `build_route_inventory(report) -> RouteInventory` deduplicates by `(route_path, method, owner_module, migration_target)` and preserves source evidence.
- `evaluate_completion()` reads the inventory and reports unregistered/expired legacy routes.

- [ ] **Step 1: Write failing scanner tests.** Add `dist-production` and `dist-test-governance` fixtures and an `/api/ebom` fixture; assert generated files are ignored and `/api/ebom` is legacy.
- [ ] **Step 2: Run the scanner tests and verify failure.**

Run: `python -m pytest backend/tests/test_capability_v2_consumer_routes.py backend/tests/test_capability_v2_completion.py backend/tests/test_capability_v2_route_inventory.py -q`

Expected: FAIL on `dist-*` exclusion and inventory generation.
- [ ] **Step 3: Implement source-only scanning and route normalization.** Keep the existing report shape backward-compatible and add unique route records.
- [ ] **Step 4: Generate both inventories from the frontend `test` source tree.** Every legacy route must have owner, migration target, absolute deadline no later than `2026-11-21`, allowed consumers, and evidence.
- [ ] **Step 5: Add legacy inventory and expiry checks to `completion.py` and the Release Gate.**
- [ ] **Step 6: Run focused scanner and Gate tests.**
- [ ] **Step 7: Commit backend inventory tooling and JSON.**

```bash
git add backend/capability_v2/consumer_routes.py backend/capability_v2/completion.py backend/capability_v2/route_inventory.py backend/tests/test_capability_v2_consumer_routes.py backend/tests/test_capability_v2_completion.py backend/tests/test_capability_v2_route_inventory.py docs/governance/*route*inventory*
git commit -m "feat: add source-only legacy route governance"
```

### Task 5: Split confirmed Craft EBOM Capability and preserve a bounded facade

**Files:**
- Modify: `plugins/craft/craft_backend/capabilities/ebom_change.py`
- Modify: `plugins/craft/craft_backend/routers/ebom.py`
- Create: `plugins/craft/craft_backend/capabilities/ebom_snapshot_change.py`
- Create: `plugins/craft/craft_backend/capabilities/ebom_snapshot_status_change.py`
- Create: `plugins/craft/craft_backend/capabilities/ebom_vpps_stats_change.py`
- Create: `plugins/craft/craft_backend/capabilities/ebom_part_change.py`
- Modify: `backend/tests/test_craft_ebom_change_boundary.py`
- Create: `backend/tests/test_craft_ebom_atomicity.py`
- Modify: frontend `E:/Projects/ai00/workmanship-web/packages/craft-plugin/web/ebom/ebom.js`
- Modify: frontend `E:/Projects/ai00/workmanship-web/packages/craft-plugin/web/pbom_check/pbom_check.js`

**Interfaces:**
- Each new Capability exposes exactly one operation and its own schema, permission, idempotency, transaction, and audit event.
- The old `craft.ebom.change.apply` adapter accepts only already-inventoried legacy calls and delegates to one new Capability per request; it cannot dispatch an arbitrary operation set for new consumers.

- [ ] **Step 1: Add failing boundary tests** asserting the new Capability IDs exist, the old descriptor is deprecated/compatibility-only, and each adapter route names one target Capability.
- [ ] **Step 2: Run the Craft boundary tests and verify failure.**
- [ ] **Step 3: Extract the existing operation handlers into single-effect Providers without changing SQL semantics.**
- [ ] **Step 4: Update the router and frontend route-family callers to use Gateway/SDK/BFF calls with the new IDs.**
- [ ] **Step 5: Run Craft focused tests and frontend syntax checks.**

Run: `python -m pytest backend/tests/test_craft_ebom_change_boundary.py backend/tests/test_craft_ebom_atomicity.py -q` and `node --check E:\Projects\ai00\workmanship-web\packages\craft-plugin\web\ebom\ebom.js`.
- [ ] **Step 6: Commit backend and frontend changes in their respective `test` repositories.**

### Task 6: Split Knowledge and Project Management merged Capabilities

**Files:**
- Modify: `plugins/knowledge/knowledge_backend/capabilities/reviewed.py`
- Modify: `plugins/knowledge/knowledge_backend/application/outcomes.py`
- Modify: `plugins/knowledge/knowledge_backend/api/knowledge_hub_legacy.py`
- Modify: `plugins/project_management/project_management_backend/application/service.py`
- Modify: `plugins/project_management/project_management_backend/capabilities/*`
- Modify: `backend/tests/test_knowledge_capability_contracts.py`
- Modify: `backend/tests/test_knowledge_legacy_boundary.py`
- Modify: `backend/tests/test_project_capabilities.py`
- Create: `backend/tests/test_atomic_capability_split_boundaries.py`

**Interfaces:**
- Knowledge create/update/delete/read/history each maps to a distinct stable Capability ID and provider function.
- Project approval decisions, state transitions, project/vehicle, task/dependency and batch operations each map to distinct stable IDs; no `_OPERATIONS` entry may silently combine unrelated resources.
- Legacy routers remain adapters with an inventory deadline and explicit target ID.

- [ ] **Step 1: Add failing tests for the new IDs and one-effect operation tables.**
- [ ] **Step 2: Run the focused Knowledge/Project tests and verify failure.**
- [ ] **Step 3: Extract provider functions and schemas, preserving repository transactions and authorization checks.**
- [ ] **Step 4: Update legacy adapters, Catalog references, and consumer tests.**
- [ ] **Step 5: Run focused domain tests and the atomicity audit.**
- [ ] **Step 6: Commit the backend domain split.**

### Task 7: Add Task Tool/Pack/Skill/Workflow and business panorama registries

**Files:**
- Create: `docs/governance/task-tool-registry.schema.json`
- Create: `docs/governance/task-tool-registry.json`
- Create: `docs/governance/capability-pack-registry.schema.json`
- Create: `docs/governance/capability-pack-registry.json`
- Create: `docs/governance/skill-registry.schema.json`
- Create: `docs/governance/skill-registry.json`
- Create: `docs/governance/workflow-registry.schema.json`
- Create: `docs/governance/workflow-registry.json`
- Create: `docs/governance/business-panorama-ledger.schema.json`
- Create: `docs/governance/business_panorama_ledger.json`
- Modify: `backend/capability_v2/release_gate.py`
- Create: `backend/capability_v2/orchestration_audit.py`
- Test: `backend/tests/test_capability_v2_orchestration_audit.py`

**Interfaces:**
- `audit_orchestration_registries(root, catalog) -> OrchestrationAuditReport` validates IDs, owners, lifecycle, Gateway/SDK route, and stable `consumed_capabilities`.
- `audit_business_panorama_ledger(path, catalog) -> PanoramaAuditReport` requires at least five nodes and stable mappings for every green node.

- [ ] **Step 1: Write failing registry and ledger tests.** Include invalid unstable consumption, missing owner, and green node without observability.
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Add the schemas, first three Task Tools, one Pack, one Skill, one Workflow, and five business nodes.**
- [ ] **Step 4: Add the audit to Release Gate and run focused tests.**
- [ ] **Step 5: Commit the registry assets and audit.**

### Task 8: Bind authoritative release evidence and update the final Gate

**Files:**
- Modify: `backend/capability_governance_test/evidence.py`
- Modify: `backend/capability_governance_test/release_gate.py`
- Modify: `backend/scripts/run_capability_v2_acceptance.py`
- Modify: `backend/scripts/build_capability_v2_production_artifact.py`
- Modify: `backend/tests/test_capability_governance_evidence.py`
- Modify: `backend/tests/test_capability_governance_release_gate.py`
- Create: `backend/tests/test_capability_v2_release_evidence_alignment.py`

**Interfaces:**
- `read_release_evidence()` rejects missing authority records, `not_run/skipped`, mismatched `code_revision`, and mismatched hashes.
- The production artifact builder accepts only a Gate report whose evidence was reloaded from the authority port.

- [ ] **Step 1: Write failing evidence-alignment tests** for stale code revision, null runtime hash, and component `not_run`.
- [ ] **Step 2: Run evidence tests and verify failure.**
- [ ] **Step 3: Implement strict alignment checks and include the current backend/frontend test revisions in the acceptance manifest.**
- [ ] **Step 4: Run the controlled test-governance acceptance from the backend worktree cwd and persist the report.**
- [ ] **Step 5: Re-run the authority-backed Release Gate.**
- [ ] **Step 6: Commit evidence and release-gate changes.**

### Task 9: Full verification and handoff

**Files:**
- Modify only generated reports under `.runtime/` if the acceptance runner writes them.
- Review: all files changed by Tasks 1–8.

- [ ] **Step 1: Run contract, Catalog, atomicity, route, registry, and evidence tests.**

Run: `python -m pytest -p no:cacheprovider backend/tests/test_capability_v2_contracts.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/test_capability_v2_atomicity.py backend/tests/test_capability_v2_consumer_routes.py backend/tests/test_capability_v2_completion.py backend/tests/test_capability_v2_route_inventory.py backend/tests/test_capability_v2_orchestration_audit.py backend/tests/test_capability_governance_evidence.py backend/tests/test_capability_governance_release_gate.py -q`

- [ ] **Step 2: Run domain boundary tests for Craft, Knowledge, and Project Management.**
- [ ] **Step 3: Run source-only frontend route scan and JavaScript syntax checks on the frontend `test` worktree.**
- [ ] **Step 4: Run all existing release prerequisite scripts from the backend `test` worktree.**
- [ ] **Step 5: Run `python backend/scripts/check_capability_v2_release_gate.py --web-root E:\Projects\ai00\workmanship-web` and require `passed: true`.**
- [ ] **Step 6: Review `git status`, changed-file scope, and generated evidence hashes; report any remaining external/runtime blocker separately rather than weakening the Gate.**
