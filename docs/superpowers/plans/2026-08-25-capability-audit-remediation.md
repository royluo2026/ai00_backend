# Capability Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the 2026-08-25 audit blockers by making route evidence scope-consistent, binding runtime evidence to the current commit, making Catalog metadata semantically truthful, and reducing frontend legacy REST consumers in tested route-family batches.

**Architecture:** Keep legacy REST adapters as Gateway-backed compatibility paths while moving browser consumers to `/api/v1/capabilities/{id}:invoke`. Treat `web_route_inventory.json` as generated scanner evidence and `legacy_route_inventory.json` as the reviewed exception ledger; they are validated independently. Add structured consumer metadata at the descriptor boundary without changing business payload schemas.

**Tech Stack:** Python 3.12, Pydantic, pytest, JSON governance artifacts, vanilla JavaScript, Node syntax checks.

**Spec:** `docs/governance/atomic-capability-spec-v2.md` and `docs/audits/2026-08-25-atomic-capability-code-audit.md`

## Global Constraints

- Do not modify production databases, Catalog storage, permissions, or external systems.
- Every frontend migration must preserve the existing response shape or normalize the Capability response locally.
- Every production-code change gets a failing focused test first, then a passing test.
- The full web root is `E:\Projects\ai00\workmanship-web`; package-only scans are supplementary, not release evidence.
- Preserve compatibility routes until all active consumers are migrated or an explicit dated exception is recorded.

---

### Task 1: Make route evidence and legacy ledger deterministic

**Files:**
- Modify: `backend/capability_v2/consumer_routes.py`
- Modify: `backend/capability_v2/completion.py`
- Modify: `docs/governance/legacy_route_inventory.json`
- Modify: `docs/governance/capability-coverage-review/generated/web_route_inventory.json`
- Test: `backend/tests/test_capability_v2_completion.py`
- Test: `backend/tests/test_capability_v2_route_inventory.py`

**Interfaces:**
- `scan_web_routes(root, roots=(".",), ...)` remains the authoritative full-web scan.
- `evaluate_completion(..., web_root=...)` continues to compare generated scan evidence separately from the reviewed legacy ledger.
- `legacy_route_inventory.json` contains one reviewed entry per unique legacy `(route_path, method)` family, with owner, target capability, deadline, source, and allowed consumers.

- [ ] **Step 1: Write the failing tests**

Add assertions that a full-root scan includes both `packages/` and `web/`, that generated evidence drift is detected independently of legacy-ledger validation, and that the ledger rejects an active legacy route missing a concrete deadline or target capability.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run: `python -m pytest --basetemp E:\Projects\ai00_v3\.pytest-run-route-ledger-red -p no:cacheprovider backend/tests/test_capability_v2_completion.py backend/tests/test_capability_v2_route_inventory.py -q --tb=short`

Expected: FAIL on the new scope/independence assertions before implementation.

- [ ] **Step 3: Implement the minimum route-evidence fix**

Keep the generated inventory comparison in `_web_route_inventory_drift`; expose the full-root scan in the release-gate invocation and populate `legacy_route_inventory.json` from normalized route families rather than treating the generated scanner artifact as the ledger.

- [ ] **Step 4: Regenerate and verify**

Run the route inventory generator against `E:\Projects\ai00\workmanship-web`, then rerun the focused tests and assert `web_route_inventory_drift:0`.

- [ ] **Step 5: Commit**

Commit as `fix: align web route evidence and legacy ledger`.

### Task 2: Make Catalog governance metadata semantically valid

**Files:**
- Modify: `backend/capability_v2/contracts.py`
- Modify: `backend/capability_v2/catalog.py`
- Modify: `backend/capability_v2/catalog_audit.py`
- Modify: `backend/capability_v2/descriptor_adapter.py`
- Modify: `docs/governance/business_capability_ledger.json`
- Test: `backend/tests/test_capability_v2_catalog_audit.py`

**Interfaces:**
- `consumer_refs` becomes a tuple of structured records with `consumer_id`, `consumer_type`, and `version_constraint`.
- Provider descriptors without a verified consumer must use an explicit `no_consumer_reason` rather than `exposure:*` placeholders.
- `business_effect` and `side_effects` remain strings but must not silently fall back to `description` or a generic read/write sentence for stable descriptors.

- [ ] **Step 1: Write failing catalog-audit tests**

