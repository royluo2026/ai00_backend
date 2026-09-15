# Live document synchronization implementation plan

> Execute inline with superpowers:executing-plans. Preserve unrelated edits. This replaces the superseded live-hierarchy-sync plan.

**Goal:** Bind existing VisMockup documents to Simulation environments, preserve repeated model insertions and incrementally synchronize AH references without reloading CPS.

**Architecture:** Simulation owns saved definitions, observation staging and bindings. Connector supplies session-scoped reads and bounded native edits; Electron coordinates selection, not business persistence. Existing-document adoption uses the same binding and observation path as ordinary synchronization.

**Tech Stack:** Python domain/repository, existing MySQL storage, .NET Connector/SQLite cache, Electron/JavaScript.

**Spec:** ../specs/2026-09-14-online-vismockup-environment-sync-design.md and ../specs/2026-09-14-large-structure-sync-design.md.

## Constraints

- Test worktrees only. No deploy or production migration.
- No document reload for AH edits; no original CPS mutation or geometry loading for structure reads.
- Source identity, insertion instance, occurrence and document session are distinct.
- Partial observations never authorize deletion; unknown write outcomes never authorize replay.
- No new executable exposure until current Catalog/Descriptor/Provider/consumer checks are complete. Machine tests are not human approval or runtime evidence.
- Batch targets: 10 ms/32 native calls, child page 256, server page 1,000/1 MiB, backpressure at 80%, resume at 40%. A blocking native call is not preemptible.

## 1. Reconciliation and reference identity

- [x] Implement immutable, session-scoped three-way AH merge in `domain/live_hierarchy_sync.py`; test conflict, partial reads, cycles and 10,000-deep trees.
- [x] Require insertion instance and occurrence alongside source identity; test repeated sources and retarget conflicts.
- [x] Verify timestamp provenance and repeated observation stability in the import projection.
- [x] Exercise 100,000 siblings without claiming native performance from Python tests.
- [x] Exercise independent 10,000-AH observations with one shared model-instance index per observation revision (pure-domain test; native throughput remains unverified).

Run: `py -m pytest plugins/simulation/tests/test_live_hierarchy_sync.py -q -p no:cacheprovider`.

## 2. Existing-document import projection

- [x] Implement a pure validated import projection consuming session-scoped model/AH observations, preserving distinct source instances and first-seen times. It must not invoke file open/export or native mutations.
- [ ] Test existing binding reuse, same-name source instances, absent insertion timestamps, mismatched sessions and partial data. Keep unresolved references as explicit incomplete state.
- [ ] Do not wire a UI action that reports success until durable creation, binding and observation receipt are connected.

## 3. Durable binding, staging and contracts

- [ ] Inspect actual Registry and existing `workspaces.py`, `alternate_hierarchies.py`, `connector_runtime.py`, model-document/placement schemas and migration 0018 before adding exposures.
- [ ] Reuse model record identities where compatible; add explicit timestamp provenance and runtime instance mappings without deduplicating by source hash.
- [ ] Add transaction-scoped create-and-bind with document-session uniqueness, tenant authorization, idempotency and recovery. Repeated requests return the same environment; unauthorized bindings do not reveal identities.
- [ ] Add bounded observation staging under an immutable observation revision. Validate page replay/content mismatch and session fences before committing a complete AH baseline.
- [ ] Version changed insertion semantics consistently across Connector manifests, request/result schemas, Provider, plan signatures, recovery and consumers; retain old @1 behavior until migration.

## 4. Native document adapter

- [ ] Replace research addresses with validated version-scoped document discovery before enabling native AH operations.
- [ ] Verify model-instance enumeration/readback, particularly repeated same-path entries; a preexisting path must not count as successful new insertion.
- [ ] Verify virtual-group create/move/delete, read-only structural lazy expansion, document activation and closed/reused-session rejection.
- [ ] Feed bounded pages and deltas through one serialized process executor; unknown effects quarantine further writes until readback.

## 5. UI integration

- [x] Build and test `document_session_coordinator.js`: generation fencing, delayed A/B selection, unbound contexts, native selection and failed attachment cleanup.
- [ ] Wire authorized adapters and existing selectors; selector UI must not perform persistence decisions.
- [ ] Add “从此文档创建仿真环境” to document menu; reuse existing binding or create importing environment, show model/AH progress separately from viewport attachment.
- [ ] Preserve selected B while adoption of A completes; no automatic focus steal. Test document close and connection loss.

## 6. Acceptance

- [ ] Controlled runtime: import existing document, mixed repeated sources, manual AH readback, A/B/A switching, close/reopen definitions and failed source recovery.
- [ ] Scale: one AH/100k nodes, 10k AH, 100k siblings, slow native calls, cancellation and reconnect; record actual timings and memory.
- [ ] Record exact governance version/definition hash/provider artifact/controlled run evidence separately from unit results.

## Evidence, not completion

2026-09-14: 68 focused backend tests and 14 coordinator tests passed. Source inventory was read from two live documents; reliable source-to-root mapping remains unverified. Durable bindings and UI adoption remain incomplete. No new Capability is advertised and no database migration has been applied. Test-governance configuration repairs are now user-authorized; inventory pin repair has 23 passing focused tests, but provider fingerprint and dedicated runtime configuration still block global governance verification. See `../specs/2026-09-14-live-document-sync-progress.md` for exact evidence and governance failures.
