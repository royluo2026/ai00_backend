# Capability V2 Coverage and Domain-Independence Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete, reviewable disposition for every stable user function and an exact code/database independence backlog for every first-class domain, without implementing or migrating any new Capability before the candidate list is approved.

**Architecture:** Store one independently reviewable JSON document per domain, validate all documents against one closed schema, and generate five deterministic cross-domain views: function dispositions, Capability candidates, consumer exposure, code extraction, and database ownership/migration. Join those reviews to the existing User Function Registry, frozen Catalog, domain ownership registry, table inventory, and both dependency baselines. Audit strict mode accepts reviewed new-Capability proposals but rejects unreviewed functions, duplicate business implementations, ambiguous owners, unowned tables/migrations, and unaccounted boundary violations; the existing Registry release gate continues to reject proposed IDs until later plans implement and publish them.

**Tech Stack:** Python 3, JSON Schema Draft 2020-12, pytest, existing Capability V2 Registry/Catalog builders, existing domain-boundary scanners, Markdown generated reports.

## Global Constraints

- This plan is audit-only. It may add validators, tests, reviewed governance data, and generated reports; it must not add or modify Capability Providers, domain business logic, routers, repositories, database migrations, Web consumers, Plugin consumers, Agent tools, or runtime deployment code.
- Web, REST compatibility, Plugin, Agent, MCP, and Local Runtime share one Capability ID, Descriptor, Provider, Gateway pipeline, and version history for the same business outcome.
- Registry resolution does not imply universal exposure. Consumer access is recorded independently and enforced later through the shared Capability.
- Every stable function resolves exactly once as `existing_capability`, `new_capability`, or `excluded`.
- Every exclusion contains a specific reason, source evidence, reviewer, owner, and review date; generic internal/operations labels fail validation.
- Every proposed Capability names one owner domain, one business outcome, its source function IDs, intended consumers, Application Port, Provider artifact, owned tables, and owned migration stream.
- Every table and migration has exactly one domain owner. Cross-domain writes, Router imports, Repository imports, ORM imports, migration imports, concrete-service imports, and private database-helper imports remain explicit debt until a later implementation plan removes them.
- Historical migrations are immutable. Ownership corrections use new migrations in later implementation plans.
- Existing Capabilities are reused before a new Capability is proposed. Route-shaped and catch-all Capabilities are prohibited.
- If the proposed stable Catalog exceeds 170 Capabilities, or any domain proposes more than 40 additions, the audit stops at architecture review.
- Do not access production databases, production OIS, real devices, or release channels.

---

## File Map

### Reviewed source documents

- `docs/governance/capability-coverage-review.schema.json`: closed schema shared by every domain review.
- `docs/governance/capability-coverage-review/manifest.json`: binds the review set to Git commit, Registry hash, Catalog release/hash, ownership hash, table-inventory hash, and baseline hashes.
- `docs/governance/capability-coverage-review/base-platform.json`
- `docs/governance/capability-coverage-review/agent.json`
- `docs/governance/capability-coverage-review/craft.json`
- `docs/governance/capability-coverage-review/digital-model.json`
- `docs/governance/capability-coverage-review/project-management.json`
- `docs/governance/capability-coverage-review/simulation.json`
- `docs/governance/capability-coverage-review/ontology.json`
- `docs/governance/capability-coverage-review/knowledge.json`
- `docs/governance/capability-coverage-review/local-integration.json`

### Generated review views

- `docs/governance/capability-coverage-review/generated/function-dispositions.md`
- `docs/governance/capability-coverage-review/generated/capability-candidates.md`
- `docs/governance/capability-coverage-review/generated/consumer-exposure.md`
- `docs/governance/capability-coverage-review/generated/code-ownership-extractions.md`
- `docs/governance/capability-coverage-review/generated/database-ownership-migrations.md`
- `docs/governance/capability-coverage-review/generated/summary.json`

### Validation code

