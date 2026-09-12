# Reverse-station screenshot checkpoint (2026-09-12)

## Intended result

Capture stations in descending Craft `sort_order`. Within each station, capture one PNG per process in reverse process order, then attach each ArtifactRef to that exact BOP process. When a BOP has operations directly under stations, keep one PNG per operation.

## Implemented and checked

- The manifest groups child operation products and resources under their owning process, without generating extra child-operation screenshots. Its cumulative product scene remains keyed by the process ID. `CaptureWorkflow.start_capture` orders plans by descending execution sequence.
- The V1 Service and interactive SessionHost now share a ProgramData capture directory, so the Service can read PNGs written in the user session.
- The V2 App Host uploads PNGs under the authenticated lease and step, records only the returned ArtifactRef in its signed outcome, and quarantines uncertain uploads. The server authorizes the exact leased capture step before accepting bytes.
- The existing prepared Simulation workflow now routes its V1 intent to a freshly signed V2 plan when the bound runtime is Electron. The V2 projection must match the persisted V1 plan's identity, steps, payloads, hashes, and effect classifications before changing capture state. Direct Service runtimes continue to use the V1 queue.
- Capture admission for an Electron runtime requires materialization completed in that exact runtime generation and instance. If the App restarted, the browser prepares and separately dispatches a new materialization before starting capture.
- Materialization and capture action previews now target the new `simulation.connector.plan.queue@3` contract for complete workstation plans. The existing `@2` snapshot-only contract remains unchanged. The prepared action remains separately confirmed before dispatch.
- The App heartbeat now carries its actual adapter contract and product-version probe. Preflight accepts the V1 prepared intent only when it can be bridged to a fresh authenticated V2 App session with matching adapter operations; the advertisement is session-bound in Simulation's runtime device row.
- Simulation preflight calls `simulation.connector.health.get@2` under `simulation.use`; the legacy `@1` `agent.run` contract remains intact.
- Craft screenshot attachment now accepts both `process`/`bop_process` and direct operation node types.
- Verification: Connector project 230/230, Python HTTP/capture/manifest/Craft boundary 33/33, frontend capture workflow 7/7. These are code-level tests, not a live VisMockup capture.

## Remaining before runtime verification

1. The V2 plan producer/projection bridge has code-level coverage but has not been exercised against a real paired Electron App and database. The installed legacy Service binary predates the shared capture-directory fix.
2. No backend listener or isolated test database was configured in this worktree. `backend/.env` lacks `AI00_SIMULATION_TEST_DB_URL`. Migration `0023_connector_app_adapter_health.sql` still needs to be applied in an isolated test database before a live run. A BOP version with station/process hierarchy and an open VisMockup model are needed. Use only a configured test database and `test_` tables for local validation.
3. Verify each produced PNG's scene and BOP attachment, including all station/process boundaries, in an interactive session. The local scene controller does not yet save and restore the pre-run scene; this remains an acceptance gap.
4. Offline governance scan is blocked by `pinned_product_descriptor_count_mismatch` (checked release: 546 stable descriptors; scanner pin: 545). Generated Catalog and checked release also differ. Do not adjust the pin or publish the release solely to clear this gate.

Evidence is kept separate: `machine_passed=false` while the governance scan is blocked; `human_approved=unverified`; `runtime_verified=unverified`.
