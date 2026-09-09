# Digital Simulation Environment Redesign Governance Baseline

Date: 2026-09-08
Design specification: `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`
Catalog source: `docs/capabilities/catalog.v2.json`
Static catalog release: `rel_b4f751f7fde8f0a0ef3e9545aaf0b074`

This file records the implementation baseline. It is evidence for development and review; it is not an approval record. Runtime Registry and Snapshot verification must be added from an actual running environment before release.

## G0 Capability inventory

Static lifecycle inventory from the current generated catalog:

| Capability | Lifecycle | Implementation use |
| --- | --- | --- |
| `simulation.environment.compose@1` | stable | Existing stable route; no contract widening. |
| `simulation.environment.compose@2` | experimental | Development-only redesign candidate. |
| `simulation.document_snapshot.request@1` | deprecated | Must not receive new traffic. |
| `simulation.document_snapshot.request@2` | experimental | Development-only snapshot request. |
| `simulation.environment.materialize@1` | deprecated | Must not receive new traffic. |
| `simulation.environment.materialize@2` | experimental | Development-only materialization candidate. |
| `simulation.capture_run.start@1` | deprecated | Must not receive new traffic. |
| `simulation.capture_run.start@2` | experimental | Development-only reverse capture candidate. |
| `knowledge.resource_model_mapping.resolve@1` | stable | Exact reverse lookup for governed resource classification. |
| `digital_model.version.get@1` | stable | Existing digital-model version lookup. |
| `base.artifact.import@1` | experimental | Development-only raw PLMXML artifact import. |
| `base.artifact.get@1` | experimental | Development-only artifact metadata lookup. |
| `base.artifact.bytes.get@1` | experimental | Development-only bounded artifact byte retrieval. |

All `simulation.vismockup.*@1` entries in the current catalog are experimental:

- `application.attach.request`
- `application.launch`
- `application.launch.request`
- `capture.create`
- `command.get`
- `model.close.request`
- `model.open`
- `model.open.request`
- `selection.highlight`
- `status.get`
- `tree.get`
- `tree.read.request`
- `visibility.change.apply`
- `visibility.change.request`

The earlier unscoped `vismockup.*` entries are deprecated and have no exposure. New consumers must use the Simulation-owned contracts.

Approval and runtime evidence remain deliberately open for this implementation cycle:

- `human_approved: unverified`
- `runtime_verified: unverified`

No implementation task may change these values, promote a candidate to stable, or claim release readiness. The user will run one consolidated approval later.

Release policy is **stable-only release routing**. Experimental capabilities may be exercised only in the governed development/test environment and cannot be selected by a formal production release.

## G1 Connector v2 boundary

Every VisMockup business effect, including attach, export, tree read, highlight, visibility changes, model open/close, and capture, must follow this chain:

`Renderer -> Gateway -> Simulation Provider -> execution-plan.v2 -> ConnectorHost journal/Adapter -> COM -> outcome.v2 -> Simulation Provider projection`

Required properties:

- The Gateway resolves the Capability from the pinned catalog and invokes the registered Simulation Provider.
- The provider emits a signed, expiring, idempotent `execution-plan.v2` with bounded inputs and expected outcome schema.
- ConnectorHost validates the plan before writing the durable journal and invoking the VisMockup COM adapter.
- The adapter returns a signed `outcome.v2`; only the provider may project that outcome into Simulation state.
- Local recovery journals are encrypted, user/device scoped, bounded, and contain no reusable bearer credential.
- Teamcenter/PLMXML links are immutable source references. AI00 persists only snapshots, identity projections, bindings, arrangements, poses, and version lineage.

`IPC/named-pipe/WebSocket business bypass: forbidden`

IPC, named pipes, loopback HTTP/WebSocket, or Electron preload calls may transport an already-authorized Connector v2 envelope. They may not invent a second business API, bypass catalog resolution, perform an ungoverned COM action, or write authoritative Simulation state directly.

## Gate evidence status

| Gate | Status | Evidence required to close |
| --- | --- | --- |
| G0 | static verified; runtime open | Pinned runtime Registry/Snapshot readback and exact release comparison. |
| G1 | static boundary recorded | Focused gateway/provider/ConnectorHost tests proving signature, expiry, idempotency, and no bypass. |
| G2 | local passed | Six focused tests cover the real 21 MB sample, joins, identity fields, hostile XML and every parser limit; deployment worker memory quota remains a release check. |
| G3 | open | Identity/diff tests pass locally, but Teamcenter-launched window attachment, multi-window selection, ExportEx and recovery still require real VisMockup evidence. |
| G4 | local contract identified; owner approval open | Test DB and Craft sources identify `part_feed` as the authoritative field; Craft now projects `parameters.is_load_part`. Historical-false semantics and owner approval remain open. |
| G5 | partial; approval open | Private workspace/atomic CAS tests and Knowledge reverse-lookup unit tests pass. The governed Knowledge mapping table exists but contains zero test rows, so real resource classification remains unverified. |
| G6 | partial; runtime open | Canonical Artifact freeze saga now records completed, orphaned, and unavailable outcomes. Simulation-owned selective publish plan/map/outbox persistence exists. Integrated Windows x64 VisMockup and real Craft dispatch evidence remain open. |

## 2026-09-09 runtime data findings

- All reads used the configured test database and `test_` table prefix.
- Process/operation ontology definitions contain no Load-equivalent boolean property; the only boolean candidate is `critical_process`.
- Craft owns `part_feed` on BOP entries, process detail, and operation detail. Its standard-operation import maps `match_tag=part_feed` to this field.
- `knowledge.resource_model_mapping.resolve@1` owns the immutable resource-to-model mapping table. The test table schema is valid but currently has zero rows, so `model_ref_json.model_id` reverse lookup has no real-data evidence yet.
- The populated legacy resource catalog currently resides in `workmanship_craft_resource_requirements` and includes `attributes['TC数模号']`. Simulation must not read that table. A Knowledge-owned population/synchronization path is required before reverse classification can be runtime-verified.
- Candidate workspace and reverse-lookup handlers remain unregistered. No approval state or stable release was changed.
- Selective publish planning uses opaque `client_ref` values. The current Craft preview contract cannot resolve parent client references created in the same preview, so dispatch remains blocked until Craft owns and versions that contract extension.
