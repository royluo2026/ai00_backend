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
