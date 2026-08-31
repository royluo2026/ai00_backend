# Task 4 — Freeze Project/List closure evidence

## Outcome

Task 4 evidence commit: `2107e5bccd9b2f1460a0c6f3c803740b73cd3aa7` — `docs: close Project list and approval governance`.

Round-one integrity fix commit: `553e2b7f02dfe07fd2a93330c5eeab31c6dacc26` — `fix: harden Project closure evidence`.

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
- Focused/adversarial Project/Web backend suite: `71 passed in 93.63s`, including committed factory/report identity assertions.
- Project Management migration suite: `13 passed in 0.60s`; migration check reports two migrations.
- Domain dependency gate: one reviewed test-only Gateway-harness dependency, no new production dependency.
- Every requested generator `--check` passed.
- Strict offline acceptance from clean tracked commit `553e2b7f02dfe07fd2a93330c5eeab31c6dacc26`: status `passed`, 473 stable capabilities, 3,311 declared/validated, 0 failed, 0 skipped; acceptance pytest reports `3322 passed in 7.80s`.
- `git diff --cached --check` passed before the evidence commit.

Catalog release: `rel_570b28961bd996541523b75c90e3e769`.

Acceptance report ID: `sha256:60bd375b1d8410bf3518aa518c696d4f7ecd28d4ff859059fcb642756c31c84c`.

Committed factory: `backend.tests.support.integration_catalog_factory:build`, file SHA-256 `sha256:67009b68b2ca32693174cb017317904a76ae6a76ccb851d8a7a651f547b41882`.

Machine report: `docs/acceptance/project-list-approval-capability-closure.json`, SHA-256 `sha256:4b9d7f5eae8f73c3f53cfbccab200ea6c4595399fcd0466ca723b5d398779419`; its identity binding is `docs/acceptance/project-list-approval-capability-closure-evidence.json`.

## Handwritten changes

- `backend/scripts/build_craft_agent_project_structural_web_remediation.py`
- `backend/capability_v2/existing_capability_migrations.py`
- `backend/scripts/check_structural_remediation_plan.py`
- `backend/tests/test_craft_agent_project_structural_remediation_manifest.py`
- `backend/tests/test_existing_capability_web_migrations.py`
- `backend/tests/test_project_list_approval_closure_acceptance.py`
- `backend/tests/support/integration_catalog_factory.py`
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
- `docs/acceptance/project-list-approval-capability-closure.json`
- `docs/acceptance/project-list-approval-capability-closure-evidence.json`

## Round-one integrity corrections

- Clean replay order is wrapper freeze → route inventory → ledger → atomic contracts → structural remediation → existing-capability migrations → structural plan → special residuals → provider freeze → Catalog → docs → acceptance manifest. The migration audit itself rebuilds and canonically validates remediation evidence, so it does not trust or require a stored generated manifest.
- The complete `LIST_CAPABILITIES` block and `capability_not_bound` branch are parsed from pinned source/dist Git blobs. Emitted mappings are no longer builder-owned constants.
- Later remediation requires exact equality with a freshly rebuilt canonical manifest, including content hash, frontend revision, route/capability/occurrences, and all source anchors. Partial and stale/self-rehashed forgeries fail.
- The approval rejection flow permits exactly one outbound operation, `project.approval.order.reject`; legacy API, notification helpers/capabilities, and generic publish/emit/send paths fail evidence generation.
- Catalog and acceptance use the committed no-I/O test factory. The clean-run JSON report and its factory/report/provider identity manifest are committed and hash-checked.

Exact clean replay order (`$WEB_ROOT` is the frozen frontend worktree):

```powershell
python backend\scripts\refresh_web_wrapper_contracts.py --web-root $WEB_ROOT --write
python backend\scripts\check_web_capability_routes.py --web-root $WEB_ROOT --write
python backend\scripts\build_web_route_root_cause_ledger.py --web-root $WEB_ROOT --write
python backend\scripts\build_atomic_web_contracts.py --write
python backend\scripts\build_craft_agent_project_structural_web_remediation.py --web-root $WEB_ROOT --write
python backend\scripts\build_existing_capability_web_migrations.py --web-root $WEB_ROOT --write
python backend\scripts\check_structural_remediation_plan.py --write
python backend\scripts\build_special_web_residual_contracts.py
$env:PYTHONPATH="$PWD\plugins\integration"
$env:AI00_INTEGRATION_ADAPTER_FACTORY='backend.tests.support.integration_catalog_factory:build'
python backend\scripts\freeze_official_domains.py
python backend\scripts\build_capability_catalog.py --write
python backend\scripts\generate_capability_docs.py --write
python backend\scripts\build_capability_acceptance_manifest.py --write
python backend\scripts\run_capability_v2_acceptance.py --mode offline --strict --report docs\acceptance\project-list-approval-capability-closure.json
```

## Residual risks

- Strict acceptance retains the unsuppressed global completion advisory `coverage_invariant:stable_functions:922!=920`. Contract acceptance itself passed; this count is outside the three-group closure.
- Eleven Craft/Agent structural groups and fourteen occurrences remain canonical unresolved work. This task preserves their prior classification and evidence.
- The Project dependency-baseline entry covers only a test that composes the real shared Gateway; production Project modules remain domain-isolated.
- Approval recovery after a full frontend reload still relies on refresh/reconciliation because its opaque operation key is live-page state; this is unchanged from Task 3.
