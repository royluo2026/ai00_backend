# BOP all-depth insertion retains actual part and resource nodes

## 1. Change classification
- Implementation correction plus experimental contract/capacity change requested by the user: `all` means all actual source nodes, not the process-type allowlist. Maximum projected nodes increases from 10000 to 20000; bounded depth behavior is unchanged.
- Existing process-only hierarchy records are preserved. Corrected `all` projection identity adds `:full-hierarchy-v1` so an old incomplete insertion does not block a new full insertion; repeated corrected insertions still use the same duplicate identity.
- No published/signed Catalog, formal approval or production table modifications. This is an unpublished local test change, not a stable release decision.

## 2. Authoritative context inspected
- Capabilities `simulation.environment.bop_projection.preview@1` and `.apply@1`; Provider `simulation.provider`, official.simulation v1.0.0; domain/owner simulation; lifecycle experimental.
- Current local Catalog, provider specs/descriptors, actual Craft execution_structure normalization, repository insertion/readback, test table node counts and App 1.0.3 caller/forest builder inspected.
- Persisted capability_version_gid, governance snapshot_gid, test-run GID and exact-hash human approval: unverified.
- Effect: preview and atomically insert the exact selected BOP hierarchy into an owned Simulation environment. Inputs and output field names unchanged; preview nodes bound increased to 20000.
- Existing controls retained: simulation.use, user confirmation, tenant/owner scope, expected workspace version, exact source/plan hash revalidation, idempotency, one domain transaction and standard domain errors. Audit evidence remains bop_projection_applied; persisted Gateway audit identity unverified.
- Dependency remains Craft execution_structure.get@1, with version.get@1 and execution_structure.preview@1 for explicitly selected active BOP. No cross-domain SQL added to the Provider.
- Internal BOP business data; no secrets copied into evidence.

## 3. Reuse, atomicity and ownership
- Root cause: `build_bop_projection_plan` applied `_BOP_KIND_DEPTH` to `all` and discarded every actual source type outside the process allowlist. Merely increasing the depth number did not include parts.
- Test workspace 230291366528323584, legacy hierarchy 231001597197586432, source version 205576954294833152: inserted 8127 process nodes versus 15406 actual source nodes.
- Preserve the original source GIDs, node types, names and parents for all-depth. References remain references, not fabricated nodes; no duplicate part nodes are generated from pbom_part links.
- Existing depth-first validation and parent-depth batching are reused. The readback/frontend forest accepts generic node types; no frontend workaround needed.

## 4. Implementation boundary
- Simulation owner paths: capabilities/alternate_hierarchies.py, capabilities/provider.py, data/workspace_repository.py and two matching test files.
- New descriptors explicitly describe all actual source nodes, distinguish nodes from references, and declare the changed capacity. Prior signed business-definition approval must not be reused.
- Runtime-only manifest `.runtime/recovery-local-domains.json` updates only simulation artifact to `sha256:5fe58b189c4db4a18c9b0f30b86d2c0b60ff67500d8e1c7133570f484514109e`. Unrelated dirty changes preserved.
- Same test-prefixed workspace/hierarchy/node/idempotency/materialization-verification tables as the preceding FK fix. No migration. Existing incomplete user hierarchy not archived or overwritten.
- No frontend rebuild required: the existing App retrieves the corrected projection/readback from the backend.

## 5. Verification evidence
- Base revision `488dd7c6997a95c0eb518d87c2cf584235f18b05` plus dirty working tree; exact runtime Provider hash above.
- RED: four failures reproduced discarded all-depth nodes and 10000-node limit; separate regression reproduced collision with legacy incomplete identity. GREEN: focused suite 27 passed in 3.58s.
- Related command: `python -m pytest plugins/simulation/tests/test_environment_hierarchy_repository.py plugins/simulation/tests/test_alternate_hierarchy_capabilities.py plugins/simulation/tests/test_environment_document_repository.py plugins/simulation/tests/test_environment_document_capabilities.py plugins/simulation/tests/test_environment_materialization.py plugins/simulation/tests/test_environment_verification.py -q --disable-warnings` -> **53 passed in 3.70s**.
- Tests exercise line-scoped all, global all, unchanged operation cutoff, parent preservation, separate reference handling, 20000-node output validation, real PyMySQL batching and noncollision with legacy projection identity.
- Actual test OceanBase: built the real Craft execution structure, ran real Simulation plan builder and output schema, inserted through the real repository in an always-rollback diagnostic transaction. Source/plan node parent mappings and inserted per-type counts matched. Result: 15406 nodes; line_process 26, station_process 1134, factory_bop 1, equipment_need 43, process 3038, operation 3929, part 4413, support_material 79, standard_part 618, tool_need 998, non_standard_part 1127. After rollback, zero probe hierarchy/node/idempotency rows remained; workspace revision/cache hash unchanged. This was local repository validation, not an authenticated Gateway insert.
- Initial diagnostic call used the wrong build_execution_structure signature and stopped with TypeError before any database action; corrected to its actual one-positional-argument signature and reran successfully.
- Full project command `python -m pytest -q --disable-warnings`: stopped at collection, 6 errors and 2 warnings in 17.49s. Four tests failed on preexisting checked-in `provider_artifact_mismatch: craft`: test_base_self_annotation_routes.py, test_capability_consumer_e2e.py, test_knowledge_capability_contracts.py, test_route_self_check.py. test_bop_active_line_provider.py could not import craft_backend; test_org_management_application.py could not import project_management_backend. Not a full-suite pass; no hash check disabled to force success.
- `git diff --check` on the five code/test files passed, with CRLF normalization warnings only.
- Restarted only canonical test backend, PID 344692; App and native model windows left running. Logs `.runtime-services/backend-test-bop-full-20260930-184839.{out,err}.log`; startup complete and GET /ready returned 200, all six checks ok.
- Runtime local Catalog verified against current Provider artifact hash, preview maxItems=20000, and updated full-hierarchy acceptance criteria.

## 6. Governance status
- machine_passed: unverified for a full governance Snapshot; 53 scoped tests and exact local artifact checks passed. Full suite blocked as above.
- human_approved: unverified for the new exact business-definition hash; no AI approval issued.
- runtime_verified: actual-source rollback repository validation and restarted service readiness verified; fresh authenticated App full insertion unverified.
- advisory: true. Snapshot/test-run/result-hash platform bindings unavailable, not fabricated.

## 7. Findings and unresolved risks
- Existing incomplete hierarchy is a saved snapshot and is not automatically repaired; user must generate a fresh preview and confirm insertion of the full hierarchy. Renaming alone does not bypass duplicate checks.
- This fixes hierarchy completeness, not model-instance matching or automatic visibility/color control. BOP references remain independent of native model placements.
- The 20000-node cap remains enforced. Larger BOPs need a separately scoped capacity/pagination design.
- Published release/approval governance and the unrelated full-suite collection errors remain unresolved by this test-only fix.
