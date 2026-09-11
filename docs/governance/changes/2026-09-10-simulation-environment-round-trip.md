# Simulation Environment Round-trip Capability Change Record

## Business purpose

AI00 now treats a Simulation environment as durable domain state rather than a
single transient VisMockup window. One environment can own one primary PLMXML,
additional inserted PLMXML/JT documents, editable alternate hierarchies and
placements. The same semantic state can be exported to one deterministic
top-level PLMXML runtime package and verified against the Connector readback.

## Ownership and atomicity

- Simulation owns environment documents, alternate hierarchies, placements,
  materialization manifests and runtime verification records.
- Artifact owns immutable file bytes and leases; only Artifact refs are stored.
- Connector owns workstation staging and VisMockup COM effects.
- Craft owns BOP repositories, versions and Fork. Simulation may consume only a
  governed immutable Craft projection; it must not read Craft tables.
- Document add/remove, hierarchy create/update/archive and placement
  create/move/remove are separate optimistic-concurrency effects.
- A materialization has exactly one top-level PLMXML. Source documents remain
  immutable and are staged as dependencies.

## Capability changes

The Simulation Provider adds experimental `@1` capabilities for model-document
search/add/remove, alternate-hierarchy search/get/create/update/archive,
placement create/move/remove, PLMXML environment import/export and governed
VisMockup document insert. Existing stable Capability meanings are unchanged.

## Authorization, confirmation and consistency

- Reads require `simulation.use` and enforce owner/shared workspace visibility.
- Writes require `simulation.use`, server-side ownership checks, row-version CAS
  and an idempotency key.
- Destructive archive/remove operations require user confirmation.
- Local file paths never enter browser Capability payloads or durable Simulation
  rows. Signed plans carry immutable Artifact refs; AppHost resolves them to a
  lease-scoped private cache path immediately before COM invocation.
- A crash before a later plan step starts is reported as
  `failed_without_effect`; it cannot be projected as successful merely because
  an earlier step completed.

## Transaction and evidence boundaries

Database mutations commit within the Simulation domain transaction. Artifact
download and VisMockup effects are separate recoverable steps with signed plan,
step journal and post-condition evidence. Catalog evidence identifies Provider
artifacts; the generated runtime package and readback report identify the exact
semantic environment state.

## Rollout and rollback

Migration `0018` is additive and resumable on OceanBase. New Capabilities remain
experimental. Rollback disables their consumers and retains rows/artifacts for
audit; it does not destructively remove migrated data. Production promotion
requires a clean-tree business audit, an end-to-end VisMockup pilot and explicit
human approval of the exact generated Catalog release.

## Current approval state

- machine checks: partial; deterministic Catalog/schema/scan checks pass.
- human approval: not granted.
- trusted runtime verification: not granted.
- advisory: true.
