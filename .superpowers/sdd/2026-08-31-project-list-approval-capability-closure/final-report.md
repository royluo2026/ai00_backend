# Project/List approval capability closure — final report

## Frozen inputs

- Backend implementation baseline: `614805f59294006b8802ae01869dc9d7fe3cf694`.
- Frontend evidence revision: `69e5e00054d3c1cff635fe41fcb96fbe150d25fb`.
- Frontend route evidence is pinned to Git blobs, not the mutable worktree:
  - shared client source/dist: `a179dc94009217bafb32b7f9571d3c052bb01d56`
  - list sidebar source/dist: `5441dcc79b2eddf24af8b87f0fa959e42f3e216f`
  - BOP source: `9f99585bb577e331241743027a631e84bf77ec4b`; dist: `313b6f9c06920a8d905099e40f2754be71a5dba8`
  - approval source: `7903b987d7f27b5d05b94181cf0361eca0abad6f`; dist: `67019bf6dec52d8be278b8dda44e76299269d870`

The closure manifest derives the prior inventory from the pinned backend baseline and the remainder from the canonical scanner. It proves `14 groups / 17 occurrences - 3 groups / 3 occurrences = 11 groups / 14 occurrences`. The three closed groups are `GET /api/lists`, `DELETE /api/lists/{dynamic}`, and `POST /api/approval/orders/{dynamic}/reject`. Their legacy route literals/fallbacks are absent. Approval rejection has no Web notification publication side effect.

The evidence also pins exact source hashes, line spans, and snippet hashes for the Project/Craft providers, input/output contracts, Project application operations, approval owner service, transactional outbox repository, `0002_approval_notification_outbox.sql`, Gateway idempotency context, and the real Gateway integration test. No unresolved Craft/Agent finding was relabelled, and no advisory was suppressed.

## Red/green development evidence

The first source-derived tests failed before the builder was changed:

```text
AttributeError: module ...build_craft_agent_project_structural_web_remediation has no attribute 'build_project_closure_evidence'
2 failed
```

After adding exact source evidence, the full arithmetic assertion failed against the old generated manifest:

```text
ValueError: final three-domain inventory drift
```

The structural-plan regression then exposed its stale target (`craft.bop.version.search@1`), and migration regeneration exposed the old invariant that prohibited a source-proved later remediation:

```text
migration_final_reclassification_mismatch:POST:/api/approval/orders/{dynamic}/reject
```

Round-one review tests then failed on six intended integrity boundaries: the missing source-derived list/outbound parsers, clean replay without a stored remediation artifact, forged/stale remediation acceptance, the missing committed Integration factory, and the missing machine acceptance result. The repair derives the complete list mapping and fail-closed branch from source/dist Git blobs, validates the rejection flow's exact allowed outbound call set, and rebuilds the canonical remediation manifest before historical migration audit. The final focused/adversarial Project/Web suite finished with `71 passed in 93.63s`.

## Regeneration and check commands

`WEB_ROOT` below is `E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance`.

```powershell
python backend\scripts\refresh_web_wrapper_contracts.py --web-root $WEB_ROOT --write
python backend\scripts\check_web_capability_routes.py --web-root $WEB_ROOT --write
python backend\scripts\build_web_route_root_cause_ledger.py --web-root $WEB_ROOT --write
python backend\scripts\build_atomic_web_contracts.py --write
python backend\scripts\build_craft_agent_project_structural_web_remediation.py --web-root $WEB_ROOT --write
python backend\scripts\build_existing_capability_web_migrations.py --web-root $WEB_ROOT --write
python backend\scripts\check_structural_remediation_plan.py --write
python backend\scripts\build_special_web_residual_contracts.py
python backend\scripts\freeze_official_domains.py
python backend\scripts\build_capability_catalog.py --write
python backend\scripts\generate_capability_docs.py --write
python backend\scripts\build_capability_acceptance_manifest.py --write

python backend\scripts\refresh_web_wrapper_contracts.py --web-root $WEB_ROOT --check
python backend\scripts\check_web_capability_routes.py --web-root $WEB_ROOT --check
python backend\scripts\build_web_route_root_cause_ledger.py --web-root $WEB_ROOT --check
python backend\scripts\build_atomic_web_contracts.py --check
python backend\scripts\build_craft_agent_project_structural_web_remediation.py --web-root $WEB_ROOT --check
python backend\scripts\build_existing_capability_web_migrations.py --web-root $WEB_ROOT
python backend\scripts\build_special_web_residual_contracts.py --check
python backend\scripts\check_structural_remediation_plan.py --check
python backend\scripts\freeze_official_domains.py --check
python backend\scripts\build_capability_catalog.py --check
python backend\scripts\generate_capability_docs.py --check
python backend\scripts\build_capability_acceptance_manifest.py --check
```

