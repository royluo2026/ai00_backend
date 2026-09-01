# Task 6 Report — Capability Business Governance V2.5

## Completed scope

- Extended the existing proposal and `base.capability_review.decide` workflow with the closed `business_definition` review path; no parallel approval API was added.
- Kept the durable `proposed_descriptor_hash` field, while explicitly projecting it as `business_definition_hash` for this review type.
- Enforced approval from the server-created effective identity only: an undelegated web user with the trusted `super_admin` active role. Payload roles, ordinary roles, agent/service identities, and delegation are rejected.
- Added strict SHA-256 hash validation, allowed decisions, bounded non-empty reasons, pending/current-snapshot/CAS checks, append-only `CapabilityBusinessReview` persistence, and exact idempotency semantics.
- Made current approval require the latest exact approved review, so rejected/changes-requested or a changed business-definition hash cannot revive an earlier approval.
- Added bounded, redacted business review evidence and relation-candidate projections for super-admin proposal readback; ordinary readers receive no business evidence/history. Pagination is sorted by proposal id and cursor-stable.

## Test-first evidence

- RED: `python -m pytest backend/tests/test_capability_business_review.py -q` initially failed five new cases because the existing decision route required the generic `stage` field and had no business-review decision branch.
- GREEN: `python -m pytest backend/tests/test_capability_business_review.py backend/tests/test_capability_governance_business_store.py backend/tests/test_capability_governance_service_workflow.py backend/tests/test_capability_business_relations.py backend/tests/test_versioned_migration_files.py -q` — 58 passed.
- `python -m compileall -q backend/capability_governance_test/workflow.py backend/capability_governance_test/service.py backend/capability_governance_test/contracts.py backend/capability_governance_test/provider.py backend/capability_governance_test/store.py backend/capability_governance_test/business_models.py backend/capability_v2/gateway.py` — passed.

## Known shared-worktree condition

`python -m pytest backend/tests/test_capability_governance_provider.py -q` has one pre-existing failure caused by the shared, uncommitted static-gate release changes (`static_gate_not_passed` changes the expected blocker count). Those unrelated hunks remain unstaged and untouched by this task.

## Fix round 1 — trusted identity, atomicity, and evidence binding

- The decision path now accepts only the concrete V2 `ConsumerIdentity` contract attached by the gateway. A structural lookalike, payload roles, delegation, non-web consumer, and service/AI actor cannot gain approval authority.
- Business review transition is serialized at the shared proposal workflow boundary. The review append occurs before the proposal mutation, a persistence exception leaves proposal/history unchanged, and concurrent same-row decisions have one CAS winner.
- Review timestamps are server UTC values; the closed review contract rejects caller `decided_at`. Current approval uses highest append/review gid in both stores rather than caller-controlled time.
- Pinned and current snapshots must both expose the exact proposal version, capability major, and business hash. Memory now verifies the referenced snapshot/version before appending a review.
- Proposal search now applies cursor before the page limit, reads `limit + 1`, and projects only relation candidates that contain the exact `capability_id@major_version` key from the pinned snapshot.

### Clean-materialization verification

Clean detached worktree: `E:\Projects\ai00_v3\.task6-worktree-clean-a5c18109` at commit `a5c18109`.

- `python -m pytest backend/tests/test_capability_business_review.py backend/tests/test_capability_governance_business_store.py backend/tests/test_capability_governance_service_workflow.py backend/tests/test_capability_business_relations.py backend/tests/test_capability_governance_provider.py -q` — **79 passed in 2.28s**. Pytest emitted two cache-directory permission warnings only; test outcomes are clean.
- `python -m compileall -q backend/capability_governance_test/workflow.py backend/capability_governance_test/service.py backend/capability_governance_test/contracts.py backend/capability_governance_test/provider.py backend/capability_governance_test/store.py backend/capability_governance_test/business_models.py backend/capability_v2/gateway.py` — passed.
- `git diff --check` for the staged Task6 fix was clean before commit.
- Separate known migration issue: `python -m pytest backend/tests/test_versioned_migration_files.py -q` has **1 failed, 8 passed** because pre-existing `202608310001_craft_rule_identity_backfill.sql` contains non-resumable `UPDATE` SQL. It is outside Task6 and unchanged.

## Fix round 2 — durable proposal CAS transaction