- `backend/scripts/build_capability_coverage_review.py`: merge-preserving initializer, validator, generator, and drift checker.
- `backend/tests/test_capability_coverage_review.py`: schema, join, count, ownership, exposure, and report tests.
- `backend/tests/fixtures/capability_coverage_review/`: minimal valid and invalid review fixtures.
- `backend/scripts/build_user_function_registry.py`: strict-mode linkage to approved dispositions.
- `backend/tests/test_user_function_registry.py`: strict disposition linkage tests.
- `backend/scripts/check_domain_dependencies.py`: review linkage for all seven module-level debt rows.
- `backend/scripts/audit_domain_boundaries.py`: review linkage for 262 cross-domain SQL and 30 internal-import debt rows.
- `backend/scripts/verify_domain_db_isolation.py`: complete runtime database-account coverage for all nine first-class domains.
- `backend/tests/test_domain_independence_v2.py`: exact ownership and debt-accounting tests.
- `backend/tests/test_domain_governance.py`: table/migration/write-path review tests.
- `backend/tests/test_plugin_acceptance_tooling.py`: database-isolation verifier coverage.

---

### Task 1: Define the closed per-domain review contract

**Files:**
- Create: `docs/governance/capability-coverage-review.schema.json`
- Create: `backend/tests/fixtures/capability_coverage_review/minimal-valid.json`
- Create: `backend/tests/fixtures/capability_coverage_review/invalid-generic-exclusion.json`
- Create: `backend/tests/fixtures/capability_coverage_review/invalid-consumer-duplicate.json`
- Create: `backend/tests/test_capability_coverage_review.py`

**Interfaces:**
- Produces: Draft 2020-12 schema with `additionalProperties: false` at every object boundary.
- Produces: resolution enum `unreviewed | existing_capability | new_capability | excluded`; approved documents and audit strict mode forbid `unreviewed`.
- Produces: exposure keys `web`, `rest`, `plugin`, `agent`, `mcp`, and `local_runtime`, each with `enabled`, `reason`, and `policy_ref`.
- Produces: candidate, code-extraction, database-boundary, and debt-disposition records used by all later tasks.

- [ ] **Step 1: Write failing schema tests**

```python
def test_minimal_domain_review_is_closed_and_valid(review_schema, fixture):
    jsonschema.Draft202012Validator(review_schema).validate(fixture("minimal-valid.json"))


def test_generic_exclusion_is_rejected(review_schema, fixture):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-generic-exclusion.json")
        )


def test_consumer_specific_duplicate_implementation_is_rejected(review_schema, fixture):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(review_schema).validate(
            fixture("invalid-consumer-duplicate.json")
        )
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_coverage_review.py -q`

Expected: FAIL because the schema and fixtures do not exist.

- [ ] **Step 3: Implement the schema and exact fixtures**

Every domain document must require these top-level keys:

```json
{
  "schema_version": 1,
  "domain": "Project Management",
  "reviewed_against": {
    "git_commit": "40 lowercase hexadecimal characters",
    "registry_sha256": "sha256:<64 lowercase hexadecimal characters>",
    "catalog_release": "non-empty release ID",
    "catalog_sha256": "sha256:<64 lowercase hexadecimal characters>"
  },
  "function_dispositions": {},
  "capability_candidates": {},
  "consumer_exposures": {},
  "code_extractions": [],
  "database_boundaries": [],
  "debt_dispositions": [],
  "review": {
    "reviewer": "non-empty owner identity",
    "reviewed_at": "YYYY-MM-DD",
    "status": "draft"
  }
}
```

`excluded` records require at least one source path, an evidence string of at least 20 characters, a reason of at least 20 characters, and classification `internal | operations | ui_transient | transport_adapter | unstable_product_surface`. They must have `target_capability: null`.

`existing_capability` records require a non-null Catalog ID and may not define a candidate. `new_capability` records require a matching key in `capability_candidates`.

Every candidate requires `business_outcome`, `non_goals`, `source_function_ids`, `owner_domain`, `application_port`, `provider_artifact`, `owned_tables`, `migration_stream`, and `consumer_exposure_ref`.

