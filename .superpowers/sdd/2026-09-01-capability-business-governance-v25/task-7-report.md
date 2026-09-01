# Task 7 Report — Enforce New/Changed Approval Without Blocking Legacy Testing

## Result

Implemented and committed the mandatory SQL STANDARD-review persistence prerequisite and the Task 7 business-governance release policy. New and materially changed definitions require an exact current-hash approval; unchanged cutover entries pass as `passed_with_legacy_backlog`; deterministic blockers always fail the gate. Machine, human, and runtime truth are reported independently in both the static and signed Governance Center reports.

## Commits

- `29a1d2aa` — `fix: persist standard governance reviews`
- `d8f67d2d` — `feat: gate new capability business definitions`

## Mandatory prerequisite

STANDARD review appends now persist in the proposal CAS transaction, hydrate from SQL in stable `review_gid` order with the exact recorded stage, and use a store-owned STANDARD review allocator. Memory and SQL stores therefore retain `base_owner` across restart and allow `platform_release`; duplicate retries remain exactly-once and insert failures roll back the whole transition. The deferred business-review process-local GID issue was not expanded.

TDD evidence: initial focused SQL RED was 2 failures (missing hydrated row and missing rollback failure); focused GREEN was 3 passed. Clean materialization focused regression was 2 passed, 43 deselected. The combined store/workflow suite was 49 passed in the shared materialization before selective commits. In the clean commit materialization it was 48 passed / 1 failed only because the pre-existing authoritative-release fixture omits the separately owned static-gate evidence, causing the known fail-closed `static_gate_not_passed` path; the Task 7 persistence tests pass.

## Task 7 policy and baseline

The explicit result contains aggregate and per-capability `machine_passed`, `human_approved`, `runtime_verified`, `legacy_pending_review_count`, blockers, `governance_status`, and `change_kind`. The signed report canonicalizes this structure, fails on missing/blocked governance, and cannot derive human or runtime truth from a static pass.

The one-time baseline is `docs/governance/capability-business-governance-legacy-baseline.json`: 495 entries, source revision `b52cb4a74b29d27fdf6e0c00ec5598fe5462c907`, Catalog release `rel_3f5ef8265738dc99f4803579111af53d`, and baseline hash `sha256:f22102aeb1fbf187e28c46bbea89cec23c18398419248dda32717d9841080cf4`. Creation refuses an existing destination; normal commands only load and verify it.

## Verification

Clean detached materialization at `d8f67d2d`:

- release-gate command from the brief: 22 passed
- prerequisite focused restart/rollback tests: 2 passed, 43 deselected
- offline strict acceptance: exit 0, status `passed`, 3365 passed; business governance `passed_with_legacy_backlog`, 495 legacy pending, human/runtime false, zero governance blockers
- `compileall`: passed
- `git diff --check`: passed
- clean materialization reported `working_tree_clean: true`

Shared static-gate edits and `source_root` forwarding were preserved but not absorbed into these commits. No migration, bootstrap, or Catalog failure occurred in the clean Task 7 acceptance run.
