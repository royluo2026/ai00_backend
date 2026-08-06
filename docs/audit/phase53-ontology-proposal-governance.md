# Phase 53 — Ontology proposal and human review governance

Date: 2026-08-06
Branch: `codex/capability-wave-a`

## Implemented interfaces

- `ontology.change.proposal.create`
- `ontology.change.proposal.get`
- `ontology.change.proposal.search`
- `ontology.change.proposal.review.submit`

## Governance guarantees

- Proposals require the exact active base release and the repository repeats the check under `SELECT ... FOR UPDATE` before writing.
- Changes use typed operations: `concept|property|relation|mapping` × `add|change|deprecate`, plus `parent.change`.
- Proposal revisions are normalized, hashed, and appended; reviews bind the exact revision GID and content SHA-256.
- Only human entry channels (`web` and `feishu`) may submit formal decisions. Agent/runtime/plugin-originated review attempts fail with `human_review_required`.
- `approve|reject|request_changes` are the only decisions. `request_changes` requires an explanatory comment and blocks approval until a new proposal revision exists.
- An author approval alone is never publishable; at least one approval from a different human reviewer is required, and any bound rejection/change request blocks publication.
- Review operations require `ontology.review` and explicit user confirmation.

## Persistence boundary

Proposal content and reviews are append-only evidence. Only the proposal workflow status is mutable. No operation mutates an immutable ontology release or the active ref.

The approved public interface list does not yet contain a proposal-revision write Capability. Repository/schema support for multiple immutable revisions is retained, but exposing that write requires a separate non-overlapping Capability decision rather than overloading `proposal.create`.

## Verification

Task 9 proposal/review and Capability kernel tests passed. Broader final evidence is recorded at commit time.

No database connection, deployment, push, or remote mutation was performed.
