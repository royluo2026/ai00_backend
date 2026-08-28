# Structural Owner Services Design

## Status

- Date: 2026-08-28
- Approval: the user's `go` approves the conservative defaults below
- Governing specification: `docs/governance/atomic-capability-spec-v2.md`
- Evidence source: `docs/governance/capability-v2-structural-remediation-plan.json`
- Scope: 37 root-cause groups / 45 Web occurrences

## Decision

Close the remaining Web governance blockers by domain-owned application services, not by route-shaped providers, direct database capabilities, BFF relabeling, or exclusions. Delivery is grouped into five independently reviewable domain batches: Base, Integration, Craft, Agent, and Project Management. A batch is complete only when its compatibility handlers and Capability providers call the same public owner service and a fresh canonical scan no longer reports its covered occurrences as unresolved.

## Global Safety Semantics

1. Inputs and outputs use closed, versioned schemas. Unknown nested fields are rejected on writes and are never echoed as an opaque passthrough.
2. Writes require tenant/actor binding, resource authorization, optimistic revision where an aggregate already exists, idempotency, and durable audit evidence.
3. Destructive browser verbs map to recoverable lifecycle transitions by default. Permanent purge is outside this scope and requires a separate Capability and stronger approval.
4. Compatibility REST and Capability Gateway are adapters over one application service; neither adapter owns SQL or imports another domain's router.
5. Secrets appear only as vault references after enrollment. They cannot enter Capability evidence, output, logs, or browser-readable projections.
6. External calls and Agent execution have explicit time/resource bounds and durable `accepted`, `succeeded`, `failed`, or `outcome_unknown` state. Retrying an unknown outcome reconciles by idempotency key; it does not blindly repeat the side effect.
7. No package may reduce unresolved counts by changing an occurrence to operations-excluded, BFF, or another domain's Capability.

## Base Batch

### Saved views and annotations

Saved-view configuration is a finite semantic grammar: selected field identifiers, ordered sort clauses, conjunction-only typed filters, page size, and presentation mode. Arbitrary expressions, executable fragments, SQL, and unknown keys are rejected. Copy creates a new owner-bound aggregate and never copies sharing grants. Delete is a tombstone with restore metadata.

Self annotations accept plain text plus typed attachment references (`attachment_gid`, media type, display name, size, checksum). Binary content and storage credentials never cross the service. Update replaces the declared reference set after validating that every attachment is visible to the actor. Deletion tombstones the annotation while preserving audit and retention metadata.

### Identity projection

The browser-visible projection is limited to actor gid, display name, tenant/team gids, locale, time zone, and effective permission identifiers. It omits credential, authentication-provider, recovery, token, and internal policy fields.

### Plugin lifecycle

Install accepts only a signed marketplace release identity and explicit requested grants; arbitrary URLs are retired. Uninstall disables mounts and revokes grants in the installation transaction, preserves tenant data by default, records an audit event, and supports retry/idempotency. Hard deletion of plugin-owned data is not part of uninstall.

## Integration Batch

Connector creation/update consumes a one-time credential-enrollment handle and stores only the resulting vault reference. The owner service applies the network allowlist before any runtime call. Connection test, discovery, preview, and sync are bounded durable operations with timeout and reconcilable unknown outcomes.

Mapping definitions use a closed field-mapping grammar with allowlisted transforms, bounded batch size, exact stable target Capability version, minimum Catalog release, and optimistic revision. The legacy mapping flows are retained and migrated because they represent active browser outcomes in the canonical inventory.

## Craft Batch

Library delete verbs become revision-locked `retire` transitions after reference checks, with restore metadata and audit. BOP version deletion becomes archive, and only the `item_type=bop_version` list branch dispatches to Craft.

Rule definitions use a typed, versioned grammar and the lifecycle `draft -> validated -> active -> suspended -> retired`. Definition updates apply only to draft or suspended rules; activation requires successful validation and explicit confirmation. Evaluation and waiver are separate atomic outcomes; waivers are scoped, expiring, auditable, and never mutate the rule definition.

## Agent Batch

Canvas and node execution use a deny-by-default allowlist of typed node kinds and Gateway Capability targets. Arbitrary code, shell execution, dynamic import, and unrestricted network access are forbidden. Each run has wall-clock, CPU, memory, node-count, input/output-size, and external-call limits; side-effecting nodes pause for explicit confirmation. Durable run records, signed single-use pause tokens, idempotent resume, and audit lineage are mandatory.

## Project Management Batch

Approval rejection performs one revision-locked state transition and writes an audit record plus notification outbox event in the same transaction. It requires a non-empty reason and idempotency key. Recipients are derived from the approval aggregate (requester and current assigned approvers except the rejecting actor); templates receive identifiers and reason, never secrets. Delivery failure does not roll back the rejection and is retried from the outbox.

## Delivery and Acceptance

Each domain batch follows test-driven development and includes owner-service unit tests, adapter equivalence tests, authorization/confirmation/idempotency tests, contract rejection tests, and the canonical Web scan. Catalog descriptors, providers, REST adapters, manifests, generated evidence, and frontend calls change together in one reviewed batch.

The structural program is complete when:

- all 37 root-cause groups and 45 occurrences have a governed Capability disposition;
- canonical unresolved groups and occurrences are both zero;
- no new operation exclusion or BFF classification was used to obtain zero;
- all targets are stable and owner-domain correct;
- strict Capability V2 acceptance and repository tests pass;
- runtime snapshot and signed release evidence are generated only after all source-changing batches are committed.