Add tests rejecting `consumer_refs=["exposure:web"]`, rejecting a stable descriptor whose `business_effect == description`, rejecting generic side-effect text, and accepting a descriptor with a concrete consumer record or `no_consumer_reason`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest --basetemp E:\Projects\ai00_v3\.pytest-run-catalog-red -p no:cacheprovider backend/tests/test_capability_v2_catalog_audit.py -q --tb=short`

Expected: FAIL against the current string fallback and description fallback.

- [ ] **Step 3: Implement structured metadata and strict audit rules**

Update the Pydantic contract and deterministic projection, remove the placeholder fallbacks for stable descriptors, and make the audit report concrete semantic failures rather than only empty-field failures.

- [ ] **Step 4: Populate the business capability ledger and regenerate projections**

Register the existing business capability nodes and the verified consumers already migrated in `flow_editor.js`, `factory_info.html`, `project_info.html`, and `my_files.js`; do not invent consumers for still-legacy callers.

- [ ] **Step 5: Run catalog checks**

Run: `python backend/scripts/build_capability_catalog.py --check` and `python -m pytest --basetemp E:\Projects\ai00_v3\.pytest-run-catalog-green -p no:cacheprovider backend/tests/test_capability_v2_catalog_audit.py -q --tb=short`.

- [ ] **Step 6: Commit**

Commit as `fix: enforce truthful capability consumer metadata`.

### Task 3: Bind fresh runtime evidence to the current revision

**Files:**
- Modify: `backend/scripts/check_capability_v2_release_gate.py`
- Modify: `backend/governance/capability_v2_completion.json` only if the evidence path needs correction
- Test: `backend/tests/test_capability_v2_completion.py`
- Create: current-commit runtime evidence under `.runtime/` (untracked, not committed)

**Interfaces:**
- Evidence records include the exact current backend commit, catalog release, snapshot/test-run identifiers, and no `not_run`/`skipped` cases.

- [ ] **Step 1: Write a failing evidence-binding test**

Add a test that a release report with a stale `git_commit` is rejected even when all static checks pass.

- [ ] **Step 2: Run RED**

Run: `python -m pytest --basetemp E:\Projects\ai00_v3\.pytest-run-evidence-red -p no:cacheprovider backend/tests/test_capability_v2_completion.py -q --tb=short`.

- [ ] **Step 3: Implement evidence revision validation**

Require the report commit to equal the evaluated repository revision and preserve the existing strict failure behavior for skipped/not-run cases.

- [ ] **Step 4: Generate fresh evidence**

Run the offline strict acceptance and release-gate scripts against the current `test` revision; keep generated evidence in `.runtime/` and do not stage it unless the repository’s existing evidence policy explicitly requires it.

- [ ] **Step 5: Commit code-only changes**

Commit as `fix: bind release evidence to evaluated revision`.

### Task 4: Continue frontend migration by route family

**Files:**
- Modify in batches: `packages/craft-plugin/web/ebom/ebom.js`, `packages/craft-plugin/web/pbom_check/pbom_check.js`, `packages/craft-plugin/web/project/project.js`, `packages/craft-plugin/web/bop/bop.js`, `packages/craft-plugin/web/gbop/gbop.js`, `web/ontology/ontology.js`, `web/org_mgmt/org_mgmt.js`, `web/workbench/workbench.js`
- Modify: generated `docs/governance/capability-coverage-review/generated/web_route_inventory.json`
- Test: Node syntax checks for each changed JavaScript file and `backend/tests/test_capability_v2_route_inventory.py`

**Interfaces:**
- Reads use the exact read Capability and normalize its response locally.
- Writes use atomic change Capabilities and preserve expected-version/idempotency requirements.
- No frontend call is redirected to a generic Capability merely because its name resembles the route; the provider contract must match first.

- [ ] **Step 1: Write a failing route-family regression test**

Add scanner assertions for each migrated family that the source contains a Gateway capability invocation and no direct legacy call for the migrated operation.

- [ ] **Step 2: Migrate one family at a time**

Start with EBOM, then project reads/writes, then BOP/GBOP reads whose Capability contracts are already exposed to web. Leave ontology and ambiguous factory compatibility routes registered as legacy until a provider contract is verified.

- [ ] **Step 3: Verify each batch**

Run `node --check` on changed files, refresh the inventory, and run the focused route tests before starting the next family.

- [ ] **Step 4: Commit each batch**

Use commits `feat: migrate ebom web consumers`, `feat: migrate project web consumers`, and `feat: migrate governed bop readers` as applicable.

### Task 5: Remove or quarantine EBOM legacy dead code

**Files:**
- Modify: `plugins/craft/craft_backend/routers/ebom.py`
- Modify: `backend/tests/test_craft_ebom_change_boundary.py`
- Test: `backend/tests/test_craft_ebom_change_boundary.py`

**Interfaces:**
- Active route functions remain unchanged and continue to invoke atomic Gateway capabilities.
- `_legacy_*` SQL helpers are removed only after tests stop requiring their presence; no legacy SQL is reintroduced.

- [ ] **Step 1: Replace presence assertions with active-route assertions**

Test that the decorated snapshot/part routes invoke the atomic capabilities and that no `_legacy_*` function is reachable from the router module.

- [ ] **Step 2: Run RED**

Run: `python -m pytest --basetemp E:\Projects\ai00_v3\.pytest-run-ebom-red -p no:cacheprovider backend/tests/test_craft_ebom_change_boundary.py -q --tb=short`.

- [ ] **Step 3: Delete the unreferenced SQL helpers**

Remove only the unreferenced `_legacy_*` functions; preserve active DTOs and shared validation used by decorated routes.

- [ ] **Step 4: Run GREEN and commit**

Run the focused test and commit as `refactor: remove ebom legacy SQL helpers`.

## Verification Gate

Before claiming the audit is closed, run:

```powershell
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/check_domain_dependencies.py
python -m pytest --basetemp E:\Projects\ai00_v3\.pytest-run-capability-audit -p no:cacheprovider backend/tests/test_capability_v2_completion.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/test_capability_v2_route_inventory.py backend/tests/test_craft_ebom_change_boundary.py -q --tb=short
python backend/scripts/check_capability_v2_release_gate.py --web-root E:\Projects\ai00\workmanship-web
```

The release gate must report `web_route_inventory_drift:0`, zero stale-evidence failures, and zero unregistered legacy route families. Remaining legacy consumers may only remain if their ledger entries are explicit, dated, and approved.