- [ ] **Step 4: Run schema tests and verify GREEN**

Run: `python -m pytest backend/tests/test_capability_coverage_review.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/governance/capability-coverage-review.schema.json backend/tests/fixtures/capability_coverage_review backend/tests/test_capability_coverage_review.py
git commit -m "test: define capability coverage review contract"
```

### Task 2: Build deterministic review initialization and five generated views

**Files:**
- Create: `backend/scripts/build_capability_coverage_review.py`
- Create: `docs/governance/capability-coverage-review/manifest.json`
- Create: the nine domain JSON documents listed in the File Map
- Create: the six generated files listed in the File Map
- Modify: `backend/tests/test_capability_coverage_review.py`

**Interfaces:**
- Produces: `load_sources(root: Path) -> AuditSources`.
- Produces: `merge_domain_review(existing: dict, discovered: list[dict]) -> dict` preserving every reviewed field.
- Produces: CLI modes `--write`, `--check`, and `--strict`.
- Produces: deterministic Markdown sorted by domain, business outcome, Capability ID, and function ID.

- [ ] **Step 1: Write failing merge and determinism tests**

```python
def test_merge_preserves_reviewed_dispositions_and_adds_new_candidates(builder):
    merged = builder.merge_domain_review(REVIEWED_DOMAIN, DISCOVERED_FUNCTIONS)
    assert merged["function_dispositions"]["rest:GET:/api/projects"]["resolution"] == "existing_capability"
    assert merged["function_dispositions"]["rest:GET:/api/new-route"]["resolution"] == "unreviewed"


def test_generated_views_are_order_independent(builder):
    assert builder.render_views(DOCUMENTS) == builder.render_views(list(reversed(DOCUMENTS)))
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_coverage_review.py -q`

Expected: FAIL because the builder module does not exist.

- [ ] **Step 3: Implement initialization without semantic auto-classification**

`--write` copies stable Registry evidence into the owning domain document and assigns only `resolution: unreviewed`. It may suggest groups in generated Markdown, but it must never auto-approve an exclusion, owner change, existing mapping, or new Capability.

`--check` verifies deterministic source and generated-file drift while allowing drafts. `--strict` additionally requires every stable function to have an approved disposition and every domain review status to be `approved`.

- [ ] **Step 4: Generate the initial nine draft documents and views**

Run: `python backend/scripts/build_capability_coverage_review.py --write`

Expected summary: 753 stable function records, 125 already resolved from the existing Registry, and 628 `unreviewed` records distributed across the current seven unresolved domains; Digital Model and Simulation documents exist with zero unresolved rows.

- [ ] **Step 5: Verify deterministic output**

Run: `python backend/scripts/build_capability_coverage_review.py --check`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/build_capability_coverage_review.py backend/tests/test_capability_coverage_review.py docs/governance/capability-coverage-review
git commit -m "feat: generate domain capability coverage reviews"
```

### Task 3: Make Registry strict mode consume approved review dispositions

**Files:**
- Modify: `docs/governance/user-function-registry.schema.json`
- Modify: `backend/scripts/build_user_function_registry.py`
- Modify: `backend/tests/test_user_function_registry.py`
- Modify: `backend/tests/test_capability_coverage_review.py`

**Interfaces:**
- Consumes: approved per-domain function dispositions.
- Produces: a generated Registry projection; reviewed governance remains authored in the domain review documents.
- Produces: strict failures for missing review rows, mismatched source evidence, dangling Catalog IDs, generic exclusions, candidate-without-definition, and owner mismatch.

- [ ] **Step 1: Write failing strict-linkage tests**

```python
def test_strict_rejects_registry_row_missing_from_domain_review(tmp_path):
    result = run_builder("--strict", registry=ONE_STABLE_ROW, reviews=EMPTY_REVIEWS)
    assert result.returncode != 0
    assert "missing reviewed disposition" in result.stdout


