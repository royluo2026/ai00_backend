# Local Integration Protocol V2

This document is normative for Base, Local Integration plugin, Windows Runtime, Session Host, plugin developers, and AI consumers. Capability-specific inputs and outputs are defined in `docs/capabilities/local-integration/`.

## Trust boundary

Public invocations contain domain values and immutable references only. A caller must never provide a local path, object-storage key, download URL, pipe name, signing key, or COM object identifier. The Gateway authorizes the caller and selected `device`/`artifact` resources before the Local Integration provider queues an operation.

A workstation belongs to its enrolling user and may optionally be assigned to that user's active tenant. Invocation accepts either the owner or a caller in that exact trusted tenant context; arbitrary caller-supplied tenant IDs are rejected at enrollment.

Web and API identities are not granted global `device:*` or `artifact:*` scopes. When ordinary ABAC evaluation reports an exact resource-scope denial, the Base-owned resource-authorizer registry may prove each requested reference independently: Local Integration owns the `device` resolver and Base owns the `artifact` resolver. The Gateway retries authorization with only those exact references. An unknown resource type, a missing resolver, any unresolved reference, or a resolver failure denies the complete invocation. A domain may register one resolver implementation for a resource type; alias imports and hot reloads of that same source implementation are idempotent, while different source code cannot replace it at runtime.

The control plane signs a closed `ai00.local-operation.v2` envelope over canonical UTF-8 JSON. The signature is HMAC-SHA256 and includes the tenant, operation ID, capability ID, complete payload hash, key ID, issue time, and expiry. Servers and devices may hold multiple key IDs during rotation. The active server key is configured by `AI00_LOCAL_OPERATION_SIGNING_KEY_ID` and `AI00_LOCAL_OPERATION_SIGNING_SECRET`; the Session Host accepts the corresponding semicolon-separated `key-id=secret` key ring in `AI00_LOCAL_OPERATION_KEYS`.

## Execution sequence

1. Capability Gateway creates the durable Base `OperationRef`.
2. The Local Integration provider queues a command whose ID is exactly the Base operation ID.
3. An authenticated device leases the command. Base reconciles the operation to `claimed` and the response carries the signed operation plus an opaque lease ID.
4. For `vismockup.model.open`, the Runtime requests a short-lived download grant only for the `ArtifactRef` already embedded in that active lease. It writes to a device-owned cache, rejects size/hash mismatches, and atomically publishes the verified file.
5. The Runtime sends the signed cloud operation and local materialization evidence through the restricted named pipe. The Session Host verifies the cloud signature, expiry and payload hash, then independently verifies cache containment, byte size and SHA-256 before opening the file.
6. The Session Host writes `started` to a bounded durable ledger before COM execution. A process restart converts unresolved `started` records to `outcome_unknown`; duplicate side effects are never replayed automatically.
7. The authenticated device reports only `completed`, `failed`, or `outcome_unknown` with a stable sanitized error code. The adapter first durably stores a `pending_*` device outcome, then reconciles the Base operation and only then publishes the device terminal state. Every subsequent lease poll retries pending reconciliation, closing the cross-database failure window without replaying the local action.

Consumers poll the returned Base `OperationRef`. After it reaches `completed`, they call `local.command.get` with the same operation ID to obtain the capability-specific result. A capture result contains an `ArtifactRef`; it never contains a workstation path.

## Operational requirements

- Runtime and Session Host must run under the same configured Windows identity when `PipeOptions.CurrentUserOnly` is used. Deployments requiring separate identities must provision an explicit two-principal pipe ACL before changing service accounts.
- `AI00_LOCAL_ARTIFACT_CACHE` (Session Host) and `LocalRuntime:ArtifactCacheRoot` (Runtime) must resolve to the same non-user-writable cache root.
- TLS and device credentials protect the lease channel; the HMAC protects the operation after it leaves that channel.
- A signing-key outage fails closed. A missing artifact, mismatched immutable reference, expired lease, hash mismatch, or unrecognized capability also fails closed.
- `outcome_unknown` requires operator or domain reconciliation. Plugins and agents must not blindly retry a write operation.

## Compatibility and verification

Canonicalization and signature compatibility are locked by `backend/tests/fixtures/device_protocol_vectors.json` and both Python and .NET tests. Protocol changes require a new protocol value, new shared vectors, dual-read migration, and a documented retirement window; silently changing canonical JSON is forbidden.
