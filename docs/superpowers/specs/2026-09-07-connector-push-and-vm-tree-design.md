# Connector Push Wake-up and VM Tree Design

## Goal

Remove avoidable Connector command latency without bypassing Capability governance, and load the VisMockup structure tree through the governed Connector path instead of the disabled loopback Bridge.

## Design

The backend exposes an authenticated, outbound-only WebSocket for each paired Connector. It carries only `ready`, `plan_available`, and keepalive messages. A queued signed plan notifies an in-process Simulation-owned wake broker; the Connector immediately uses the existing authenticated HTTP lease endpoint, verifies the signed plan, executes it, and posts its signed outcome. A two-second HTTP poll remains only as recovery when WebSocket delivery is unavailable. Queued work is drained without sleeping between plans.

The VM tree reuses the existing `simulation.document_snapshot.request@2`, `action.get@1`, `dispatch@1`, and `get@1` workflow and its `vismockup.document.snapshot@1` Connector atom. The page prepares a bounded request, obtains explicit downstream confirmation for the exact immutable plan, dispatches it, waits for the persisted outcome, converts its flat bounded node list into the existing tree view model, and renders it. No browser-to-loopback call is restored.

## Boundaries

- Owner: `simulation`.
- WebSocket is transport signalling only and cannot carry or execute plans.
- Existing Connector credentials authenticate the WebSocket.
- Existing plan signatures, hashes, leases, idempotency, permissions, audit, and outcomes remain authoritative.
- The fallback poll prevents lost wake-ups and supports deployments where WebSocket affinity is unavailable.
- Snapshot confirmation remains governed by the current stable Capability contract; no approval is fabricated or bypassed.

## Verification

- Backend broker and plan-queue notification tests.
- Connector worker tests proving immediate drain and wake-or-fallback behavior.
- Frontend tests proving the VM tree no longer calls `_bridge` and converts bounded snapshots correctly.
- Existing Connector, Simulation control-plane, Catalog, docs, and browser runtime checks.
- Runtime latency measured from plan creation to Connector step start.
