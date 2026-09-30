# Teamcenter bulk cloud cache design

## Intent and scale

The user rejected per-node cache scheduling for a vehicle containing about 10000 occurrences. Keep the existing standalone App, project/phase/version model, all TC values and JT references, and resumable cloud cache. Continue the same W10-2026 / SOP / v1 batch when the replacement is verified. Project-manager and scheduled triggers remain reserved. The instruction to design then execute still applies; execution is inline in this task.

The current implementation requires approximately N structure jobs and N property jobs. A warm job takes about 3 seconds, with another 6–7 seconds between jobs. At N=10000, a 20000-job design is on the order of 50 hours before extra property cost. Session reuse fixes repeated login but does not fix this scaling law. UI list/query reads refresh cached data; they do not perform TC collection and are not the cause of the per-node design.

## Alternatives and decision

1. Concurrent per-node jobs: retains tens of thousands of governed dispatches and many TC requests, increases load, and complicates session/ordering. Reject.
2. Pack legacy tasks into groups: improves dispatch overhead but retains separate structure/property tasks, repeated node requests and existing task proliferation. Useful fallback, not the target architecture.
3. Bulk BOM structure, bulk properties, durable local flat snapshot, bounded cloud pages: reuse the installed SOA APIs and existing SQLite/page machinery; this changes dispatch scaling to O(N/page_size). Choose this.

## Collection model

Use one authenticated, persistent read-only TC connection and one exact configured BOM window. Reuse `expandPSAllLevels` from the existing observe path, with `expItemRev=true` and the current explicit configuration date handling. Validate service errors, output mappings, node/depth limits, cycles and every occurrence edge. Construct a flat breadth-first table carrying full occurrence/revision paths, exact parent paths, child order and child counts. Derive occurrence IDs using the existing selector/path hash, not shared revision UID, VPPS or parent display names.

Do not copy the observe path's weaker error handling or temporary UID identity. Reuse its bulk SOA calls only. The eight exact instance metadata fields, torque/importance, revision/owner/type/weights, optional matrices and JT Dataset/file references retain current raw field names, object identity, null/value/unavailable states and strict reference-read failures.

Read properties in groups of at most 256 occurrences per native call; deduplicate ItemRevision objects within the group and cache verified revision/JT results within the source session. Required BOMLine and revision properties use bounded `getProperties` calls, relation expansion and Dataset/file property requests operate on sets. Formatting individual rows must issue zero TC requests. Optional fields preserve unavailable states; failed required/geometry requests must never be turned into empty success.

## Durable local snapshot and bounded transport

Add Simulation-owned local SQLite snapshot metadata and rows using the existing cache database. A snapshot is bound to cloud batch ID, source selector, principal and generation. Structure collection has a deterministic fingerprint and page cursor. Fetch native structure pages over the private persistent protocol, not through one cloud Capability per node and not as a giant stdout JSON result. Commit validated structure pages locally; mark structure ready only after the full topology validates.

For each cloud page, bulk-fetch missing properties for its flat rows, then persist the complete local row results before returning them. A replay uses the same saved page. After Connector restart, completed property pages remain available without TC reread. To collect unfinished properties, reopen BOM and bulk reconstruct its locator once, compare the topology fingerprint, then continue. A changed tree fails with a stale-generation error rather than mixing snapshots.

Start with 200 complete rows per cloud page, with a soft 4 MiB serialized payload cap and a hard 8 MiB contract limit. Smaller pages are valid if large raw values require them; a single oversized row is a stable error. No credentials, session tokens, FMS tickets or JT bytes enter the cache. A 10000-node vehicle normally requires approximately 50 cloud pages, rather than 20000 node jobs. This is a dispatch-count target, not an unmeasured wall-clock promise.

## Cloud checkpoint and existing batch continuation

Keep the current domain-owned tables, batch control and page-receipt transaction. Introduce an internal snapshot task kind in the existing VARCHAR task table. Each accepted flat page atomically upserts complete rows, commits its receipt and queues the next cursor. Validate source/principal/generation, contiguous cursor, row identities, parent path/order and final full graph/count before marking completed.

Migration 0032 adds nullable snapshot_generation and snapshot_position columns to the existing cloud nodes table, with a unique batch/generation/position index. Mark membership with each accepted row; reject identities already accepted on another page. Final membership count must equal the declared snapshot count as well as the complete batch count. This prevents an old node from hiding a duplicated or missing new snapshot member. Test deployments apply it through the existing test_ table projection and resumable domain migration tooling.

For an unfinished legacy batch, first settle any admitted legacy operation. Admit one deterministic snapshot task when the bound runtime advertises the new contract. Keep accepted data and receipts. Retire remaining legacy work explicitly as superseded, never fabricate completion receipts. Overlapping nodes must have matching occurrence paths and parent identities. The final snapshot must account for all pre-existing node identities; incompatible topology requires needs_refresh instead of deletion or silent reconciliation. No clear/recreate of the user's original batch.

## Capability governance

1. Classification: new major version of the existing Simulation-owned principal-pinned local cache read; compatible cloud advance implementation and internal task lifecycle changes. Keep `simulation.teamcenter.model_cache.read@1` and native `teamcenter.model_cache.read@1` available; add @2 for bounded complete snapshot pages rather than changing @1 semantics.
2. Authoritative context: current TC worker and installed SOA classes; existing observe/page/children/property contracts; Adapter advertisement and PlanExecutionWorker read classification; cloud Provider/Descriptor/dependencies; repository transaction, graph validator, test_ migrations and durable worker; generated Catalog and prior test runtime evidence. Exact new live Registry and signed release evidence remain unverified until the controlled rollout.
3. Reuse/ownership: all business behavior remains in Simulation. Reuse connection lifecycle, bulk SOA calls, SQLite, Gateway worker, deterministic signed plans, transaction participation and receipts. No direct browser TC connection, generic batch business bypass, new domain or product cron implementation.
4. Boundaries: Simulation native Adapter/worker and cache Provider/repository/contracts; shared Host changes are limited to recognizing the registered @2 read operation. Frontend progress rendering consumes existing batch metadata and query values.
5. Verification: native 10000-node call-count/topology tests, repeated-revision distinct-instance and all-field/JT regressions; real subprocess framing/lifecycle tests; SQLite resume/partial checkpoint/size/generation tests; cloud actual repository/Gateway transaction/receipt/upgrade tests; old/new advertisement/version/hash refusal; controlled TC W10 run with independent native and cloud timing evidence.
6. Status: machine_passed=unverified; formal human_approved=unverified; runtime_verified=unverified for the new @2 path. User repair authorization does not constitute formal exact-hash release approval.
7. Risks: all-level TC call duration and memory must be measured; optional-field partial errors must be classified carefully; source drift after restart must reject rather than mix; superseded task status affects monitoring; native responses and cloud result escaping require byte caps. Another task owns global backend blocking; do not modify Agent or its worker.

## Acceptance

- A synthetic 10000-occurrence vehicle uses one bulk structure expansion per live source session, set-based property/reference requests and roughly 50 governed data pages at the normal row/byte budget.
- Every occurrence, parent edge, requested TC value and JT reference is preserved; instance duplicates sharing a revision remain distinct.
- Pause/restart/replay resumes accepted local/cloud pages without clearing them, duplicate receipt or lost continuation.
- The actual test App uses the verified new Connector and the original W10 batch continues under the new path; report actual throughput and remaining bottlenecks, not just test counts.
