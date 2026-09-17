# Online model search output correction — governance record

## Change classification
- Implementation fix, advisory. Existing `simulation.environment.model_document.search@1` returns Teamcenter registration envelopes as artifact references. Gateway output validation rejects them before tree reading.
- Owner boundary: simulation repository and tests only; generated Provider/Catalog/docs/acceptance metadata updated using existing generators. No new Capability, schema relaxation, business-data write, migration, or Teamcenter mutation.

## Authoritative context inspected
- Capability version `cv2_8fc4e5e3743123ec029d4955`, lifecycle experimental, Provider `simulation.provider` / `official.simulation`.
- Descriptor: `capabilities/environment_documents.py`; dispatch ownership in `capabilities/provider.py`; persistence `data/workspace_repository.py`; registration in `data/product_structure_observation_repository.py`.
- Gateway `/api/v1/capabilities/simulation.environment.model_document.search:invoke`; actual consumer `cad_sim.js::_refreshModelDocuments`.
- Business effect: search model documents in one readable Simulation environment. Existing invariants and acceptance-criteria arrays are empty; this correction does not invent business rules.
- Input workspace_gid; closed output model list with artifact_ref nullable and source_selector separate. Permission `simulation.use`, required simulation-workspace resource scope, confidential data, cloud_sync/read, owning-domain Provider transaction, no idempotency required, standard audit, no external writes.
- Tables read: test-prefixed workspace, model-document, online-source and completed observation tables. Registration stores its source envelope internally; repository now emits null artifact_ref for teamcenter_online and retains selector in its existing field. Local artifacts and live documents unchanged.

## Reuse, atomicity and ownership
- Reuses existing search operation and output contract. One read effect. No cross-domain SQL or new duplicate endpoint.
- Existing Catalog consumer_refs is empty despite observed web consumer; recorded registration gap, not silently filled with invented identity. Experimental domain_errors remain undeclared. No stable/production promotion claimed.

## Verification evidence
- Runtime error at 2026-09-16 15:31:37, request cap_60b89c75ba12435bbfd42b7530ae6c8e: `output.items[0].artifact_ref does not match any allowed schema`.
- New parameterized repository-to-output-schema regression: RED online case failed with identical message, local/live cases passed; GREEN focused repository/capability/children suite 20 passed. Pytest cache permission warnings did not affect assertions.
- Real test database read for selected environment ending 20260916090559: six online model records; corrected repository output passes actual schema, all artifact_ref null and source_selector present. No records removed or rewritten.
- First diagnostic omitted runtime prefix initialization and failed with missing unprefixed table; performed no writes. Repeated with configure_table_prefix('test_') and explicit SQL rewrite assertion succeeded.
- Provider freeze/check, Catalog build/check, generated docs/check and acceptance manifest build/check passed: rel_7bb6d295a56c3090ef00ca17da64736b, 797 descriptors, 546 stable manifest entries.
- Provider artifact sha256:855697f0c2fd6553a830223f86361dbed1988bc0850eef0c3d64c5a0265187e9.
- Business-definition hash sha256:85448a7884a495dd9661a54d8e280204ffdb7694c183cd5e461cbdd7ba9989ae unchanged versus HEAD; this is not reuse authorization for an old signed release.
- code_revision: backend HEAD 6434def95 plus uncommitted repository/test fix and earlier pending work. snapshot_gid/test_run_gid/result_hash: unverified; no platform evidence identity fabricated.

## Governance status and unresolved risks
- machine_passed: unverified for full governance Snapshot; listed scoped machine checks passed. Prior full offline acceptance remains blocked by 28 unchanged historical business-definition errors.
- human_approved: unverified for exact signed release; user authorized test implementation, not a fabricated super_admin decision.
- runtime_verified: real test-data repository/schema check passed; authenticated UI/Gateway retry and complete tree load remain unverified.
- advisory: true. No production publication or remote push.
- Test runtime candidate/restart to be verified after generation. Keep all six user-created source links; same names do not authorize deduplication.
- Deployment: matching test candidate generated; full `npm run app:test` exited 0 with TABLE_PREFIX=test_. Backend48368, Vite147536, App140088, Connector148280. No VisMockup close/reload requested. Authenticated UI retry remains pending.
