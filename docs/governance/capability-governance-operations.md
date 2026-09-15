# Capability Governance Center (test-only) operations

The Governance Center is enabled only with `AI00_DEPLOYMENT_PROFILE=test-governance`.
It is a read/analyse/govern/release control plane: neither its UI nor its
database may edit or delete capability contracts. Contract changes continue
through the normal reviewed proposal workflow.

## Prerequisites

Use the dedicated OceanBase test runtime and DDL accounts, an explicit
`AI00_GID_MACHINE_ID`, and the test-only release-signing key. Never use a
production database URL, production service, or production frontend artifact.
Before a live release run, the operator must set
`AI00_GOVERNANCE_ACCEPTANCE_AUTHORIZED=true`; absence of this acknowledgement
is a deliberate fail-closed external prerequisite.

## Normal test-environment sequence

### Shared database with test-prefixed tables

The local AI00 test environment uses a shared database with `TABLE_PREFIX=test_`.
This is table-namespace isolation, not a requirement for a separate database.
Use its explicitly selected environment file for runtime connections. Keep DDL
credentials explicit in `AI00_BASE_DDL_DB_URL`; do not automatically promote a
runtime credential into a migration credential.

For that environment, set `TABLE_PREFIX=test_` together with the test-governance
profile before running the commands below. The migration command rewrites SQL
before metadata checks, including the Catalog backfill dependency, and uses a
separate test-prefixed migration ledger and lock. It accepts only exact `test_`
or the existing empty-prefix dedicated-database mode; never use empty-prefix
mode against the shared database. Source migration checksums remain unchanged.
`--check` is offline. The test Catalog release table must exist before migration
0009. Never copy production approvals into test tables to make a release pass.

If OceanBase returns error 1305 specifically for `GET_LOCK`, the default remains
fail-closed. `--externally-serialized` requires the operator to guarantee a single
migration executor for that target. It does not suppress lock timeouts, permission
errors or migration failures. A workstation mutex does not coordinate remote jobs.

The 2026-09-14 shared-test initialization required empty-table recovery on engine
`5.7.25-OceanBase-v3.2.3.3`: VARCHAR-to-VARBINARY and nullable-to-NOT-NULL changes
were rejected. Five newly created empty tables were rebuilt with binary hashes;
their empty originals remain as `test_workmanship_cg_hash_backup_0_20260914`
through `_4_20260914`. The empty snapshot hash column was recreated NOT NULL.
No evidence rows were removed or manufactured. This is not a populated-table
upgrade path. All nine ledger entries completed; replay applied zero migrations.

```powershell
$env:AI00_DEPLOYMENT_PROFILE = 'test-governance'
python backend/scripts/migrate_capability_governance_test.py --apply
python backend/scripts/run_capability_governance_scan.py --offline --output .runtime/governance-scan.json
python -m pytest backend/tests/test_capability_governance_test_profiles.py backend/tests/test_capability_governance_workflow.py -q
python backend/scripts/run_capability_governance_release_acceptance.py --base-url http://127.0.0.1:8094 --strict
python backend/scripts/check_capability_v2_completion.py --mode strict --governance-acceptance-report docs/governance/test-extension/capability-governance-release-acceptance.json
```

The strict acceptance report must contain precisely fourteen mandatory sections,
zero failed checks, and zero skipped checks. It contains only IDs and hashes;
credentials, URLs, payloads, and repair-prompt text must not be retained.

Run the bounded fast profile continuously. Run the release E2E profile only for
an authorised release candidate with isolated `E2E-<candidate>-*` fixtures and
an exact cleanup plan. A changed descriptor, evidence, catalog, or code hash
stales the proposal/release evidence and blocks release.

## Frontend and service deployment

Build both frontend profiles in `E:/Projects/ai00/workmanship-web`:

```powershell
npm test
npm run build:web:test-governance
npm run build:web:production
node scripts/test_capability_governance_build_profiles.js
```

Synchronise only `dist-test-governance/web/admin/capability_governance/` and its
test-governance `web/admin_hub/index.html` into the Capability V2 service
distribution. Do not delete unrelated `dist` files and never copy
`dist-production` into the test service. Restart only `AI00Backend-CapabilityV2`
and verify `/health`, `/ready`, and
`/web/admin/capability_governance/index.html` with
`python backend/scripts/check_frontend_deployment.py`.

Production release construction must use the production profile and then run:

```powershell
python backend/scripts/check_production_governance_exclusion.py --root <production-artifact>
```

It must prove that the Governance backend, migrations, catalog extension, UI,
and test identifiers are physically absent.

## Retention, waivers, and recovery

Keep immutable scan, analysis, test, prompt-metadata, audit, and release
reports for the configured governance retention period. Repair prompts retain
only their redacted summary and hash. Waivers require a bounded expiry and are
invalid when their code, catalog, or evidence hash changes; renew them only by a
new reviewed waiver.

On migration, static-asset, permission, scan, or release-gate failure: stop the
release, preserve the redacted report GID/hash, fix the failing controlled
input, rescan, and obtain fresh approval. For a service rollback, restore the
previous `AI00Backend-CapabilityV2` test artifact, restart that service only,
and re-run the frontend deployment check. Do not roll back by editing immutable
governance evidence or by applying any Governance artifact to production.
