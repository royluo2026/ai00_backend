# Task 3B.3e Craft / Agent / Project review

**Verdict: REQUEST CHANGES** — 0 Critical, 2 Important.

Reviewed backend `2db07be42dc525e20c17e3cb209aea3c721acb07..84699dc5f6d8deda41e2eb4974630f07fbe35ecf` and the pinned frontend worktree at `6dd62900c9a82173adcbbe277bb38846ab556031`.  No frontend diff was present.  The manifest check itself completed successfully in 19.9 seconds and reported 14 groups / 17 occurrences, all unresolved.

## Findings

### Important — BOP and Project evidence is a self-asserted string, not lifecycle evidence

`BOP_REASON` is injected as all three input/output/side-effect claims for both `/api/lists` routes, without parsing or binding the actual conditional branch, Capability IDs, authorization/approval, notification/audit, or lifecycle effects.  The test repeats that same literal, so it cannot catch a false Project-list/SQL conclusion.  The real handlers contain material evidence that must be represented: the BOP list branch selects `item_type == "bop_version"` and invokes `craft.bop.version.list`; delete requires `expected_revision` and invokes `craft.bop.version.archive`.  The approval adapter also carries notification behavior, while the specific reject function has no route decorator.  The manifest should encode and fail closed on those facts (including the missing reject handler and resulting notification/audit gap), rather than use the blanket lifecycle sentence.

- `Important`: `backend/scripts/build_craft_agent_project_structural_web_remediation.py:47,79-81,97-101,123-125`
- Evidence needing binding: `plugins/craft/craft_backend/routers/lists.py:123-140,170-184`; `plugins/craft/craft_backend/routers/approval.py:44-60,92-93`
- Inadequate regression: `backend/tests/test_craft_agent_project_structural_remediation_manifest.py:54-58`

### Important — the claimed test GREEN state is not independently reproducible and coverage omits required mutations

Twice, the focused pytest command was cut off at the 30-second tool boundary after emitting only `.`; no final exit status or `3 passed` summary was observed.  It must not be reported as passed.  Separately, the test only checks three of the four Agent groups (`canvas-options` is absent), and its tamper case changes only a final line number.  Add a bounded, independently recorded command and cases for all four Agent groups plus `occurrence_id`, source path/hash, and the pinned baseline-ledger revision/hash.  Keep the existing builder check, which did pass, as static artifact evidence only.

- `Important`: `backend/tests/test_craft_agent_project_structural_remediation_manifest.py:48-58,67-75`

## What remains sound

The builder pins the root-cause ledger with `git show 2db07be4`, discovers final occurrences from the frontend scanner, records final IDs/paths/lines/source hashes, and compares a checked-in manifest with a rebuilt expected payload.  `--check` passed against frontend `6dd62900`; no Catalog, permissions, BFF, provider implementation, or frontend source drift was introduced by this commit.

## Required real owners before any migration

Implement and expose real Craft rule/equipment/fixture lifecycle services; an Agent runtime service with explicit execution bounds, cancellation/resume, timeout and durable outcomes; and a Project approval service that owns rejection transition, audit, idempotency and notification delivery.  BOP may migrate only through its version-list/archive lifecycle providers with its selector and optimistic-concurrency contract preserved.
