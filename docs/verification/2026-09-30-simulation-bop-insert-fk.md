# Simulation BOP insert: OceanBase parent-before-child batching

## 1. Change classification
- Implementation fix: preserve the exact previewed BOP hierarchy while satisfying the database's self-referencing foreign key during bulk insertion.
- No contract, schema, permission, source-selection, or business-effect change. AI assessment is advisory.

## 2. Authoritative context inspected
- Capability: `simulation.environment.bop_projection.apply@1`; companion `simulation.environment.bop_projection.preview@1`.
- Domain/owner: simulation; Provider: `simulation.provider`, `official.simulation`, `simulation_backend.capabilities` v1.0.0; lifecycle: experimental.
- Persisted capability_version_gid, governance snapshot_gid and exact-hash approval: unverified; no identities invented.
- Read provider-owned specs in `capabilities/alternate_hierarchies.py`, published Catalog, unpublished local Catalog and local domain manifest.
- Effect: atomically insert the exact previewed Craft BOP skeleton as an editable alternate hierarchy in one owned Simulation workspace.
- Inputs: workspace/version/line/depth/name, expected row version, exact plan hash, idempotency key. Output: hierarchy identity, counts and updated workspace revision.
- Existing controls retained: `simulation.use`, user confirmation, tenant/owner scope, source/plan revalidation, optimistic revision checks, one simulation-domain transaction and persisted idempotency response.
- Existing errors retained: version_conflict, workspace_not_found, bop_projection_plan_changed, malformed/missing-parent/cyclic nodes and duplicate projection errors.
- Consumer: App 1.0.3 `packages/sim-plugin/web/cad_sim/cad_sim.js` `_openBopInsert`, via Capability Gateway preview/confirm/apply; cross-domain source reads remain through DomainClient, not SQL.
- Audit operation result remains `bop_projection_applied`; exact persisted Gateway audit event identity unverified. Internal BOP data; no credentials or raw production data recorded here.

## 3. Reuse, atomicity and ownership
- Fix existing `WorkspaceRepository.insert_bop_projection`; no duplicate Capability or frontend workaround.
- Existing topological validation retained. Finish all rows at each parent depth before batching the next depth; maximum 500 rows per batch retained.
- Same-depth rows still use real PyMySQL multi-row statements. Transaction, workspace revision and idempotency updates remain atomic.
- Root cause: request `cap_a6c51fd581ef4fd6bb8437cb0064faa4` at 18:20:43 failed with MySQL error 1452 in the node `executemany`. Actual OceanBase parent/child same-statement probe failed; separate parent/child statements succeeded. Both probe transactions rolled back.
- Actual test foreign keys point to test-prefixed workspace/node tables, not production tables.

## 4. Implementation boundary
- Changed simulation `data/workspace_repository.py` only within BOP insertion, plus `tests/test_environment_hierarchy_repository.py`.
- Preserved unrelated existing dirty changes, including cache resume and tenant filtering.
- Test-only runtime manifest `.runtime/recovery-local-domains.json`: updated only simulation artifact hash to `sha256:7b6a778ee798e57390e342e2f76c8d1af70e329f6c7ea2e9bce87d3dc9bfd19f` using the existing `hash_domain_artifact` algorithm. No published/signed release or approval edits; normal fail-closed hash checks retained.
- Tables used by this path: test_workmanship_sim_workspaces, test_workmanship_sim_workspace_hierarchies, test_workmanship_sim_workspace_nodes, test_workmanship_sim_workspace_idempotency, test_workmanship_sim_materialization_verifications. No migration or production write.
- Compatibility: API unchanged, no consumer migration or deprecation required.

## 5. Verification evidence
- Base revision: `488dd7c6997a95c0eb518d87c2cf584235f18b05` plus dirty working tree; exact Provider artifact hash above is the runtime binding.
- Focused red/green from implementation session: old batching failed two regression assertions; patched focused suite passed 21 tests, rerun passed 21 in 2.77s.
- Broader command: `python -m pytest plugins/simulation/tests/test_environment_hierarchy_repository.py plugins/simulation/tests/test_alternate_hierarchy_capabilities.py plugins/simulation/tests/test_environment_document_repository.py plugins/simulation/tests/test_environment_document_capabilities.py plugins/simulation/tests/test_environment_materialization.py plugins/simulation/tests/test_environment_verification.py -q --disable-warnings`
- Outcome: **47 passed in 2.98s**. Real PyMySQL cursor test confirms 502 nodes produce batches [1,500,1] and three SQL statements, with every child referencing an earlier batch.
- Controlled database repository test: actual configured test OceanBase, five unordered source nodes over four depths, actual insert/revision/idempotency logic, connection context always rolls back. PASS; zero hierarchy/node/idempotency probe rows afterwards, original workspace revision and cache hash unchanged. This is a local repository test, not an authenticated Gateway execution.
- First repository diagnostic attempt omitted the explicit prefix initializer and stopped on the initial SELECT with table-not-found, before writes. Corrected harness called `configure_table_prefix('test_')` and asserted rewriting before rerun. No application prefix behavior was changed.
- `git diff --check` on source/test: passed (only existing CRLF normalization warnings).
- Restarted only test backend via canonical `.runtime/run_current_test_backend.py`; new PID 394204 on 127.0.0.1:8080. App and Connector/model processes were not restarted.
- Runtime logs: `.runtime-services/backend-test-bop-fix-20260930-183509.{out,err}.log`. Startup complete. `/health` HTTP 200; `/ready` HTTP 200 with memory, connector_plan_signing, routes, domain_db_config, migrations and craft_db all ok. Connector runtime renewal returned HTTP 200.
- Regenerated local runtime Catalog simulation artifact matches current source hash exactly. Other local domain hashes unchanged and matched before restart.
- No production verification, full-repository suite, authenticated App BOP insertion, external reviewer approval or signed release evaluation performed. Test-run GID/result hash/governance snapshot bindings are unverified.

## 6. Governance status
- machine_passed: unverified for the complete governance Snapshot; the 47 selected tests and artifact checks passed.
- human_approved: unverified; user requested a bugfix, not an exact-hash governance release approval.
- runtime_verified: local repository rollback test and service readiness verified; authenticated user-facing insertion and production effect unverified.
- advisory: true.

## 7. Findings and unresolved risks
- User should start a fresh BOP preview/confirm/apply in the existing App session, not blindly replay an old confirmation token or version.
- Deep chains require one statement per depth; wide hierarchies retain batching. No speculative performance change added.
- Existing Windows stdout Unicode logging errors were visible at startup; service nevertheless passed readiness. Logging configuration was not changed in this fix.
- Trusted human/server governance release decisions remain separate from this unpublished test-only deployment.