def test_strict_rejects_target_owned_by_another_domain(tmp_path):
    result = run_builder("--strict", registry=PROJECT_ROW, reviews=PROJECT_TO_CRAFT_CAPABILITY)
    assert result.returncode != 0
    assert "capability owner mismatch" in result.stdout
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest backend/tests/test_user_function_registry.py backend/tests/test_capability_coverage_review.py -q`

Expected: FAIL because Registry strict mode does not load domain reviews.

- [ ] **Step 3: Implement one-way projection from review documents**

The Registry builder reads domain reviews after discovery and applies only approved dispositions whose `function_id`, domain, and sorted `source_paths` match current evidence. A stale review is reported and ignored; it is never silently retained.

- [ ] **Step 4: Verify draft behavior and strict blocking**

Run: `python backend/scripts/build_user_function_registry.py --check`

Expected: PASS with draft reviews.

Run: `python backend/scripts/build_user_function_registry.py --strict`

Expected: FAIL with exactly 628 unresolved review rows before the domain audits.

- [ ] **Step 5: Commit**

```bash
git add docs/governance/user-function-registry.schema.json backend/scripts/build_user_function_registry.py backend/tests/test_user_function_registry.py backend/tests/test_capability_coverage_review.py
git commit -m "feat: bind registry governance to domain reviews"
```

### Task 4: Join code, table, migration, and dependency evidence into the review

**Files:**
- Modify: `backend/scripts/build_capability_coverage_review.py`
- Modify: `backend/scripts/check_domain_dependencies.py`
- Modify: `backend/scripts/audit_domain_boundaries.py`
- Modify: `backend/scripts/verify_domain_db_isolation.py`
- Modify: `backend/tests/test_capability_coverage_review.py`
- Modify: `backend/tests/test_domain_independence_v2.py`
- Modify: `backend/tests/test_domain_governance.py`
- Modify: `backend/tests/test_plugin_acceptance_tooling.py`
- Read: `docs/governance/domain-ownership.json`
- Read: `docs/governance/domain-dependency-baseline.json`
- Read: `backend/governance/table_inventory.json`
- Read: `backend/governance/boundary_baseline.json`

**Interfaces:**
- Produces: an exact debt key for every module dependency and boundary violation.
- Produces: migration ownership inferred from the most-specific `migration_paths` rule.
- Produces: a database boundary row for every one of the 162 inventoried tables.
- Produces: runtime database-account checks for `base`, `agent`, `craft`, `digital_model`, `project_management`, `simulation`, `ontology`, `knowledge`, and `local_integration`.
- Requires: all 7 module-level dependency rows and all 292 boundary rows appear exactly once in a domain review.

- [ ] **Step 1: Write failing evidence-completeness tests**

```python
def test_every_baseline_violation_has_one_review_disposition(audit):
    assert audit.unreviewed_dependency_keys == set()
    assert audit.duplicate_dependency_keys == set()


def test_every_table_and_migration_has_one_owner(audit):
    assert len(audit.table_owners) == 162
    assert audit.ambiguous_tables == set()
    assert audit.unowned_migrations == set()


def test_database_isolation_verifier_covers_all_first_class_domains():
    assert set(URLS) == {
        "base", "agent", "craft", "digital_model", "project_management",
        "simulation", "ontology", "knowledge", "local_integration",
    }
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_coverage_review.py backend/tests/test_domain_independence_v2.py backend/tests/test_domain_governance.py backend/tests/test_plugin_acceptance_tooling.py -q`

Expected: FAIL because review documents do not account for dependency and database evidence.

- [ ] **Step 3: Implement exact joins and generate ownership views**

Use the existing violation fingerprints when present. For `domain-dependency-baseline.json`, derive a stable SHA-256 key from canonical JSON containing `source`, `imported_module`, `source_domain`, and `target_domain`.

Each debt disposition records `current_owner`, `target_owner`, `replacement_boundary`, `source_paths`, and `resolution_plan`. This task records the debt; it does not remove it. Complete the verifier's URL map with `AI00_DIGITAL_MODEL_DB_URL`, `AI00_ONTOLOGY_DB_URL`, and the canonical `AI00_LOCAL_INTEGRATION_DB_URL`; retain `AI00_DEVICE_DB_URL` only as a documented compatibility input.

- [ ] **Step 4: Regenerate and verify current-state counts**

Run: `python backend/scripts/build_capability_coverage_review.py --write`

Expected generated summary includes 7 module dependency rows, 292 boundary rows split into 262 `cross_domain_sql` and 30 `internal_import`, and 162 tables.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/build_capability_coverage_review.py backend/scripts/check_domain_dependencies.py backend/scripts/audit_domain_boundaries.py backend/scripts/verify_domain_db_isolation.py backend/tests/test_capability_coverage_review.py backend/tests/test_domain_independence_v2.py backend/tests/test_domain_governance.py backend/tests/test_plugin_acceptance_tooling.py docs/governance/capability-coverage-review
git commit -m "test: inventory domain code and database boundaries"
```

