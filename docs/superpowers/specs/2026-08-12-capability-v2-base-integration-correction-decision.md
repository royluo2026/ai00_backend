# Capability V2 Base / Integration Frozen-Review Correction Decision

**Status:** Approved

**Approved by:** Repository owner in the Codex task on 2026-08-12 (`go` in response to the recommended correction)

**Applies to:** `docs/governance/capability-coverage-review/base-platform.json`, `docs/governance/capability-coverage-review/integration.json`, Plans 02, 12 and 15

## Context

The frozen coverage review assigns five external-datasource and mapping candidate IDs to Base even though their source functions operate exclusively on Integration-owned connector and mapping tables. It also retains three entries that the approved domain-rearchitecture design explicitly classifies as internal operations mechanisms. Implementing those conclusions unchanged would violate the approved ownership model and the goal that each domain can develop its code and database independently.

This is a correction of eight known frozen entries. It does not reopen discovery, rescan the 752 stable functions, change the eleven domains, or reclassify any unrelated Capability.

## Decision 1: Move external datasource and mapping outcomes to Integration

The five obsolete Base candidate IDs are removed without aliases. Their function dispositions move to Integration and are split across the already-approved Integration contracts according to their actual business outcome:

| Obsolete candidate ID | Stable function ID | Replacement Capability | Owner | Consumer |
|---|---|---|---|---|
| `base.external_datasource.change.apply` | `rest:POST:/api/ext-datasources` | `integration.connector.create` | Integration | REST |
| `base.external_datasource.change.apply` | `rest:PATCH:/api/ext-datasources/{gid}` | `integration.connector.update` | Integration | REST |
| `base.external_datasource.change.apply` | `rest:DELETE:/api/ext-datasources/{gid}` | `integration.connector.archive` | Integration | REST |
| `base.external_datasource.connection.test` | `rest:POST:/api/ext-datasources/{gid}/test` | `integration.connector.connection.test` | Integration | REST |
| `base.external_datasource.search` | `rest:GET:/api/ext-datasources` | `integration.connector.search` | Integration | REST |
| `base.external_datasource.search` | `rest:GET:/api/ext-datasources/{gid}/tables` | `integration.connector.schema.discover` | Integration | REST |
| `base.external_mapping.change.apply` | `rest:POST:/api/ext-mappings` | `integration.mapping.create` | Integration | REST |
| `base.external_mapping.change.apply` | `rest:PATCH:/api/ext-mappings/{gid}` | `integration.mapping.update` | Integration | REST |
| `base.external_mapping.change.apply` | `rest:DELETE:/api/ext-mappings/{gid}` | `integration.mapping.archive` | Integration | REST |
| `base.external_mapping.change.apply` | `rest:POST:/api/ext-mappings/{gid}/import` | `integration.sync.start` | Integration | REST |
| `base.external_mapping.change.apply` | `rest:PUT:/api/ext-field-mappings/batch` | `integration.mapping.update` | Integration | REST |
| `base.external_mapping.read` | `rest:GET:/api/ext-mappings` | `integration.mapping.search` | Integration | REST |
| `base.external_mapping.read` | `rest:GET:/api/ext-field-mappings` | `integration.mapping.get` | Integration | REST |
| `base.external_mapping.read` | `rest:GET:/api/ext-mappings/{gid}/columns` | `integration.connector.schema.discover` | Integration | REST |
| `base.external_mapping.read` | `rest:GET:/api/ext-mappings/{gid}/preview` | `integration.mapping.preview` | Integration | REST |

Integration owns `workmanship_int_ext_datasources`, `workmanship_int_ext_mappings`, and `workmanship_int_ext_field_mappings`; Plan 12 migrates them to `ai00_integration` and exposes them only through the Integration Provider. Base code, Base migrations and Base runtime credentials must not reference these tables.

The old REST URLs may remain temporarily as protocol-only adapters. Each adapter must pin the replacement Capability ID and major version and invoke Catalog + Gateway. It may not import an Integration application, provider, service or repository module, and may not execute SQL. Plan 15 deletes the compatibility routes after parity evidence passes. No obsolete `base.external_*` Capability alias is published.

## Decision 2: Remove three operations mechanisms from the business Catalog

| Removed ID | Affected function | Final treatment | Owner | Consumers |
|---|---|---|---|---|
| `system.worker.outbox.health` | `capability:system.worker.outbox.health` | Authenticated operations/health endpoint outside the business Catalog | Base operations | None through Capability Gateway |
| `plugin.upgrade.finish` | `capability:plugin.upgrade.finish` | Trusted deployment-health callback authenticated by the Plugin Platform control plane | Base / Plugin Platform internal | Deployment controller only |
| `base.plugin.marketplace.usage.close` | `rest:POST:/api/v1/plugin-marketplace/usage/months/{month}/close` | Scheduled/admin accounting operation outside the business Catalog | Base / Plugin Platform internal | Operations only |

These mechanisms retain authentication, authorization, audit and tenant isolation appropriate to operations endpoints. Removing them from the business Catalog does not make them public or ungoverned. They must not be discoverable as Plugin, Agent or MCP tools.

## Migration and compatibility rules

1. Update the two domain review files and regenerate all coverage documents; do not hand-edit generated files.
2. Base finalization removes the three operations descriptors and excludes all five obsolete `base.external_*` IDs.
3. Integration finalization publishes the replacement contracts and owns the three Integration tables and migration stream.
4. Existing REST clients keep their URL and response compatibility only through Gateway adapters until Plan 15 parity passes.
5. There is no dual write, shared database credential, cross-domain SQL, internal Integration import, or implicit fallback to the legacy router implementation.
6. Catalog release notes record removed IDs and replacement IDs. Because the five obsolete IDs were candidate-only, they receive no runtime Capability aliases.

## Required evidence

- Frozen review validation reports 752 stable functions and zero unreviewed functions after the correction.
- Base Provider registration contains none of the eight removed IDs.
- Integration Provider contains every replacement ID used by the affected REST functions.
- Base runtime database access to Integration tables is denied.
- Compatibility REST tests prove the same response contract through Catalog + Gateway.
- Consumer bypass and boundary scanners report no SQL or internal imports in the compatibility adapters.
