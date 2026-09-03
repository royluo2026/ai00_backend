# Capability V1 Retirement Runbook

Status: implemented on 2026-08-10. Owner: Base Platform.

## Retired kernel surfaces

| Retired surface | Last observed | Replacement Capability / surface | Owner | Rollback |
| --- | --- | --- | --- | --- |
| `/api/capabilities/*` | No production telemetry is available; repository consumers and the Web route scanner reported zero references on 2026-08-10 | `/api/v1/capabilities/*` | Base Platform | Revert the retirement commit only during a declared incident; do not run both URLs during normal service |
| `backend.capabilities.models` | No source imports found on 2026-08-10 | `backend.capabilities.models_next` and `backend.capability_v2.provider_contracts` | Base Platform | Revert the retirement commit with its matching tests |
| `backend.capabilities.registry` | No source imports found on 2026-08-10 | `backend.capabilities.registry_next`; consumers invoke through `CapabilityGatewayV2` | Base Platform | Revert the retirement commit with its matching tests |

The unversioned URL was a duplicate transport for the same kernel, not a business
endpoint. Repository scans, Web migration checks, Agent tests and MCP tests are
the available evidence. Because request telemetry was not historically retained,
the Last observed value is deliberately not represented as a fabricated timestamp.

## Legacy business REST observation boundary

The generated [User Function Registry](../governance/user-function-registry.json)
is the authoritative inventory for legacy REST, Web, Agent and MCP consumers. A
row may be deleted only after it has all of the following fields resolved:

- `owner` names the independently maintained domain.
- `target_capability` names a stable replacement, or `exclusion_reason` proves
  that the endpoint is transport/control-plane functionality rather than a
  plugin/AI business function.
- `migration_status` is `migrated` or `excluded`.
- deployment telemetry supplies a real Last observed timestamp and shows zero
  use for the agreed observation window.
- the domain owner records a rollback release or feature flag.

Do not delete a legacy business endpoint while its Last observed value is
unknown, while a Registry row remains `candidate`, or while any current consumer
is recorded. Such endpoints remain internal compatibility adapters and must not
be advertised as the plugin or Agent contract.

## Release checks

1. `test_capability_v1_retirement.py` proves that only the versioned public URL
   exists and that the obsolete kernel modules cannot be imported accidentally.
2. `test_no_registry_consumer_bypass.py` proves governed consumers do not invoke
   the in-process Registry directly.
3. The Web legacy-route checker must report zero direct Capability REST calls.
4. A rollback must restore route, modules and tests as one atomic deployment;
   partial rollback is unsupported because it creates two public contracts.

## Direct VisMockup capability retirement

The direct `vismockup.*@1` capability family is deprecated from the AI00 Web,
API, plugin, Agent and MCP surfaces. New workflows use
`simulation.environment.materialize@1` for active-document/BOM validation,
model attachment and scene construction, and `simulation.capture_run.start@1`
for reverse-process internal screenshots and Craft screenshot association.

The old operation IDs remain available only inside the AI00 Connector local
runtime as a bounded compatibility path. They are not an authorization surface
for arbitrary COM, scripts or MCP calls. Removal requires production usage
telemetry, a published sunset date, completed fake integration evidence and
real-workstation VisMockup evidence; until then rollback consists of restoring
only the prior exposure descriptor, never bypassing signed Connector plans.
