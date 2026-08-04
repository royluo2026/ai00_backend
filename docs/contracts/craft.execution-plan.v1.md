# `craft.execution-plan` v1

Owner: Craft. Primary consumer: Simulation.

This immutable snapshot is the only supported way for Simulation to interpret BOP
execution order. Simulation must not query `workmanship_bop_*`, infer ordering from
table layout, or retain a mutable BOP object reference.

The producer publishes the snapshot to OIS and returns it through the versioned
`craft.execution-plan.get` Capability. Simulation stores all four source fields:

- `source_bop_version_gid`
- `source_bop_revision`
- `source_bop_hash`
- immutable `execution_plan_snapshot_uri`

`operations` use canonical `(sequence, operation_id)` order. Dependencies are
explicit `predecessor_ids`; every predecessor must exist and have a lower sequence.
The SHA-256 content hash covers the contract, source metadata, publication time and
all operation content. Rebuilding a Simulation environment verifies both the hash
and the pinned version/revision before use.

Breaking semantic changes require contract v2. Additive optional fields may be
introduced in v1 only when old consumers can safely ignore them; consumer contract
tests remain the release gate.
