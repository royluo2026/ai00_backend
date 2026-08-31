# Task 4 — Freeze Project/List closure evidence

## Outcome

Task 4 evidence commit: `2107e5bccd9b2f1460a0c6f3c803740b73cd3aa7` — `docs: close Project list and approval governance`.

The canonical structural-remediation evidence now closes exactly three source-proved Project-facing groups and occurrences:

- `GET /api/lists` → finite owner dispatch using `craft.bop.version.list@1` or `project.list.read.atomic.lists_search@1`.
- `DELETE /api/lists/{dynamic}` → finite owner dispatch using `craft.bop.version.archive@1` or `project.list.change.apply.atomic.lists_delete@1`.
- `POST /api/approval/orders/{dynamic}/reject` → `project.approval.order.reject@1`.

The count is derived from immutable inputs: `14 groups / 17 occurrences - 3 / 3 = 11 / 14`. Exact frontend commit/blobs, route absence, source/dist call sites, Project/Craft provider and contract anchors, approval service/outbox/migration/Gateway anchors, and notification-side-effect absence are pinned in the manifest.

## Red/green evidence

### Red

Source-derived tests were added before implementation and failed with:

```text
AttributeError: module ...build_craft_agent_project_structural_web_remediation has no attribute 'build_project_closure_evidence'
2 failed
```

Subsequent narrow regressions exposed:

```text
ValueError: final three-domain inventory drift
```

```text
expected craft.bop.version.list@1, found craft.bop.version.search@1
```

```text
migration_final_reclassification_mismatch:POST:/api/approval/orders/{dynamic}/reject
```

### Green

- Frozen-frontend tests: Project list dispatch, approval rejection, and existing-capability migration scripts all passed at `69e5e00054d3c1cff635fe41fcb96fbe150d25fb`.
- Focused Project/Web backend suite: `65 passed in 59.20s`.
- Project Management migration suite: `11 passed in 0.65s`; migration check reports two migrations.
- Domain dependency gate: one reviewed test-only Gateway-harness dependency, no new production dependency.
- Every requested generator `--check` passed.
- Strict offline acceptance: status `passed`, 473 stable capabilities, 3,311 declared/validated, 0 failed, 0 skipped; acceptance pytest reports `3322 passed in 7.84s`.
- `git diff --cached --check` passed before the evidence commit.

Catalog release: `rel_570b28961bd996541523b75c90e3e769`.

Acceptance report ID: `sha256:2f665f2428738ff48f4866d553086ef48c14a886f9996d269870a924102a66de`.

## Handwritten changes

- `backend/scripts/build_craft_agent_project_structural_web_remediation.py`
- `backend/capability_v2/existing_capability_migrations.py`
- `backend/scripts/check_structural_remediation_plan.py`
- `backend/tests/test_craft_agent_project_structural_remediation_manifest.py`
- `backend/tests/test_existing_capability_web_migrations.py`
- `docs/governance/web-api-lexical-non-routes.json`
- `docs/governance/domain-dependency-baseline.json`
- `docs/governance/capability-coverage-review/project-management.json`
- `.superpowers/sdd/2026-08-31-project-list-approval-capability-closure/final-report.md`

## Generated files

- `backend/capability_v2/official_domains.json`
- `backend/tests/acceptance/fixtures/case-manifest.json`
- `docs/governance/web-api-wrapper-contracts.json`
- `docs/governance/existing-capability-web-migrations.json`
- `docs/governance/web-route-root-cause-ledger.json`
- `docs/governance/capability-coverage-review/generated/web_route_inventory.json`
- `docs/governance/atomic-web-capability-contracts.json` (verified current; no final diff)
- `docs/governance/craft-agent-project-structural-web-remediation.json`
- `docs/governance/capability-v2-structural-remediation-plan.json`
- `docs/governance/capability-v2-structural-remediation-plan.md`
- `docs/governance/special-web-residual-contracts.json`
- `docs/governance/capability-catalog-lineage.json`
- `docs/governance/capability-catalog-release.json`
- `docs/capabilities/catalog.v2.json`, generated machine indexes, and 489 generated capability pages.

## Residual risks

- Strict acceptance retains the unsuppressed global completion advisory `coverage_invariant:stable_functions:922!=920`. Contract acceptance itself passed; this count is outside the three-group closure.
- Eleven Craft/Agent structural groups and fourteen occurrences remain canonical unresolved work. This task preserves their prior classification and evidence.
- The Project dependency-baseline entry covers only a test that composes the real shared Gateway; production Project modules remain domain-isolated.
- Approval recovery after a full frontend reload still relies on refresh/reconciliation because its opaque operation key is live-page state; this is unchanged from Task 3.