Before provider-dependent commands, set:

```powershell
$env:PYTHONPATH="$PWD\plugins\integration"
$env:AI00_INTEGRATION_ADAPTER_FACTORY='backend.tests.support.integration_catalog_factory:build'
```

The committed no-I/O factory is `backend/tests/support/integration_catalog_factory.py`, SHA-256 `sha256:67009b68b2ca32693174cb017317904a76ae6a76ccb851d8a7a651f547b41882`. It is test support only and has no production runtime registration.

## Verification

Frontend evidence source:

```powershell
node scripts\test_project_list_capability_dispatch.js
node scripts\test_project_approval_reject_capability.js
node scripts\test_existing_capability_migrations.js
```

All three passed at the frozen frontend revision.

Backend focused suite:

```powershell
python -m pytest backend\tests\test_craft_agent_project_structural_remediation_manifest.py backend\tests\test_existing_capability_web_migrations.py backend\tests\test_special_web_residuals.py backend\tests\test_web_compatibility_confirmation.py backend\tests\test_project_list_approval_closure_acceptance.py plugins\project_management\tests\test_project_approval_reject_capability.py plugins\project_management\tests\test_project_approval_reject_gateway_integration.py plugins\project_management\tests\test_project_application.py plugins\project_management\tests\test_project_capabilities.py -q
```

Result: `71 passed in 93.63s`, including the committed factory/report identity assertions. Adversarial cases mutate both Project mapping and fail-closed source, add a renamed notification publisher, substitute a notification capability, supply a superficially plausible partial remediation document, and supply a stale revision with a recomputed self-hash.

Domain gates:

```powershell
python backend\scripts\check_domain_dependencies.py
python backend\scripts\run_domain_migrations.py --domain project_management --check
python -m pytest backend\tests\test_domain_migration_runner.py plugins\project_management\tests\test_database_isolation.py -q
```

Results: dependency check passed with one explicitly reviewed test-only Gateway harness dependency and no new production dependency; Project Management reports two migrations; migration suite reports `13 passed in 0.60s`.

Strict acceptance:

```powershell
python backend\scripts\run_capability_v2_acceptance.py --mode offline --strict --report docs\acceptance\project-list-approval-capability-closure.json
```

- Status/scope: `passed` / `contract`
- Catalog release: `rel_570b28961bd996541523b75c90e3e769`
- Stable capabilities: `473`
- Declared/validated: `3311 / 3311`
- Failed/skipped: `0 / 0`
- Code commit / clean tracked tree: `553e2b7f02dfe07fd2a93330c5eeab31c6dacc26` / `true`
- Acceptance pytest summary: `3322 passed in 7.80s`
- Report ID: `sha256:60bd375b1d8410bf3518aa518c696d4f7ecd28d4ff859059fcb642756c31c84c`
- Machine report: `docs/acceptance/project-list-approval-capability-closure.json`
- Machine report SHA-256: `sha256:4b9d7f5eae8f73c3f53cfbccab200ea6c4595399fcd0466ca723b5d398779419`
- Identity manifest: `docs/acceptance/project-list-approval-capability-closure-evidence.json`
- Provider manifest: `sha256:9edaee5e8c239a586b104ceeca362045e12df6ca64c63761841549416f04065f`
- Unsuppressed global completion advisory: `coverage_invariant:stable_functions:922!=920`

Strict contract acceptance passes; the independent completion audit remains incomplete only for that pre-existing global coverage invariant.

## Generated result

- Catalog: 489 descriptors, release `rel_570b28961bd996541523b75c90e3e769`.
- Developer manual: 489 generated capability pages plus generated indexes/machine artifacts.
- Acceptance manifest: 473 stable capabilities, seven mandatory cases each.
- Route inventory: 383 total Web occurrences, 14 unresolved occurrences in 11 canonical groups.
- Structural remediation: 14 baseline groups/17 occurrences; 3/3 migrated; 11/14 unresolved.
- Existing-capability migrations: 53 groups/80 occurrences; 22 migrated and 31 reclassified.
- Atomic Web contracts: 48 groups/71 occurrences; 36 migrated and 12 reclassified.
- Special residual contracts remain 6 groups/23 occurrences.

## Residual risks

- The repository-wide stable-function count remains `922` while the frozen completion invariant expects `920`. This is reported, not hidden, and is outside this three-group closure.
- The reviewed Project test dependency exists only so the integration test can exercise the real shared Gateway. Production Project code introduces no Base Platform import.
- Eleven structural groups/fourteen occurrences remain deliberately unresolved in the canonical Craft/Agent remainder; this task neither relabels nor suppresses them.