### Task 5: Review Base Platform and Project Management

**Files:**
- Modify: `docs/governance/capability-coverage-review/base-platform.json`
- Modify: `docs/governance/capability-coverage-review/project-management.json`
- Modify: generated review views

**Interfaces:**
- Resolves: 146 current Base Platform and 22 current Project Management unresolved stable records.
- Corrects: Project Management behavior incorrectly hosted or classified under Craft/Base.
- Records: physical extraction of `plugins/craft/craft_backend/routers/projects.py` and `plugins/craft/craft_backend/routers/workbench_home.py`.
- Records: replacement ownership stream for `202608050002_craft_work_collaboration_tables.sql` and `202608050003_craft_list_team_visibility.sql` without editing applied migrations.

- [ ] **Step 1: Produce an evidence packet before making dispositions**

Run: `python backend/scripts/build_capability_coverage_review.py --domain "Base Platform" --evidence`

Run: `python backend/scripts/build_capability_coverage_review.py --domain "Project Management" --evidence`

Expected: reports sorted source functions, existing Catalog matches, source owners, tables, migrations, consumers, and boundary debt for both domains.

- [ ] **Step 2: Review every function against business ownership**

Use `existing_capability` only when the input/output/resource/audit meaning matches. Use `excluded` for transport, health, authentication plumbing, operational diagnostics, and UI-transient composition only with specific evidence. Use `new_capability` for stable project/workspace/task/issue/milestone/member-role/change-coordination outcomes not represented by the existing Catalog.

- [ ] **Step 3: Review shared-system boundaries**

Base retains identity, tenancy, authorization, plugin lifecycle/storage, Artifact/Operation/Revision infrastructure, shared activity/search primitives, and Capability runtime. Project Management owns projects, workspaces, tasks, issues, milestones, memberships, workbenches, lists used for work coordination, and their tables.

- [ ] **Step 4: Validate both domain reviews**

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain "Base Platform"`

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain "Project Management"`

Expected: zero unreviewed function rows for both domains; all proposed candidates and exclusions validate; no implementation files change.

- [ ] **Step 5: Commit the reviewed data**

```bash
git add docs/governance/capability-coverage-review
git commit -m "docs: review base and project capability coverage"
```

### Task 6: Review Knowledge and Ontology

**Files:**
- Modify: `docs/governance/capability-coverage-review/knowledge.json`
- Modify: `docs/governance/capability-coverage-review/ontology.json`
- Modify: generated review views

**Interfaces:**
- Resolves: 21 current Knowledge and 27 current Ontology unresolved stable records.
- Records: replacement of direct Base database, GID, and OIS implementation dependencies with domain-owned repositories, ID ports, and ArtifactPort.
- Prevents: Craft-hosted Ontology routes from being counted as Craft business outcomes.

- [ ] **Step 1: Generate Knowledge and Ontology evidence packets**

Run: `python backend/scripts/build_capability_coverage_review.py --domain Knowledge --evidence`

Run: `python backend/scripts/build_capability_coverage_review.py --domain Ontology --evidence`

- [ ] **Step 2: Review semantic outcomes and existing aliases**

