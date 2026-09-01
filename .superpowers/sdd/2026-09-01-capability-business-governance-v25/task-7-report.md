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

## Fix round 1/5 — release-evidence hardening

Implementation commit: `d787e73d` (`fix: harden capability governance release evidence`).

All five verified review findings were addressed as one fail-closed evidence wave:

- Signed governance now uses one canonical parser for dataclass and mapping inputs. It validates exact row keys/types/identity/hash/change/status/blockers, rederives every row and all aggregates, and is used both before signing and during production-artifact readback. Resigned nested or aggregate tampering is rejected.
- The cutover baseline was regenerated with the canonical generator from the exact Catalog at source revision `b52cb4a74b29d27fdf6e0c00ec5598fe5462c907`. Its corrected binding is Catalog release `rel_0b584b19349bc98727900583bb19f687`, Catalog hash `sha256:0b584b19349bc98727900583bb19f687a093b3ce91431fb384795034d690ab60`, 495 capabilities, and baseline hash `sha256:f73f10868cf1104148d16c618991ea5153575fb3b46c74e77f513241d1ec5f47`. Normal verification now validates the referenced Catalog's own content address and exact business-definition projection; it never rewrites the baseline.
- `runtime_verified` is true only when environment validation, RC schema/commit/Catalog/migration/domain/database/case validation, and the exact five component results are all error-free. Readable or hashable evidence alone no longer sets it.
- STANDARD review request key/fingerprint/result identity is persisted in the same SQL CAS/review transaction. Restart replay returns the original result, mismatch conflicts, and request-insert failure rolls back proposal/review/key atomically. Memory has identical durable replay semantics. STANDARD and business reviews now share the store-owned review allocator, including existing-row maxima, avoiding the deferred process-local collision.
- Official release-gate and offline acceptance commands accept only an explicit immutable approval artifact bound to the Catalog release and exact `(capability_version_gid, definition_hash)`. No production connection is implicit. Missing evidence leaves new/material definitions blocked and unchanged cutover definitions in legacy backlog. The governance release-acceptance caller supplies a valid structured approved result rather than bypassing the gate.

Clean detached materialization at `d787e73d`:

- focused release/store/workflow/migration/acceptance group: `142 passed, 2 failed` in 98.03s. Both failures are pre-existing static-evidence/completion fixtures outside this round: the authoritative release fixture omits required static/business evidence, and the generated-report test expects `completion.complete` while the checked-in completion state remains false. All round-1 tests in that group passed.
- offline strict acceptance: exit 0; report status `passed`; `3365 passed`; `working_tree_clean: true`; business governance `passed_with_legacy_backlog`, 495 legacy pending, human/runtime false, and zero blockers.
- baseline/Catalog verification: source revision, release, content hash, and 495-entry projection matched exactly.
- selected `compileall`, `git diff --check`, and clean `git status --short`: passed/empty.

Shared static-gate, acceptance-manifest, and UI-asset hunks remained unstaged and were not absorbed. No push, merge, publish, or implicit production-store access was performed.
