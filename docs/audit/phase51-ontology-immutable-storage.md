# Phase 51 — Immutable ontology release storage

Date: 2026-08-06
Branch: `codex/capability-wave-a`

## Architectural correction

The written plan used an `ontology` migration domain and `workmanship_ontology_*` tables. The current migration kernel only permits governed domains `base|craft|simulation|agent|device|knowledge`, and the shared ontology is a system-wide control-plane concern rather than Craft-owned editor data. The implementation therefore deliberately uses:

- migration `202608060003_base_ontology_release_governance.sql`;
- tables prefixed `workmanship_base_ontology_*`;
- existing `workmanship_onto_*` tables only as legacy Craft editor input during bootstrap.

This preserves the rule that Base owns database governance while preventing the new shared ontology lifecycle from being coupled to Craft.

## Implemented

- Deterministic NFC-normalized canonical JSON and SHA-256 release hashing, independent of object or dictionary order.
- Duplicate stable ontology identities are rejected before persistence.
- Append-only release and release-object repository writes; no release update path exists.
- Storage tables for immutable releases/objects, change proposals, proposal revisions, reviews, and active refs.
- Active release compare-and-swap with `SELECT ... FOR UPDATE`, expected-current checks, and target Hash verification.
- Idempotent legacy bootstrap: dry-run returns counts and Hash; real mode verifies the immutable OIS snapshot before metadata insertion; later runs reuse the existing bootstrap release.
- Bootstrap reads legacy Craft ontology tables through the Craft data connection and writes governed metadata through the Base repository.

## OceanBase MySQL constraints

- All DDL is replay-safe `CREATE TABLE IF NOT EXISTS`.
- No schema creation, JSONB, PostgreSQL casts, RETURNING, or unsupported TEXT defaults.
- No foreign-key dependency is introduced across legacy and governed storage.

## Verification

The Task 7 focused repository/bootstrap/migration/OceanBase suite passed. Final pre-commit evidence is recorded in the commit handoff.

No database connection, OIS call, deployment, push, or remote mutation was performed.