- Added durable storage for the existing proposal workflow state and review-decision idempotency (`0007_business_review_idempotency.sql`); this is not a parallel approval API.
- A business decision now conditionally updates the persisted proposal (`proposal_gid`, `row_version`, `pending_approval`, and pinned hash), appends the immutable review, and stores the request fingerprint in one SQL transaction. Any failure rolls back all three writes.
- Memory uses one shared store lock, validates before publish, and stages replacement maps so a failed validation cannot expose a partial review/proposal/idempotency state.
- Business-definition transitions now use the same durable proposal CAS, preventing a normal transition from racing a review decision. SQL rehydrates the persisted proposal after commit/replay so local workflow state does not become an authority after durable writes.
- Added tests for two independent workflow instances deciding the same persisted proposal concurrently (one winner, one review), SQL write order/rollback on injected idempotency insertion failure, and the Memory equivalent.

### Clean-materialization verification

Clean detached worktree: `E:\Projects\ai00_v3\.task6-round2-clean-5ac01fdb` at commits `d88e6177` and `5ac01fdb`.

- `python -m pytest backend/tests/test_capability_business_review.py backend/tests/test_capability_governance_business_store.py backend/tests/test_capability_governance_service_workflow.py backend/tests/test_capability_business_relations.py backend/tests/test_capability_governance_provider.py -q` — **82 passed in 2.32s**.
- `python -m compileall -q backend/capability_governance_test/store.py backend/capability_governance_test/workflow.py backend/capability_governance_test/service.py backend/capability_governance_test/provider.py backend/tests/test_capability_governance_business_store.py` — passed.
- `git diff --check 5ac01fdb^ 5ac01fdb` — clean.
- Separate pre-existing migration failure remains unchanged: `python -m pytest backend/tests/test_versioned_migration_files.py -q` — **1 failed, 8 passed**; the failure is the non-resumable `UPDATE` in `202608310001_craft_rule_identity_backfill.sql`.

## Fix round 3 — persistent-service integration closure

- `SqlGovernanceStore` now acts as the existing minimal workflow port when a persistent service is constructed without a separately injected wrapper. The service no longer rejects a durable proposal/review operation merely because that optional wrapper was omitted.
- Durable proposal readback now lists persisted rows and rehydrates ordered business-review history. A restarted service sees the committed status and exactly one append-only review.
- New-definition detection loads durable proposals and transitions displaced business proposals to `superseded` through the existing conditional proposal CAS; a fresh workflow cannot review the displaced pending proposal.
- Added coverage for the default persistent service constructor across create, transitions, business decision, and restarted readback; separate connection wrappers over shared transactional state race the same stored proposal and leave one review.

### Clean-materialization verification

Clean detached worktree: `E:\Projects\ai00_v3\.task6-round3-clean-c9dd3d64` at commit `c9dd3d64`.

- Core Task6 store/workflow set: `python -m pytest backend/tests/test_capability_business_review.py backend/tests/test_capability_governance_business_store.py backend/tests/test_capability_governance_service_workflow.py backend/tests/test_capability_business_relations.py -q` — **63 passed in 1.42s** in the shared tree before clean materialization.
- Clean broad affected set (business-review, store, service-workflow, relations, provider, catalog) produced **85 passed, 10 failed**. The failures are outside Task6: one pre-existing release evidence expectation now requires static-gate fields, and nine catalog/bootstrap failures are caused by the integration provider's missing `AI00_INTEGRATION_ADAPTER_FACTORY` / catalog release mismatch. No Task6 assertion failed.
- `python -m compileall -q backend/capability_governance_test/service.py backend/capability_governance_test/store.py backend/capability_governance_test/workflow.py backend/tests/test_capability_governance_business_store.py` — passed.
- `git diff --check c9dd3d64^ c9dd3d64` — clean.
- Separate known migration failure remains unchanged: `python -m pytest backend/tests/test_versioned_migration_files.py -q` — **1 failed, 8 passed** due to `202608310001_craft_rule_identity_backfill.sql` containing a non-resumable `UPDATE`.

## Fix round 4 — restart-safe proposal identity and port-specific persistence

