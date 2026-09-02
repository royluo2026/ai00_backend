# Craft Resource Requirement Capabilities Design

## Goal

Bring the production VPPS socket, tool, fixture, and equipment standard library into the governed test branch without reintroducing direct database APIs.

## Business boundary

The Craft domain owns a **resource requirement standard**: a reusable definition of what a process needs. It is not a Factory physical asset and is not the legacy VPPS template row currently exposed by `craft.library.*@1`.

The supported resource types are `socket`, `tool`, `fixture`, and `equipment`. Every standard has a type-scoped code, name, structured attributes, source, lifecycle status, and optimistic resource version. BOP links use the same resource GID that the VPPS management page displays.

`socket` is an independent process-resource requirement identity. It is not a display-only projection of a tool and not an attribute-owned child of a tool. TC and BOP represent it with the independent `socket_need` node type and `resource_socket` link type. A socket requirement can therefore be selected, matched, staged, resolved, retired, and audited independently from a tool requirement.

## Capability family

- `craft.resource_requirement.search@1` returns a bounded, cursor-paginated collection.
- `craft.resource_requirement.create@1` creates one active standard.
- `craft.resource_requirement.update@1` changes one active standard at an expected resource version.
- `craft.resource_requirement.retire@1` retires one standard; it does not physically delete it.
- `craft.resource_requirement.alias.create@1` adds one normalized alias.
- `craft.resource_requirement.alias.delete@1` removes one alias.
- `craft.resource_requirement.staging.search@1` returns bounded unresolved TC import rows.
- `craft.resource_requirement.staging.resolve@1` binds one staging row to a type-compatible standard in one transaction.
- `craft.resource_requirement.staging.ignore@1` marks one staging row ignored without manufacturing a resource link.

Each write is idempotent at the Gateway, audited, and requires the declared confirmation policy. Resolve and ignore are separate effects.

## Data model

Craft versioned migration `0004_resource_requirements.sql` creates:

- `workmanship_craft_resource_requirements`
- `workmanship_craft_resource_aliases`
- `workmanship_craft_tc_resource_staging`

Resource code uniqueness is `(resource_type, code)`. Records are global Craft standards because the production behavior and knowledge-admin workflow are global; this decision is explicit and must be reviewed by a super administrator before human approval. `resource_version` protects updates. Retirement preserves references and history. Aliases are unique by resource and normalized value.

Migrations are additive and never delete or rewrite the legacy template tables. Existing migration `0004` remains immutable after application and continues to copy tool, fixture, and equipment standards. A new follow-up migration copies legacy tool rows that contain a nonblank `socket_model` or `socket_cad_no` into independent socket standards: the normalized `socket_model` is the preferred code and `socket_cad_no` is the fallback. Rows with the same resulting socket code collapse deterministically to one socket standard; socket CAD number and fastener metadata are retained as socket attributes, while the original tool attributes remain unchanged. The follow-up migration is rerunnable and insert-only toward the new standards.

## Provider rules

- Type must be one of the four published values.
- Code, name, and alias values are trimmed and nonblank.
- Search is bounded to 200 rows per page.
- Updates require an exact `expected_resource_version`.
- Resource type cannot change after creation.
- Retired resources cannot be selected for new BOP links.
- A staging resolution locks the staging row and resource, checks matching type, replaces only the four standard-resource link types, and commits link plus staging state atomically.
- Ignore and resolve reject already-decided staging rows.

Type-specific `attributes` remain an object, but every public input and output object is closed. The published schema enumerates the supported legacy engineering fields for sockets, tools, fixtures, and equipment; unknown keys are rejected instead of being silently discarded. Alias rows and TC staging rows likewise publish their complete closed shapes. Adding a new engineering attribute later requires an intentional contract change and regenerated governance evidence.

The family declares Capability-specific business invariants and errors rather than inheriting the complete Craft-domain error list. At minimum the contracts cover type-scoped code uniqueness, immutable resource type, active-only update/link/alias rules, optimistic concurrency, reference-safe retirement, normalized alias uniqueness, type-compatible staging decisions, and atomic staging/link updates. Each invariant binds to its enforcement location and positive/rejection tests.

## Exposure and consumers

The Gateway is authoritative. Compatibility REST routes may remain as thin adapters, but contain no SQL or business authorization.

Registered consumers are:

- VPPS management page for all four resource types.
- BOP lineage resource picker.
- TC import matching and the BOP lineage staging panel. Staging search is always scoped by required `version_gid`; the panel supplies that version and exposes resolve/ignore actions to authorized reviewers.

The TC resource-node mapping includes `socket_need`, `tool_need`, `fixture_need`, and `equipment_need`. Exact code and normalized alias matching are restricted to the node's matching resource type. Ambiguous and unmatched socket nodes follow the same staging flow as the other three types.

The legacy `craft.library.*@1` remains stable during migration. Its tool, fixture, and equipment operations are not silently redirected to the new tables.

## Verification

Tests cover contracts, nonempty attribute and alias projection through the real Gateway validator, pagination, normalization, duplicate codes and aliases, optimistic concurrency, retirement, all four TC node types, type-safe BOP links, resolve/ignore transaction behavior, deterministic socket backfill, migration ownership, compatibility routing, and browser consumer contracts. Runtime verification uses nonempty resource, alias, and staging rows; an empty-list HTTP 200 is not sufficient evidence. Generated Catalog and governance artifacts must be rebuilt from the current tree. `machine_passed`, `human_approved`, and `runtime_verified` remain independent.

## Non-goals

- No production database mutation or deployment.
- No physical asset management; that remains in Factory.
- No automatic human approval.
- No destructive migration of legacy VPPS template rows.
