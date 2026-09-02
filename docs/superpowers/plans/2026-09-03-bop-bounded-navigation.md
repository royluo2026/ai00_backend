# BOP Bounded Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix TC primary links and deliver bounded BOP card, detail, relation, and ontology-binding reads through governed capabilities.

**Architecture:** Reuse one Craft-owned allowlisted primary-entity projector for work-package and detail reads. Add two focused relation capabilities and an exact ontology `node_type_binding` match; retain all existing paging and revision guards.

**Tech Stack:** Python 3.12, FastAPI, MySQL-compatible SQL, pytest, Capability V2 registry/catalog tooling.

**Spec:** `docs/superpowers/specs/2026-09-03-bop-bounded-navigation-design.md`

## Global Constraints

- Work only in `E:/Projects/ai00_v3/.worktrees/capability-v2-implementation` on branch `test`.
- Do not modify the frontend or connect to/write the production database.
- All inputs and outputs stay closed and resource bounded.
- Never accept a caller-supplied table or column name.
- Preserve stable IDs, required fields, error semantics, and current pagination.
- Do not mark machine verification as human approval.

---

### Task 1: TC primary entity links

**Files:**
- Modify: `plugins/craft/craft_backend/routers/_bop/entries.py`
- Test: `backend/tests/test_craft_bop_entry_bulk_change_boundary.py`

**Interfaces:**
- Consumes: `_IMPORT_ENTITY_MAP`, generated `ent_gid`, existing resource resolver.
- Produces: one `bop_entry_links` primary row for every successfully created normal entity.

- [ ] **Step 1: Add a failing import test covering line, station, process, operation, operator, and all part node types**

```python
assert [row[4] for row in cursor.link_rows] == [
    "bop_line", "bop_station", "bop_process", "bop_steps", "bop_operator",
    "pbom_part", "pbom_part", "pbom_part", "pbom_part",
]
assert all(row[3] for row in cursor.link_rows)
```

- [ ] **Step 2: Run the focused test and confirm it fails because normal links are absent**

Run: `python -m pytest backend/tests/test_craft_bop_entry_bulk_change_boundary.py -q`

- [ ] **Step 3: Assign `link_entity_gid = ent_gid` only after choosing a normal entity mapping**

```python
else:
    entity_info = _IMPORT_ENTITY_MAP.get(node_type)
    if entity_info:
        link_entity_gid = ent_gid
```

- [ ] **Step 4: Run the import suite and confirm resource staging behavior still passes**

Run: `python -m pytest backend/tests/test_craft_bop_entry_bulk_change_boundary.py -q`

### Task 2: Shared bounded primary-entity projection

**Files:**
- Modify: `plugins/craft/craft_backend/services/bop_navigation.py`
- Modify: `plugins/craft/craft_backend/capabilities/contracts.py`
- Test: `backend/tests/test_craft_bop_navigation_repository.py`
- Test: `backend/tests/test_craft_bop_navigation_capabilities.py`

**Interfaces:**
- Produces: `primary_link`, `primary_link_count`, `entity_data`, decoded entry metadata and card media.
- Consumes: fixed link-type-to-table SQL projection owned by Craft.

- [ ] **Step 1: Add failing repository tests for bounded card projection and closed missing/unknown entity degradation**

```python
assert result["nodes"][0]["primary_link"]["link_gid"] == "link-1"
assert result["nodes"][0]["entity_data"]["standard_time"] == 12.5
assert result["nodes"][1]["entity_data"] is None
```

- [ ] **Step 2: Add failing contract tests requiring only the new stable envelope fields while keeping card properties optional**

```python
node_schema = descriptor.output_schema["properties"]["nodes"]["items"]
assert "entity_data" in node_schema["properties"]
assert "entity_data" not in node_schema["required"]
```

- [ ] **Step 3: Run navigation tests and observe the expected missing-field failures**

Run: `python -m pytest backend/tests/test_craft_bop_navigation_repository.py backend/tests/test_craft_bop_navigation_capabilities.py -q`

- [ ] **Step 4: Extend the page entry query and batch link query using fixed joins and decode the closed projections**

The page query includes entry-owned `meta`, media, and BOM key. The batch link query returns all existing link rows plus exactly one allowlisted primary card per page entry. It must keep `entry_gid IN (...)` restricted to the returned page.

- [ ] **Step 5: Run navigation tests and retain the existing cursor/page-size assertions**

Run: `python -m pytest backend/tests/test_craft_bop_navigation_repository.py backend/tests/test_craft_bop_navigation_capabilities.py -q`

### Task 3: Entry detail primary entity closure

**Files:**
- Modify: `plugins/craft/craft_backend/services/bop_navigation.py`
- Modify: `plugins/craft/craft_backend/capabilities/contracts.py`
- Test: `backend/tests/test_craft_bop_navigation_repository.py`

**Interfaces:**
- Consumes: Task 2 primary-card normalizer.
- Produces: detail `entry` containing the same optional governed card fields as page nodes.

- [ ] **Step 1: Add failing detail tests for card data, primary identity, missing entities, and the 500-link limit**

```python
assert result["entry"]["entity_data"]["operation_code"] == "OP-10"
assert result["entry"]["primary_link"]["link_type"] == "bop_steps"
```

- [ ] **Step 2: Run the detail tests and verify the failure is missing primary projection**

Run: `python -m pytest backend/tests/test_craft_bop_navigation_repository.py -q`

- [ ] **Step 3: Project the primary entity from the already-bounded detail link set and fixed entity query**

Do not increase the 500-link ceiling and do not expose raw rows.

