# Local viewer interaction — unpublished review candidate

This directory is an **unpublished five-capability subset**, generated from the
current Simulation Registry descriptors using the existing Catalog builder and
Capability documentation generator. It is not a replacement for the released
Catalog and is not a production release approval. Existing released snapshots
were not edited. The local test runner can assemble these experimental Provider
descriptors into its separate local Catalog as it already does.

## Main / page integration

All business calls use the existing authenticated Capability Gateway. The values
below are CapabilityOutput `data`, not an additional custom envelope.

1. `simulation.teamcenter.visualization.launch.request@2` takes the unchanged
   `{source_selector, expected_visdoc_uid}` request and returns the existing
   operation reference. The queued single step is `teamcenter.visualization.launch@2`,
   contract hash `sha256:807ebf90b7f92d994a1da3963c459191750fb21ca8890a096e3bb04d398e407a`.
   Its signed outcome contains `{protocol:'ai00.viewer.opened-source.v1', launch,
   document_identity}`. No independent current-identity lookup is required.
2. `simulation.environment.online_source.live_document.bind@2` takes exactly
   `{workspace_gid, document_gid, launch_operation_id,
   expected_workspace_row_version, idempotency_key}`. It returns the existing
   binding fields plus `source_association_id`. It rejects `identity_operation_id`.
   Evidence verification, runtime locks, binding mutation, source association,
   workspace revision and saved idempotency response share one SQL transaction.
   Major 1 retains its original input/output and separate identity behavior.
3. Main calls `simulation.viewer.interaction.scope.get@1` with
   `{workspace_gid, document_gid}` and receives `{source_association_id}`.
4. Main calls `simulation.viewer.interaction.authorize@1` with
   `{workspace_gid, document_gid, source_association_id, session_nonce,
   prior_grant_id?}`. `session_nonce` is 64 lowercase hexadecimal characters.
   The return value is the signed grant itself. First authorization omits
   `prior_grant_id`; renewal supplies the last grant ID. TTL is 60 seconds;
   Main renews at 30 seconds. The server allocates increasing generations and
   revalidates the owner, tenant, document source, binding and runtime each time.
   No plan/outcome lookup occurs during scope resolution or renewal.

Interaction ID is the grant's `session_nonce`. The signed grant stays in Main
and Connector. No timeout or unknown outcome authorizes automatic replay or
fallback to the cloud command path.

## Connector audit transport

`POST /api/v1/simulation/connectors/v2/viewer-interaction/events` uses the existing
`X-AI00-Device-ID`, `X-AI00-Runtime-Generation`, `X-AI00-Runtime-Instance-ID`,
`X-AI00-Runtime-Type: electron`, and `X-AI00-Runtime-Session` headers.

```json
{
  "protocol": "ai00.viewer.interaction.events.v1",
  "device_id": "device-1",
  "runtime_instance_id": "current-uploader-runtime",
  "device_key_id": "device-key",
  "events": [{
    "grant_id": "issued-grant-id",
    "interaction_id": "<64 lowercase hex session nonce>",
    "request_id": "request-1",
    "sequence": 1,
    "request_digest": "sha256:<64 lowercase hex canonical execute digest>",
    "operation_id": "vismockup.node.visibility.change@1",
    "outcome": {
      "request_id": "request-1",
      "status": "completed",
      "result": {"targets": [{"node_ref": "opaque-ref", "status": "completed", "error_code": null}]},
      "error_code": null,
      "timings": {"total_ms": 20, "com_ms": 10, "journal_ms": 1}
    }
  }],
  "signature": "<base64url unpadded low-S P1363 P256 signature>"
}
```

Signature bytes are UTF-8 `ai00.viewer.interaction.events.v1\n` followed by the
existing v2 canonical JSON encoding of the envelope without `signature`.
Every object is closed. Only finalized `completed`, `rejected`, `outcome_unknown`
outcomes are accepted; target status additionally permits `not_started`.
`result` may be null for recovered incomplete admissions. Timings are the three
bounded nonnegative numeric fields above, using zeros for unavailable values.
Errors are null or bounded lowercase snake_case codes, never raw COM text.

Server limit: 256 events, 256 targets/event, 1MiB body (enforced while streaming).
Uploader sends up to 128 events. Historical expired grants and grants from an
older runtime are accepted when their stored source still belongs to the same
device/owner/tenant. The uploader must authenticate its **current** runtime.
Uploading never restores execution authority. The server hashes the canonical
event (including outcome) for `(device_id, request_id)` deduplication: identical
events replay the acknowledgement, changed summaries reject the entire batch.

Successful HTTP response, emitted only after commit:

```json
{"success":true,"data":{"acknowledged_request_ids":["request-1"]}}
```

The local journal retains entries until those request IDs are explicitly acked.

### Immutable issuance evidence (0029)

Each new grant commits an append-only `workmanship_sim_viewer_grant_evidence`
row in the same transaction as allocation/signing. The row links the trusted
Gateway `outcome_operation_id`, retains the full signed grant and its canonical
SHA-256 digest, and retains exact Catalog release/hash, authorization descriptor,
Provider artifact and per-operation descriptor/version/business-definition hash.
Visibility and selection wire operations map explicitly to their respective
`simulation.vismockup.node.*.change.apply@1` descriptors. No wire changed.

Audit receipt checks persisted proof integrity and operation membership in the
persisted grant, not current operation constants. Missing proof (including old
0028-only grants) fails closed; no provenance is backfilled or invented. Expired
and old-runtime grants with valid evidence remain acceptable under current device
authentication. Catalog `cv2_` identities are not numeric governance-store GIDs;
no governance Snapshot, business approval or formal release is asserted.

The parent's applied 0028 remains frozen. Before the parent's backend switch,
prepare/apply **only 0029** from this worktree:

```powershell
python -m backend.scripts.prepare_viewer_interaction_test --check --migration 0029
python -m backend.scripts.prepare_viewer_interaction_test --apply --migration 0029 --env-file E:/Projects/ai00_v3/workmanship-backend/backend/.env
```

The apply command is for the parent/operator and was not executed by this worker.
It creates only `test_workmanship_sim_viewer_grant_evidence` and records 0029 in
`test_ai00_simulation_schema_migrations`; it does not apply all domain migrations.
0029 checksum: `500f4532fb576face066d5ce968c81a3d288f9beaaf28f07cee6269fed38404b`.

## Test-only database preparation

Run from the backend worktree:

```powershell
python -m backend.scripts.prepare_viewer_interaction_test --check
python -m backend.scripts.prepare_viewer_interaction_test --apply --env-file E:/Projects/ai00_v3/workmanship-backend/backend/.env
```

The second command is provided for the deployment operator; it was **not run**
as part of this implementation. It reads `USERS_DB_URL` like the local test
runner, fixes the prefix to `test_`, and applies only additive migration 0028.
It targets exactly `test_workmanship_sim_viewer_source_associations`,
`test_workmanship_sim_viewer_interaction_grants`,
`test_workmanship_sim_viewer_interaction_events`, plus the existing
`test_ai00_simulation_schema_migrations` ledger. It does not apply earlier
migrations, initialize old bindings as associations, or start/restart services.
Schema 0025/Connector runtime prerequisites must already exist as in the current
local test backend. MySQL DDL is not transactional; partial CREATE completion
can be resumed by the standard migration ledger and `IF NOT EXISTS` statements.

Generated docs can be verified without touching any released snapshot:

```powershell
python -m backend.scripts.generate_capability_docs --check --catalog docs/governance/local-viewer-interaction-candidate/catalog.json --output docs/governance/local-viewer-interaction-candidate/capabilities
```
