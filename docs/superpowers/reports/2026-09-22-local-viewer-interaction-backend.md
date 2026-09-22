# Task 1 backend implementation record

Plan: `docs/superpowers/plans/2026-09-22-local-viewer-interaction.md`.
Spec: `docs/superpowers/specs/2026-09-22-local-viewer-interaction-design.md`.
Scope: B Python/server/migration/tests and Provider documentation only.

## Approved 0029 governance correction checkpoint

Implemented without changing the grant/audit wire or copying governance business
registry state. New grant evidence commits with grant allocation/signing and links
the trusted Gateway outcome operation. It retains signed grant JSON/digest, exact
authorization and per-operation descriptors/version GIDs/business hashes, Catalog
release/hash and Provider artifact. Explicit mappings bind visibility/selection to
their respective existing `simulation.vismockup.node.*.change.apply@1` descriptors.
Missing trusted binding fails closed. Audit validates persisted proof integrity and
operation membership; it does not consult current operation constants. Old grants
without evidence fail closed rather than receiving invented provenance.

Correction implementation paths:

- `plugins/simulation/simulation_backend/application/viewer_interaction.py`
- `plugins/simulation/simulation_backend/data/viewer_interaction_repository.py`
- `plugins/simulation/simulation_backend/capabilities/provider.py`
- `backend/db/migrations/domains/simulation/0029_viewer_grant_evidence.sql`
- `backend/scripts/prepare_viewer_interaction_test.py`
- `backend/capability_v2/official_domains.json` (Simulation artifact hash only)
- `backend/tests/test_viewer_interaction_evidence.py`, audit/repository/migration/startup tests
- Unpublished `docs/governance/local-viewer-interaction-candidate/` assets only

Final targeted regression: **171 passed**, two pre-existing SQLite datetime
deprecation warnings, 27.25s. Command is the earlier 154-test command below plus
`backend/tests/test_viewer_interaction_evidence.py` and
`backend/tests/test_viewer_interaction_startup.py`. Tests include real temporary
SQLite rollback, missing/tampered proof, signed grant digest, wrong operation,
historical operations independent of current constants, trusted binding failures,
and batch rollback. Startup test resolves both operation bindings against the
actual local unpublished Catalog assembly and validates frozen Provider artifacts.
The migration helper's apply branch was tested with a recording connection for
0028 and 0029 independently, not a live database. Initial sandbox-wide runs had
Windows temporary-directory ACL setup errors (one run: 79 passed/89 setup errors);
the final offline run outside that sandbox passed all 171 tests. No product-code
workaround was introduced for those environment errors.

Checks: docs generator `--check` passed; domain migration discovery `--check`
found 29 migrations; scoped `git diff --check` passed with line-ending notices.
0028 SHA-256 remains `f4eb0d3c3dfb6f3fbf839bbab26ac31ba0598603f1fd7ed7ce39dbf6ea77971a`.
0029 checksum: `500f4532fb576face066d5ce968c81a3d288f9beaaf28f07cee6269fed38404b`.
Simulation artifact: `sha256:068d72d59fd28ced456a74344e7a6073fe53baae9e7f409cc115f387b326f5e9`.
Unpublished candidate: `rel_1e5489e8a50f1ef0ba736e35797e08a2`.

Parent/operator commands from this backend worktree (apply **not run** by worker):

```powershell
python -m backend.scripts.prepare_viewer_interaction_test --check --migration 0029
python -m backend.scripts.prepare_viewer_interaction_test --apply --migration 0029 --env-file E:/Projects/ai00_v3/workmanship-backend/backend/.env
```

Only `test_workmanship_sim_viewer_grant_evidence` plus the prefixed migration ledger
are written by that selected migration. No apply-all path, production table write,
deployment, restart, commit or released-snapshot edit was performed. Backend target
is `E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`; the parent's
runner remains `E:/Projects/ai00_v3/.runtime/run_current_test_backend.py` (unchanged).
Machine tests passed; implementation correction was authorized. Native 0029/runtime
verification and formal release approval remain **unverified**. No Snapshot or
authenticated business approval is invented; `cv2_` catalog identities are not
numeric governance-store identities.

## Delivered

- Registered `simulation.viewer.interaction.scope.get@1` and `authorize@1` as
  owner-authenticated web-only experimental capabilities. The existing bounded
  grant signer and repository remain authoritative; source lookup reuses scope
  validation without allocating a grant. Renewals read no historical launch result.
- Registered launch request/atom major 2 with the existing current-open receipt
  contract. The request builder selects `teamcenter.visualization.launch@2` and
  uses a distinct plan identity from major 1. Explicit fresh-confirmation handling
  also recognizes major 2 without allowing unknown-outcome retries.
- Added bind major 2 without `identity_operation_id`; verifies persisted signed
  current-open evidence under the same workspace/device/plan transaction as the
  live binding, source association, document and workspace revision, and
  idempotency response. Existing bind major 1 remains compatible.
- Added closed device-signed audit models, streaming 1MiB HTTP receiver and
  transactional device authentication, signature validation, grant ownership,
  event deduplication and commit-before-ack storage. Historical expired/old-runtime
  grants can upload under current device authentication. Changed duplicate events
  roll back the whole batch.
- Completed additive 0028 with the audit event table and prepared a fixed-prefix,
  single-migration `test_` runner. This worker did not run a real DB migration;
  the parent subsequently reported successful application of 0028 to `test_`
  (checksum prefix `f4eb0d3...`, no production tables).
