# Live hierarchy synchronization implementation plan

**SUPERSEDED — do not execute this plan as written.** User clarified online-first model sources, direct CPS reading and bidirectional document/environment switching after this plan was drafted. Use `../specs/2026-09-14-online-vismockup-environment-sync-design.md` and `../specs/2026-09-14-large-structure-sync-design.md` as the current design; rewrite the execution plan after spec review. In particular, mandatory Artifact/PLMXML cold-open assumptions below are historical, not current requirements.

> Use executing-plans for inline execution. Preserve unrelated working-tree edits.

**Goal:** Synchronize AI00-owned alternate hierarchies and product references with an environment-bound live VisMockup document without structural reloads.

**Architecture:** Existing Simulation workspace/model-document/hierarchy/placement storage remains authoritative. A three-way merge of the last agreed state, current persisted state and complete native observations detects manual changes and conflicts. A document-scoped, versioned executor applies bounded batches and acknowledges only verified results. Runtime pointers never become persistent identities.

**Tech Stack:** Python Simulation Provider, existing SQL repository/artifact services, .NET Connector, Windows native document bridge, Electron simulation plugin.

**Spec:** User-approved design in this task: one runtime document per environment; first-open reconstruction from AI00 model artifacts; retained documents on switching; continuous persistence; manual round-trip limited to alternate hierarchy nodes and product references. Geometry, transforms, annotations and original CPS edits are excluded.

## Global constraints

- No reload on AH edits; no mutation of original CPS.
- No unverified snapshot interpreted as deletion. Conflict stops affected synchronization.
- Include tenant, environment, document session and revisions in execution scope.
- Persist model bytes/dependencies through existing Artifact ownership, not a new business blob store.
- Existing Capability contracts must not silently acquire new side effects; new exposure requires complete governed bindings.
- Thousands of hierarchies and tens of thousands of nodes must use bounded, resumable execution; UI scheduling budget is a tunable target, not guaranteed preemption of native calls.
- Ordinary test results do not constitute controlled VisMockup runtime or governance approval.

## Task 1 — Domain reconciliation

Files: `plugins/simulation/simulation_backend/domain/live_hierarchy_sync.py`, `plugins/simulation/tests/test_live_hierarchy_sync.py`.

- [ ] Write failing tests for one-sided changes, simultaneous conflict, deletion against edited descendants, duplicate identities, incomplete reads, cycles, scope changes and 10,000-node trees.
- [ ] Implement `reconcile(base, desired, observed)` with immutable snapshots of AH nodes only; validate complete same-session observations and bounded forests, produce merged nodes or explicit conflicts.
- [ ] Run `py -m pytest plugins/simulation/tests/test_live_hierarchy_sync.py -q -p no:cacheprovider`.
- [ ] Verify source inputs remain unchanged and merges are deterministic.

## Task 2 — Persistent synchronization and governed contracts

Reuse `data/workspace_repository.py`, `capabilities/alternate_hierarchies.py` and existing model-document Artifact references.

- [ ] Inspect actual Registry/Descriptor/Provider bindings before defining new operations.
- [ ] Persist exact base revision, observation identity, conflicts and pending operations with workspace authorization, optimistic concurrency and idempotency.
- [ ] Add bounded observation submission and delta retrieval contracts only after owner/atomicity checks; stale/partial reads must never remove records.
- [ ] Add transaction, cross-tenant, duplicate delivery and recovery tests before repository changes.

## Task 3 — Native bridge and executor

Owner: `local-runtime/src/Ai00.Connector.Adapters.VisMockup`; research evidence: `D:/Temp/vis/vismockup-live-alternate-hierarchy-crud.md`.

- [ ] Replace experimental hardcoded object discovery with validated version-scoped document discovery; implement typed bounded native commands, no arbitrary-address exposure.
- [ ] Validate group create/move/delete, multi-document activation and model insertion on user-authorized test objects before advertising support.
- [ ] Add serialized per-document execution, deadline slices, cancellation between calls, readback and uncertain-outcome reconciliation.
- [ ] Test long batches, switching mid-flight, stale document handles, crash/reconnect and restart; retain old document until persistence completes.

## Task 4 — Environment UI integration

Consumer: frontend test worktree `packages/sim-plugin/web/cad_sim/environment_workspace.js`, `model_document_collection.js`, `cad_sim.js`; native embed controller remains separately scoped.

- [ ] Drive enter/switch from selected workspace identity, never arbitrary active document.
- [ ] Display saved revision versus applied revision, progress, conflict and unavailable native support separately from embedded-window status.
- [ ] Add tests for late A responses after switching to B; no stale attachment or overwrite.

## Task 5 — Acceptance and evidence

- [ ] Cold-open from AI00 artifacts, A/B/A switching, manual AH round-trip and close/reopen reconstruction.
- [ ] Independently exercise many hierarchies and many nodes; measure native latency and interactive responsiveness.
- [ ] Record actual Capability versions, release hash, Provider artifact and runtime evidence; do not mark unsupported or simulated paths complete.

## Initial evidence

2026-09-14: existing alternate hierarchy Capability and materialization tests: 11 passed; pytest cache permissions produced warnings, not test failures. No production exposure or new Capability registered by this plan. Current rollout remains unverified.