- Persistent business-definition proposals now allocate their identity from the existing Base-owned `workmanship_display_id_counters` mechanism. The sequence is synchronized to the greatest stored proposal id, incremented transactionally, and the proposal is inserted without an upsert, so a restarted process cannot overwrite an earlier row. The returned durable id replaces only the transient proposal id; the deterministic in-memory path is unchanged.
- Restart coverage uses two fresh `CapabilityGovernanceService` instances and distinct connection wrappers over one transactional database. A replacement definition receives a distinct id, the prior row remains visible as `superseded` and cannot be reviewed, and both rows remain addressable by their exact ids.
- The CAS race now enters through two independent services' real `base_capability_review_decide` method with genuine trusted, undelegated web `ConsumerIdentity` objects. For one persisted proposal and row version, one approved/rejected decision wins, the other reports `row_version_conflict`, one review is durable, and a restarted service rehydrates that one review.
- The persistent-runtime guard is split by proposal, waiver, and release capability and follows the service actually selected for each operation. `SqlGovernanceStore` is accepted as the durable proposal boundary only; in-memory waiver and release services remain fail-closed after restart, when placed on a workflow-port-shaped object without a persistent marker, and when they shadow separately supplied durable arguments.
- The existing SQL decision transaction remains connected: proposal CAS, immutable review insert, and idempotency insert still commit together, and the injected final-insert failure still rolls back all three writes.

### Test-first evidence

- RED: the three-finding command initially produced **2 failed, 1 passed**. The restart case reused proposal id `1`, and the persistent-runtime waiver/release case did not raise; the new service-level concurrency evidence already passed against the pre-fix decision transaction.
- RED: the workflow-port-shaped in-memory waiver/release case separately produced **1 failed** because an in-memory waiver was accepted.
- Self-review RED: the selected-service guard case separately produced **1 failed** because an in-memory workflow-port waiver shadowed an explicit persistent argument while the guard inspected the unused argument.
- GREEN at implementation commits `1f595a83` and `ad6f5a7b`: the six focused cases (original SQL transaction/rollback plus the five round-4 integration/guard cases) produced **6 passed in 0.89s**.
- GREEN at final implementation commit `ad6f5a7b`: `python -m pytest backend/tests/test_capability_governance_business_store.py -q -p no:cacheprovider --basetemp .tmp-task6-round4-clean-store` — **36 passed in 0.69s**.

### Clean-materialization verification

Clean detached worktree: `E:\Projects\ai00_v3\.task6-round4-clean-ad6f5a7b` at final implementation commit `ad6f5a7b`.

- Task6 plus affected store/workflow/provider/Task5 regression command (`test_capability_business_review.py`, `test_capability_governance_business_store.py`, `test_capability_governance_service_workflow.py`, `test_capability_business_relations.py`, `test_capability_governance_ai.py`, and `test_capability_governance_provider.py`) produced **105 passed, 2 failed in 2.68s**. Both failures are the pre-existing static-gate integration mismatch: authoritative release evidence lacks the newly expected static-gate fields and yields `governance_dependency_unavailable` / `missing_required_data`, while provider projection has the corresponding extra `missing_required_data` blocker. No round-4 store, identity, CAS, or guard assertion failed.
- `python -m compileall -q backend/capability_governance_test backend/tests/test_capability_governance_business_store.py` — passed.
- `git diff --check 22a67f4d ad6f5a7b` — clean; the clean worktree itself had no changes.

### Known migration, static-gate, and environment failures

- Governance migration compilation: `python -m pytest backend/tests/test_capability_governance_migrations.py -q` — **4 failed, 2 passed in 0.63s**. The existing `0007_business_review_idempotency.sql` table `workmanship_base_capability_business_review_requests` is absent from the existing `GOVERNANCE_TABLES` contract, so compilation reports it as an extra table; round 4 did not change migrations or schema contracts.
- Versioned migration policy: `python -m pytest backend/tests/test_versioned_migration_files.py -q` — **1 failed, 8 passed in 0.53s** because the pre-existing `202608310001_craft_rule_identity_backfill.sql` contains a non-resumable `UPDATE`.
- Catalog/bootstrap environment: `python -m pytest backend/tests/test_capability_governance_catalog.py -q` — **8 failed, 2 passed in 6.77s**. Seven failures stop at the missing `AI00_INTEGRATION_ADAPTER_FACTORY`; the remaining failure is the pre-existing generated catalog release-id mismatch (`rel_842a...` versus `rel_8456...`). These failures are outside the two implementation commits.