Map document, space, proposal, release, concept, mapping, diff, impact, ACL, revision, and migration-status functions to existing stable Capabilities where their contracts match. Keep deprecated compatibility aliases out of new candidate counts. Treat raw CRUD routes as adapters when they implement the same reviewed outcome.

- [ ] **Step 3: Record code/database independence work**

Every direct import or SQL access receives an exact target public boundary and owning artifact. Ontology tables remain Ontology-owned even when historical migration filenames contain `base`; Knowledge publication/outbox tables remain Knowledge-owned.

- [ ] **Step 4: Validate and commit**

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain Knowledge`

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain Ontology`

Expected: zero unreviewed rows in both domains.

```bash
git add docs/governance/capability-coverage-review
git commit -m "docs: review knowledge and ontology capability coverage"
```

### Task 7: Review Agent without duplicating domain business capabilities

**Files:**
- Modify: `docs/governance/capability-coverage-review/agent.json`
- Modify: generated review views

**Interfaces:**
- Resolves: 67 current Agent unresolved stable records: 39 Agent tools, 13 Agent Runtime routes, and 15 Agent-owned REST functions.
- Requires: tools for Craft, Project Management, Knowledge, Ontology, Base, and Local Integration map to those domains' shared Capabilities rather than Agent-owned duplicates.
- Keeps in Agent: Run, session, delegation, approval orchestration, memory, preference, tool selection, and Agent-specific audit outcomes.

- [ ] **Step 1: Generate the Agent evidence packet**

Run: `python backend/scripts/build_capability_coverage_review.py --domain Agent --evidence`

- [ ] **Step 2: Classify every tool by business owner**

For each of the 39 tool registrations, record `tool_name`, owning business domain, shared Capability ID or candidate ID, Agent exposure reason, required automation level, approval requirement, and data projection. A handler that imports another domain implementation is recorded for replacement by Gateway invocation.

- [ ] **Step 3: Separate runtime control plane from domain tools**

Session health and transport endpoints are reviewed as operations/transport exclusions where appropriate. Run create/pause/resume/cancel, approval decisions, memory, preference, and delegation remain Agent outcomes when they are stable user functions.

- [ ] **Step 4: Validate duplicate-implementation invariant**

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain Agent`

Expected: zero Agent rows propose an Agent-owned Capability for a Craft, Project Management, Knowledge, Ontology, Base Platform, Digital Model, Simulation, or Local Integration business outcome.

- [ ] **Step 5: Commit**

```bash
git add docs/governance/capability-coverage-review
git commit -m "docs: review agent capability consumption"
```

### Task 8: Review Craft and the remaining domains

**Files:**
- Modify: `docs/governance/capability-coverage-review/craft.json`
- Modify: `docs/governance/capability-coverage-review/local-integration.json`
- Modify: `docs/governance/capability-coverage-review/digital-model.json`
- Modify: `docs/governance/capability-coverage-review/simulation.json`
- Modify: generated review views

**Interfaces:**
- Resolves: 342 current Craft and 3 current Local Integration unresolved stable records.
- Revalidates: zero currently unresolved Digital Model and Simulation rows against ownership and shared-consumer rules.
- Requires: Project Management and Ontology dispositions from Tasks 5 and 6 before final Craft ownership classification.

- [ ] **Step 1: Generate evidence packets**

Run: `python backend/scripts/build_capability_coverage_review.py --domain Craft --evidence`

Run: `python backend/scripts/build_capability_coverage_review.py --domain "Local Integration" --evidence`

Run: `python backend/scripts/build_capability_coverage_review.py --domain "Digital Model" --evidence`

Run: `python backend/scripts/build_capability_coverage_review.py --domain Simulation --evidence`

- [ ] **Step 2: Remove misplaced behavior from the Craft count before proposing candidates**

Reassign project/work coordination, Ontology, generic identity/team/grant, and Agent orchestration functions to their reviewed owner documents. Craft retains BOP, GBOP, PBOM, manufacturing resources, craft libraries, standard operations, factory planning, import/export semantics specific to manufacturing, and Craft revision outcomes.

- [ ] **Step 3: Consolidate Craft routes around business outcomes**

Map list/detail/page helpers to existing search/get Capabilities when contracts match. Consolidate create/edit/archive/freeze/fork/publish/import/link/compare/preview operations by outcome and aggregate root. Do not create one Capability per HTTP method or path.

- [ ] **Step 4: Review Local Integration, Digital Model, and Simulation**

Local Integration owns enrollment, device commands, local execution, signed receipts, and operation recovery. Digital Model and Simulation retain their existing independent Providers and references; record any Web/Plugin/Agent exposure additions against the same existing Capability IDs.

- [ ] **Step 5: Validate and commit**

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain Craft`

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain "Local Integration"`

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain "Digital Model"`