- Added explicit Provider governance metadata and transport declaration. Updated
  only the current Simulation artifact hash in `official_domains.json` and
  generated an unpublished five-capability review subset with the existing
  Catalog/docs tools. Released snapshots were not modified.

Exact APIs, transport envelope and migration commands are in
`docs/governance/local-viewer-interaction-candidate/README.md`.

## Edited implementation files

- `backend/contracts/viewer_interaction_v1.py`
- `backend/db/migrations/domains/simulation/0028_viewer_interaction.sql`
- `backend/routers/simulation_connector.py`
- `backend/scripts/prepare_viewer_interaction_test.py`
- `backend/capability_v2/official_domains.json` (Simulation hash only)
- `plugins/simulation/simulation_backend/capabilities/viewer_interaction.py`
- `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- `plugins/simulation/simulation_backend/capabilities/connector_contracts.py`
- `plugins/simulation/simulation_backend/capabilities/live_documents.py`
- `plugins/simulation/simulation_backend/capabilities/provider.py`
- `plugins/simulation/simulation_backend/data/connector_repository.py`
- `plugins/simulation/simulation_backend/data/workspace_repository.py`
- `plugins/simulation/simulation_backend/data/viewer_interaction_repository.py`

Existing grant application/signer, current-open evidence verifier and common
grant fixture were read and reused. Their pre-existing dirty edits were preserved.
No `local-runtime` or F files were edited by this worker.

## Verification

Initial existing grant/SQL baseline: **31 passed**.
New behavior was implemented after observed failing tests for missing Provider
registration, v2 binding/atomic association, audit receiver and migration entry.

Final focused run: **154 passed**, two SQLite datetime adapter deprecation
warnings, no failures. Command (temporary directory omitted here):

```powershell
python -m pytest plugins/simulation/tests/test_viewer_interaction_authorization.py plugins/simulation/tests/test_viewer_interaction_provider.py plugins/simulation/tests/test_viewer_opened_source_binding.py plugins/simulation/tests/test_teamcenter_opened_source_evidence.py plugins/simulation/tests/test_live_document_binding_repository.py plugins/simulation/tests/test_live_document_capabilities.py backend/tests/test_viewer_interaction_repository.py backend/tests/test_viewer_interaction_audit.py backend/tests/test_viewer_interaction_migration.py backend/tests/test_connector_runtime_control_plane.py backend/tests/test_simulation_connector_http_api.py -q -p no:cacheprovider
```

Existing SQL/runtime/evidence regression: **210 passed, 162 skipped**:

```powershell
python -m pytest backend/tests/test_simulation_connector_runtime_v2_sql.py plugins/simulation/tests/test_teamcenter_launch_evidence.py plugins/simulation/tests/test_live_document_identity_evidence.py backend/tests/test_connector_runtime_sessions_v2.py -q -p no:cacheprovider
```

Additional migration-apply boundary and full local startup Catalog validation:
**7 passed** (includes five migration tests from the 154-test run):

```powershell
python -m pytest backend/tests/test_viewer_interaction_migration.py backend/tests/test_viewer_interaction_startup.py -q -p no:cacheprovider
```

The migration apply test runs the actual standard migration executor with a
recording SQL connection; translated DDL is also executed twice in temporary
SQLite. This does not prove native MySQL/OceanBase DDL, concurrency or row locks.
The optional native SQL tests skipped because `AI00_SIMULATION_TEST_DB_URL` was
not configured. No temporary SQLite result is represented as native DB evidence.

The startup test uses `build_capability_registry`, validates frozen Provider
hashes and reproduces the existing local runner's published/extension/experimental
Catalog assembly: **825 descriptors**, all five new contracts resolved. It does
not execute the runner, which would write deployment manifests and start Uvicorn.

Additional checks passed:

- `python -m backend.scripts.prepare_viewer_interaction_test --check`
- `python -m backend.scripts.run_domain_migrations --domain simulation --check`
- Generated candidate docs check (`generate_capability_docs --check` with candidate paths).
- Scoped `git diff --check` (only existing Windows line-ending notices).

## Decisions and remaining runtime verification

Ruling: retain and extend the existing dirty worktree. The parent's delegation
restricted this worker from commits, resets, restarts and deployment; this was
not a prohibition on the parent's user-authorized deployment/restart work.
No user changes were removed. The parent handles authorized deployment.

Ruling: implement only assigned Task 1 B ownership; page, pipe and adapter work
remain with their assigned workers. The approved shared protocol was not changed.

Ruling: align the old tree-request schema assertion with its already-existing
optional `expected_document_session` field. Preserve that pre-existing schema
change; do not alter the legacy forwarding path in this Task 1 implementation.

Final review: self-review (no subagent tool). Checked scope ownership and locks,
v1 compatibility, rollback boundaries, signed/closed audit limits, generation
allocation and low-frequency lookups. A separate parent adapter review is outside
this worker's review scope.

Scoped machine checks passed. Human approval covers implementation, not a formal
production release. At this worker's checkpoint, runtime verification was not
performed. The parent's later verification document supersedes that checkpoint:
the parent reports 67 targeted tests passed and native 0028 `test_` migration
applied successfully. Deployed backend/AppHost, real model interaction and latency
require the parent's runtime verification; this worker makes no claim for them.
The five-capability candidate is review material, not a complete publishable release.
