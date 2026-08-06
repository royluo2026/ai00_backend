# Phase 56 — Craft validation policy gate

Date: 2026-08-06
Branch: `codex/capability-wave-a`

## Implemented

- Immutable policy/check model for `draft_check`, `publish_check`, `simulation_check`, and `workstation_check`.
- Mandatory completeness gate for source reference, unique Owner, scope, severity, execution mechanism, check version, threshold, and algorithm reference.
- Unverified experience is automatically downgraded to `hint`; it cannot become a blocking rule.
- `publish_check` additionally requires positive, negative, boundary, and historical replay evidence.
- OceanBase-safe storage migration for published policy metadata and checks.
- Exact inventory of the four current hard-coded VPPS checks.

## Unresolved business governance

The implementation deliberately does not invent sources, Owners, thresholds or algorithm decisions. All four current VPPS checks are missing those fields plus policy version and replay evidence. Therefore `CRAFT-002` is not complete and the following Capabilities remain intentionally unregistered:

- `craft.bop.version.validate`
- `craft.bop.version.publish`
- `craft.pbom.vpps.validate`

The authoritative blocker inventory is recorded in `SYSTEM_OPTIMIZATION_BACKLOG.md`.

## OceanBase and boundary notes

Migration `202608060004_craft_validation_policies.sql` uses Base-governed versioned DDL, Craft-owned table prefixes, replay-safe table creation, MySQL JSON, and no PostgreSQL-only syntax.

No database connection, deployment, push, or remote mutation was performed.
