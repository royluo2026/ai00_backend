# Craft Structural Capability Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all seven remaining Craft route groups through two exact owner Capabilities and removal of five non-functional UI actions.

**Architecture:** Reuse the existing Craft rule engine and rule repository for the two real behaviors. Decommission UI actions whose legacy providers do not exist instead of mapping them to non-equivalent archive/release/waiver outcomes.

**Tech Stack:** Python 3.12, pytest, JavaScript, Node.js, Vite, Craft provider, Capability Gateway V2.

**Spec:** `docs/superpowers/specs/2026-08-31-craft-structural-capability-closure-design.md`

## Global Constraints

- Do not create equipment-delete, fixture-delete, mutable activate/suspend, or legacy deviation Capabilities.
- Do not map delete to archive, mutable lifecycle to immutable release lifecycle, or deviation to release waiver.
- Rule evaluation is bounded and accepts no executable source or SQL.
- Rule mutation uses a closed field allowlist, actor/team scope, expected revision, confirmation, idempotency, and one transaction.
- This plan reduces the canonical remainder from 11 groups / 14 occurrences to 4 groups / 5 occurrences.

---

### Task 1: Remove five dead Craft UI actions

**Files:**
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/knowledge_hub/pages/gbop_vpps.html`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/rule_mgmt/rule_mgmt.js`
- Modify: matching `dist-production` outputs.
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_craft_dead_actions_removed.js`

**Interfaces:**
- Consumes: audit disposition proving five providers are absent/non-equivalent.
- Produces: non-interactive unsupported labels where explanation is necessary and zero network paths for the five actions.

- [ ] **Step 1: Add failing DOM/network tests**

```javascript
assert.equal(findInteractiveAction('equipment-delete'), null);
assert.equal(findInteractiveAction('rule-activate'), null);
assert.equal(fetchCalls.length, 0);
```

Cover equipment delete, fixture delete, activate, suspend, and deviation.

- [ ] **Step 2: Run red**

Run: `node scripts/test_craft_dead_actions_removed.js`

Expected: FAIL because the current handlers still issue REST requests.

- [ ] **Step 3: Delete handlers and render non-interactive state**

Remove the event listeners and request construction. Keep only a static unsupported label where removing the control would make the state unclear.

- [ ] **Step 4: Verify, build, and commit**

Run the Node test, syntax checks, and `npm run build:web`.

Commit: `fix: remove unsupported Craft actions`

### Task 2: Add bounded rule-entry evaluation

**Files:**
- Modify: `plugins/craft/craft_backend/application/rules.py`
- Modify: `plugins/craft/craft_backend/capabilities/rule_engine.py`
- Modify: `plugins/craft/craft_backend/capabilities/rule_descriptors.py`
- Modify: `plugins/craft/craft_backend/capabilities/provider.py`
- Create: `backend/tests/test_craft_rule_entry_evaluate_capability.py`

**Interfaces:**
- Consumes: existing approved Craft rule checker/repository.
- Produces: `craft.rule.entry.evaluate@1` input `{rule_gid, rule_revision, entry}` and closed bounded output `{passed, rule_revision, diagnostics}`.

- [ ] **Step 1: Add failing bounds and ownership tests**

Test same-team success, cross-team not-found, revision mismatch, oversized entry rejection, timeout, diagnostic cap, and absence of raw expression/secret output.

- [ ] **Step 2: Run red**

Run: `python -m pytest backend/tests/test_craft_rule_entry_evaluate_capability.py -q`

Expected: FAIL because the exact capability is absent.

- [ ] **Step 3: Register a minimal wrapper over the existing checker**

```python
def evaluate_entry(payload, context):
    rule = repository.require_visible(payload["rule_gid"], context.user_gid, context.team_gid)
    require_revision(rule, payload["rule_revision"])
    return bounded_checker.evaluate(rule, payload["entry"], limits=RULE_EVALUATION_LIMITS)
