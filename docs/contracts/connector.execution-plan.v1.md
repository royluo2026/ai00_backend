# `ai00.connector.execution-plan` v1

Owner: Device control plane. Primary producer: Simulation. Primary consumer: AI00 Connector.

The plan is immutable and closed. It binds one tenant, user, device, governed
Capability version, business-definition hash, Adapter major version, ordered
steps, operation contract hashes, payload hashes, issue time and expiry time.

Canonical JSON is UTF-8, uses lexicographically sorted object keys, preserves
array order, emits no insignificant whitespace, rejects NaN and Infinity, and
serializes UTC timestamps as `YYYY-MM-DDTHH:MM:SSZ`. SHA-256 values used for
payloads, plans and results are lowercase and prefixed with `sha256:`.

`plan_hash` is the hash of the complete canonical plan with only `plan_hash`
omitted. A step may depend only on preceding steps. Duplicate IDs, missing or
forward dependencies, payload-hash mismatch, plan-hash mismatch, naive times,
and non-increasing expiry are rejected before any Adapter is created.

Step outcomes are `completed`, `failed`, or `outcome_unknown`. Plan outcomes
are `completed`, `failed`, `cancelled`, or `outcome_unknown`. Completed steps
carry a result hash and no error code; other step outcomes carry a stable error
code. An `outcome_unknown` result must be reconciled before retry.

The cross-language vector is
`backend/tests/fixtures/connector_execution_plan_v1.json`. Contract changes
that alter canonical bytes, validation, status meaning, or required fields need
a new protocol major version and a parallel migration period.
