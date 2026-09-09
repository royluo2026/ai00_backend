# BOP Repository Collaboration Readiness — 2026-09-09

## Scope and revisions

- Backend branch: `test`, implementation head before this report: `987ef9456764803a86a93c93c778a15debb5f5c1`
- Frontend branch: `test`, implementation head: `3ab2558509d996b4a8acbd038e70663a4a2168df`
- Target: Windows x64 Electron desktop with cloud-deployable backend.
- New Repository, Fork, Diff, VPPS, import, proposal, migration and Agent surfaces remain experimental development-catalog candidates.

## Verification evidence

| Area | Command | Result |
|---|---|---|
| Repository and Simulation focused suites | PowerShell-expanded `pytest` selection for `test_bop_repository_*`, Craft Fork/VPPS/collaboration, Simulation export/identity/PLMXML/snapshot/capture, and Agent assistant | PASS — 71 tests |
| Domain ownership, migrations, Provider loading, Capability completion | `python -m pytest backend/tests/test_domain_table_ownership.py backend/tests/test_domain_migration_runner.py backend/tests/test_capability_provider_loading.py backend/tests/test_capability_v2_completion.py -q` | PASS — 69 tests |
| Static Capability completion gate | `python backend/scripts/check_capability_v2_completion.py --static-only` | PASS — `complete: true`, zero failed checks, zero consumer bypasses, zero cross-domain SQL |
| Simulation renderer and Connector tests | `node --test packages/sim-plugin/web/cad_sim/*.test.js` | PASS — 18 tests |
| Four-column layout smoke | `node scripts/test_simulation_workspace_layout.js` | PASS |
| Test-governance web build | `npm run build:web:test-governance` | PASS — Vite build completed; existing non-module script notices remain warnings |
| Planned build alias | `npm run build:test` | NOT AVAILABLE — repository has no such script; replaced by the test-governance build above |

## Migration safety

Legacy BOP writes are unchanged during normal runtime. The lease/journal boundary activates only when `AI00_BOP_REPOSITORY_MIGRATION_FENCE_ENABLED=1`. The backfill mutates only when both `--apply` and `AI00_BOP_REPOSITORY_BACKFILL_MUTATION=1` are present. It records preliminary and final journal watermarks, drains pre-fence leases, performs an idempotent full rescan, quarantines records without project identity, reconciles unmapped records, and never enables product cutover itself.

## Governance state

- `machine_passed`: `unverified` for all new or changed candidate Capabilities. Local tests are engineering evidence and do not replace the trusted machine-attestation workflow.
- `human_approved`: `unverified`, as requested; no approval was inferred.
- `runtime_verified`: `unverified`; no trusted deployed runtime evidence was produced.
- `advisory`: `true`.
- Lifecycle: `experimental`; candidates were not promoted into a stable product release.

## Remaining runtime gates

Before production exposure, apply the additive Craft migrations through the domain DDL runner, run the backfill in a controlled maintenance window, resolve every quarantine row, obtain trusted machine/human/runtime evidence, and publish a Catalog release that contains only the approved candidate versions. The current code and build are ready for local development smoke testing, not production cutover.
