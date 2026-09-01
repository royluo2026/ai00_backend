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
