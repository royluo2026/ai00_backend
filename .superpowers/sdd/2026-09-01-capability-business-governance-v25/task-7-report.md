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

## Fix round 2/5 — bind governance evidence to the candidate Catalog

The three review findings were resolved at one trust boundary. `BusinessCatalogProjection` is now the canonical, content-addressed view of the candidate Catalog: release ID, Catalog content hash, projection hash, and the complete deterministic set of governed capability keys, major versions, capability-version GIDs, and business-definition hashes. The same canonical parser is used before signing and when consuming a production artifact. It rebuilds rows and aggregate truth from the trusted candidate Catalog, historical baseline, and configured exact-hash approval evidence; caller mappings cannot omit, add, invent, duplicate, rename, rehash, or self-approve rows. Missing Catalog or approval context fails closed.

The cutover baseline now has historical rather than mutable-current provenance. Creation resolves `source_revision` to one exact Git commit, reads and verifies the Catalog at that commit, and records its release, content hash, projection hash, and capability projection. Loading verifies both the baseline self-hash and that exact historical Git artifact. Current Catalog additions and material definition changes are classified entry-by-entry against the baseline and continue to exact approval lookup; the gate no longer rejects legitimate evolution as a baseline/Catalog mismatch. The regenerated baseline projection hash is `sha256:15630f67419ab2c37da05b21be35505a030fd64ea5ef0a8e47d4ad81d0fa139d`, with baseline hash `sha256:c3b48536733e155b5fe9626e823da988274e9c7df14ceab249d02b560499a392`.

Official evaluation keeps the static release Catalog and governed business Catalog as separate inputs. A non-business or zero-governed business Catalog fails closed. The CLI/core path was exercised for unchanged legacy backlog, new and material rows without approval, exact approval success, and stale/wrong approval rejection. Production-artifact validation repeats the same exact row and binding validation against the Catalog actually packaged in the artifact.

TDD and verification evidence:

- RED: the new trust-boundary suite initially failed collection because no trusted Catalog projection API existed.
- GREEN: the new adversarial/evolution suite passed `6/6`; the shared focused group passed `103/103`; STANDARD store/workflow retention passed `52/52`; production-artifact tests passed `14/14`; and the core release-gate tests passed `9/9` in the shared materialization.
- Selective-index detached materialization: focused group `99 passed, 2 failed` in 126.10s. The two failures are pre-existing stale acceptance assertions outside this round: `completion.complete is True` despite the intentional unapproved legacy backlog, and a hard-coded `1869` runtime-case count while the current clean manifest contains `3353`. All round-2 trust-boundary, signed-gate, production-artifact, and CLI/core cases in the group passed.
- Offline strict acceptance in the detached materialization: exit `0`, status `passed`, contract scope, 479 stable capabilities, `3353/3353` cases validated, zero failed/skipped; governance `passed_with_legacy_backlog`, machine true, human/runtime false, 495 legacy pending, zero governance blockers; report ID `sha256:3b1bf0b6b230d4955612d77ab3dcea9f0b3212912ea5a46bfac844e41ccbc7d6`.
- Selected `compileall` and `git diff --check` passed. The detached source was built from the exact selective index tree. Test-created `.runtime` and an access-protected pytest temp directory remained untracked in that disposable detached worktree; the target worktree/index was unaffected.

Unrelated shared static-gate, generated-Catalog, acceptance-manifest, and UI/evidence hunks remain unstaged and were not absorbed. No push, merge, publish, implicit production-store access, baseline rewrite during normal checking, or unrelated failure repair was performed.

## Fix round 3/5 — substantive business-definition enforcement

The remaining official-flow gap is closed at the existing Task 1 author-contract boundary. `substantive_business_definition_errors()` now supplies the one canonical minimum for V2.5 approval: a nonempty, non-generated business effect; at least one normalized nonempty acceptance criterion; and either complete, uniquely identified invariant records or a normalized no-invariant reason. Existing `BusinessInvariantContract` parsing continues to own rule ID shape, strict positive version, required fields, types, and test-reference structure; no parallel rule schema or maturity system was added.

`build_business_catalog_projection()` applies this minimum to every stable new or materially changed descriptor after verifying its exact content address. Only a capability whose key and business-definition hash exactly match the verified historical baseline receives the lower-maturity legacy exemption. Baseline creation and readback continue to derive that exemption exclusively from the exact historical Git Catalog. The canonical parser, signed gate, official command, and production-artifact consumer all pass the same trusted baseline into the same projection builder, so an exact approval or a correctly recomputed Catalog hash cannot rescue an empty definition. The checked-in 495-entry cutover projection remains accepted as legacy backlog.

TDD and verification evidence:

- RED: the new boundary suite initially reported `13 failed, 6 passed`; exact-content/hash catalogs with all fields empty, purpose only, whitespace-only acceptance, or acceptance without an invariant declaration were not stopped at the business-definition boundary. The official command progressed past governance validation, and the projection API had no baseline-aware substantive contract.
- GREEN: projection, actual command `main()`, production signed-report consumption, historical 495-entry positive, and prior trust-boundary cases passed `19/19` after the minimal shared fix.
- Shared focused projection/gate/artifact run: `78 passed in 43.02s`. The seven additional shared-only tests belong to preserved static-gate hunks and were not staged.
- Exact selective-index detached materialization: focused projection/gate/artifact run `71 passed in 44.19s`; offline strict acceptance exit `0`, status `passed`, 479 stable capabilities, `3353/3353` cases validated, zero failed/skipped, governance `passed_with_legacy_backlog`, machine true, human/runtime false, 495 legacy pending, zero governance blockers, report ID `sha256:f423d78547b09c7f0d3062c89d06dbf6c53082c0c0f1baba53563371758df44d`.
- Selected `compileall`, `git diff --check`, and post-artifact clean-materialization `git status --short` passed/empty.

The two previously separated stale acceptance assertions were not expanded or rewritten: one still assumes `completion.complete` despite intentional unapproved legacy backlog, and one hard-codes 1869 runtime cases while the current clean manifest has 3353. Unrelated shared CLI-wrapper, static-gate, generated-Catalog, acceptance-manifest, and UI/evidence changes remain unstaged. No push, merge, publish, baseline rewrite, or unrelated repair was performed.