- [ ] **Step 4: Run repository and capability contract tests**

Run: `python -m pytest backend/tests/test_craft_bop_navigation_repository.py backend/tests/test_craft_bop_navigation_capabilities.py -q`

### Task 4: Atomic relation reads

**Files:**
- Create: `plugins/craft/craft_backend/capabilities/bop_entry_relations.py`
- Modify: `plugins/craft/craft_backend/capabilities/__init__.py`
- Modify: `plugins/craft/craft_backend/capabilities/contracts.py`
- Modify: `plugins/craft/craft_backend/capabilities/provider.py`
- Modify: `plugins/craft/craft_backend/routers/_bop/entries.py`
- Test: `backend/tests/test_craft_bop_entry_relations.py`
- Test: `backend/tests/test_craft_bop_entry_legacy_read_boundary.py`

**Interfaces:**
- Produces: `craft.bop.entry.relation.list@1` and `craft.bop.linked_entity.detail.get@1`.
- Consumes: entry/version revision, fixed target projections, Capability execution budgets.

- [ ] **Step 1: Add failing tests for direct/recursive pagination, custom/resource links, deleted rows, missing entities, and invalid scope**

```python
assert result.data["items"][0]["target_ref"] == {"type": "pbom_part", "gid": "part-1"}
assert result.data["next_cursor"] is not None
```

- [ ] **Step 2: Run the new test module and confirm capabilities are not registered**

Run: `python -m pytest backend/tests/test_craft_bop_entry_relations.py -q`

- [ ] **Step 3: Implement fixed, revision-pinned, keyset-paged repository functions and closed schemas**

Recursive SQL starts from one entry in one version and joins descendants with `version_gid` predicates on both anchor and recursive terms. Entity detail resolves by link GID and allowlisted type only.

- [ ] **Step 4: Route the existing REST compatibility endpoints through the new atomic capabilities**

Remove `entry_links` and `entity_detail` from the legacy dispatcher enum after no backend route references them. Keep unrelated legacy operations unchanged.

- [ ] **Step 5: Run relation and legacy-boundary tests**

Run: `python -m pytest backend/tests/test_craft_bop_entry_relations.py backend/tests/test_craft_bop_entry_legacy_read_boundary.py -q`

### Task 5: Deterministic BOP node-type ontology binding

**Files:**
- Modify: `plugins/ontology/ontology_backend/concepts.py`
- Modify: `plugins/craft/craft_backend/routers/ontology.py`
- Test: `backend/tests/test_ontology_concept_capabilities.py`
- Create: `backend/tests/test_craft_ontology_schema_route.py`

**Interfaces:**
- Produces: exact `matched_by=node_type_binding` resolution and release-pinned schema lookup.
- Consumes: immutable release objects with `node_type_binding`.

- [ ] **Step 1: Add failing tests for every governed BOP node type and for the Craft route's nested result parsing**

```python
assert resolve_concept({"term": "operation"}, CONTEXT).data["matched_by"] == "node_type_binding"
assert calls[1] == ("ontology.concept.get", {"stable_gid": "concept.operation", "kind": "concept", "view": "schema", "release_gid": "rel1"})
```

- [ ] **Step 2: Run both ontology test modules and observe exact binding/route failures**

Run: `python -m pytest backend/tests/test_ontology_concept_capabilities.py backend/tests/test_craft_ontology_schema_route.py -q`

- [ ] **Step 3: Add exact unique `node_type_binding` matching before human name aliases and fix the Craft result path**

Ambiguous duplicate bindings return `ambiguous`; absent bindings continue to existing exact-name and fuzzy-candidate behavior. Pass the resolved release GID into `concept.get`.

- [ ] **Step 4: Run ontology tests**

Run: `python -m pytest backend/tests/test_ontology_concept_capabilities.py backend/tests/test_craft_ontology_schema_route.py -q`

### Task 6: Governance artifacts and verification

**Files:**
- Regenerate: `docs/capabilities/catalog.v2.json`
- Regenerate: `docs/capabilities/*.md`
- Regenerate: `backend/tests/acceptance/fixtures/case-manifest.json`
- Regenerate: provider freeze and governance lineage artifacts required by repository checks.

**Interfaces:**
- Consumes: all production and test changes from Tasks 1-5.
- Produces: current provider hashes, Catalog release, docs, acceptance manifest, and machine evidence.

- [ ] **Step 1: Run the complete focused BOP/ontology regression**

Run: `python -m pytest backend/tests/test_craft_bop_entry_bulk_change_boundary.py backend/tests/test_craft_bop_navigation_repository.py backend/tests/test_craft_bop_navigation_capabilities.py backend/tests/test_craft_bop_entry_relations.py backend/tests/test_craft_bop_entry_legacy_read_boundary.py backend/tests/test_ontology_concept_capabilities.py backend/tests/test_craft_ontology_schema_route.py -q`

- [ ] **Step 2: Regenerate provider freeze, Catalog, capability docs, and acceptance manifest using repository scripts**

Run the repository's existing checked generators; do not edit generated hashes manually.

- [ ] **Step 3: Run Catalog/docs/domain checks and offline strict acceptance**

Record pre-existing unrelated failures separately; no new Craft or Ontology failure may remain.

- [ ] **Step 4: Inspect the final diff for frontend, secrets, production configuration, or unrelated changes**

Run: `git status --short` and `git diff --check`.

- [ ] **Step 5: Commit the reviewed backend change on `test`**

```powershell
git add -- <explicit reviewed files>
git commit -m "fix(craft): close bounded BOP navigation projections"
```