Run: `python backend/scripts/build_capability_coverage_review.py --check --domain Simulation`

Expected: zero unreviewed rows across all four documents.

```bash
git add docs/governance/capability-coverage-review
git commit -m "docs: review craft model simulation and local coverage"
```

### Task 9: Freeze the discussion package without implementing candidates

**Files:**
- Modify: `docs/governance/capability-coverage-review/manifest.json`
- Modify: all generated review views
- Modify: `backend/tests/test_capability_coverage_review.py`

**Interfaces:**
- Produces: exact proposed final Catalog count, additions by domain, consolidation ratios, exclusions, exposure counts, code extraction list, table/migration ownership list, and debt-removal backlog.
- Produces: a review package bound to the current Git commit and governance hashes.
- Does not modify: Catalog descriptors, Providers, routers, repositories, migrations, consumers, or deployment code.

- [ ] **Step 1: Write the final cross-view consistency test**

```python
def test_approved_audit_has_zero_unreviewed_and_consistent_candidates(audit):
    assert audit.unreviewed_stable_functions == set()
    assert audit.dangling_existing_capability_ids == set()
    assert audit.planned_capability_ids == set(audit.capability_candidates)
    assert audit.duplicate_business_implementations == set()
    assert audit.ambiguous_code_owners == set()
    assert audit.ambiguous_table_owners == set()
    assert audit.unaccounted_dependency_debt == set()
```

- [ ] **Step 2: Run all audit and existing drift checks**

Run: `python backend/scripts/build_capability_coverage_review.py --strict`

Run: `python backend/scripts/build_user_function_registry.py --strict`

Run: `python backend/scripts/build_capability_catalog.py --check`

Run: `python backend/scripts/check_domain_dependencies.py --check`

Run: `python backend/scripts/audit_domain_boundaries.py --root .`

Run: `python -m pytest backend/tests/test_capability_coverage_review.py backend/tests/test_user_function_registry.py backend/tests/test_domain_independence_v2.py backend/tests/test_domain_governance.py backend/tests/test_domain_capability_coverage.py -q`

Expected: audit strict mode passes with zero unreviewed functions; Registry strict mode remains non-zero only for the exact approved `new_capability` set because this audit plan does not publish Providers or descriptors; existing Catalog remains unchanged and drift-free; dependency tools report the exact reviewed historical debt rather than new violations; focused tests pass.

- [ ] **Step 3: Enforce architecture review thresholds**

The builder exits with code 3 and prints the exact domain counts when the proposed stable total exceeds 170 or a domain proposes more than 40 additions. Do not change candidate records to evade this gate; return the generated candidate view for architecture discussion.

- [ ] **Step 4: Mark domain documents approved and freeze the manifest**

Update each document's review status from `draft` to `approved` only after the corresponding domain owner review is recorded. Regenerate the manifest hashes and all five views.

- [ ] **Step 5: Commit the discussion package**

```bash
git add backend/tests/test_capability_coverage_review.py docs/governance/capability-coverage-review
git commit -m "docs: freeze capability coverage discussion package"
```

## Discussion Checkpoint

Stop after Task 9. Present the five generated views and exact counts to the user. Do not create an implementation plan for new Capabilities, code extraction, database migration, consumer migration, or boundary-debt removal until the user approves the candidate and ownership lists.