```

Reject source/code/provider fields in the closed schema.

- [ ] **Step 4: Run tests and commit**

Run the focused test plus existing Craft rule-engine/provider suites.

Commit: `feat: add governed rule entry evaluation`

### Task 3: Add exact closed rule-definition mutation

**Files:**
- Modify: `plugins/craft/craft_backend/application/rules.py`
- Modify: `plugins/craft/craft_backend/capabilities/rule_library.py`
- Modify: `plugins/craft/craft_backend/capabilities/rule_descriptors.py`
- Modify: `plugins/craft/craft_backend/capabilities/provider.py`
- Create: `backend/tests/test_craft_rule_definition_change_capability.py`

**Interfaces:**
- Consumes: current rule repository supported-field set.
- Produces: `craft.rule.definition.change.apply@1` with `{rule_gid, expected_revision, changes}` and closed rule projection.

- [ ] **Step 1: Add failing schema/transaction tests**

```python
ALLOWED_CHANGES = {"name", "description", "severity", "enabled", "condition", "message", "scope", "tags", "priority", "category"}
```

Test each allowed field, unknown/nested executable fields, cross-team access, revision conflict, rollback, byte-equivalent replay, and changed-payload conflict.

- [ ] **Step 2: Run red**

Run: `python -m pytest backend/tests/test_craft_rule_definition_change_capability.py -q`

- [ ] **Step 3: Implement one owner transaction**

Validate `changes` against the frozen allowlist; update, increment revision, write operation/audit/result, and commit once. Do not allow browser-supplied compiled artifacts or audit fields.

- [ ] **Step 4: Run tests and commit**

Run focused rule tests and Craft provider contract tests.

Commit: `feat: govern Craft rule definition changes`

### Task 4: Migrate the two real Craft Web behaviors

**Files:**
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/packages/craft-plugin/web/lineage_view/layout_detail_panel.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/container_card/modes/container_item_detail.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/container_card/modes/mode_field_detail.js`
- Modify: matching `dist-production` outputs.
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_craft_rule_capability_migrations.js`

**Interfaces:**
- Consumes: Task 2 and Task 3 exact capabilities.
- Produces: real Web calls with no check-entry/update REST fallback.

- [ ] **Step 1: Add failing real-interaction tests**

Assert both evaluation occurrences call `craft.rule.entry.evaluate`; both update occurrences call `craft.rule.definition.change.apply` with revision/confirmation/idempotency.

- [ ] **Step 2: Replace calls and run green**

Use the shipped capability client and closed adapters; show structured timeout/conflict rather than generic success.

- [ ] **Step 3: Build and commit**

Run Node tests, syntax checks, and production build.

Commit: `feat: migrate Craft rule UI capabilities`

### Task 5: Freeze Craft closure evidence

**Files:**
- Modify: `backend/scripts/build_craft_agent_project_structural_web_remediation.py`
- Modify: `backend/tests/test_craft_agent_project_structural_remediation_manifest.py`
- Regenerate: governance evidence chain.
- Create: `.superpowers/sdd/2026-08-31-craft-structural-capability-closure/final-report.md`

**Interfaces:**
- Consumes: committed Tasks 1-4 and the Project closure evidence.
- Produces: two capability-migrated groups, five explicitly decommissioned groups, zero unresolved Craft groups, and canonical remainder 4/5.

- [ ] **Step 1: Add failing disposition/count tests**

Assert decommissioned groups are reported as `removed_dead_entry`, not `migrated`; assert real groups include provider/contract/Gateway anchors; assert `11/14 - 7/9 = 4/5`.

- [ ] **Step 2: Regenerate and run gates**

Freeze frontend, regenerate route/ledger/atomic/remediation/plan/trust/Catalog/docs/acceptance, run `--check`, Craft/Web tests, domain gates, and strict offline acceptance.

- [ ] **Step 3: Commit and request whole-plan review**

Commit: `docs: close Craft structural governance`

