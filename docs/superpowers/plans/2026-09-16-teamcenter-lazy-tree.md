# Teamcenter Lazy Tree Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement task-by-task with independent review.

**Goal:** Show root plus direct children without full expansion; load the next level only when requested.

**Architecture:** Keep existing full snapshot APIs unchanged. Add a read-only children operation backed by local SQLite; frontend model documents use this separate partial-tree path. Reopen a read-only BOM window and resolve a stable occurrence path with single-level calls, never reuse expired BOMLine UIDs. Cache hits avoid worker launch.

**Tech Stack:** Existing Java SOA SDK/Nashorn, .NET Connector/SQLite, Python capability provider, vanilla JavaScript model tree.

**Spec:** User-approved requirements below are the binding specification.

## Global Constraints / Specification

- Root is level 1. Initial response contains root and one direct-child page only.
- Only expandPSOneLevel on the requested path; no expandPSAllLevels or geometry relation/download calls on browsing path.
- Product structure stays read-only; no Teamcenter save/set/delete operations. AH and VisMockup launch/binding remain unchanged.
- Every node uses source-scoped full occurrence identity. Preserve repeated components; never identify by name, child index, or revision alone. Missing or ambiguous stable occurrence tokens fail closed for deeper navigation.
- Distinguish unloaded/loading/loaded/failed. An unloaded node is not a leaf. Failed expansion retains visible nodes and supports retry.
- Cache partitions include authenticated principal, full source/configuration selector, parent path and projection. Expose captured_at/cache_hit and cache generation; never claim the partial tree is a complete snapshot.
- SDK single-level response has no pagination parameter: it may return all direct children. Page serialized responses/property hydration (max 500), never recursively prefetch. State this limitation explicitly.
- First implementation reopens a BOM window and resolves ancestors on cache misses. This costs login and depth-dependent calls, but avoids retaining expired session handles. Optimize persistent sessions only after timings justify it.
- Continue using existing test worktrees; preserve unrelated dirty changes. No production writes, credentials in logs, raw secrets, or automatic remote push.

## Wire contract

New atomic `teamcenter.product_structure.children.read@1`, queued by `simulation.teamcenter.product_structure.children.read.request`.

Input: `{source_selector, parent_path, cursor, page_size, refresh, generation}`. `parent_path` is an array (max 128) of `{occurrence_uid, item_revision_uid}` stable edge tokens; empty means root. Cursor integer >=0; page_size 1..500; refresh boolean. Source selector is the existing strict six-field selector. Generation is a required nullable string: null for cursor zero, nonempty for later pages; refresh only allowed at cursor zero with null generation.

Output: `{source_identity_hash, captured_at, cache_hit, generation, parent, nodes, cursor, next_cursor, child_count, complete:false}`. Parent and nodes are lightweight records `{occurrence_id,parent_occurrence_id,occurrence_path,depth,child_order,name,item_revision_uid,revision_id,component_type,has_children}`. has_children is boolean or null (unknown, still expandable). parent is requested parent, nodes only its direct children. occurrence_id = hash of source identity and full path; root has empty path. generation pins paging: subsequent pages must not combine changed child lists; stale requests fail with a safe explicit code. Implementation may add generation input before exposing contract, keeping all consumers aligned.

### Task 1: Runtime single-level read and cache

Files: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/TeamcenterReadOnlyRuntime.cs`, `teamcenter_readonly_worker.js`, focused new tests under `local-runtime/tests` and existing .NET test project. A focused helper file is permitted to avoid enlarging runtime unnecessarily.

- [ ] Add failing behavior tests: root loads only direct children, path chooses occurrence+revision (same names remain distinct), ambiguous/missing edge fails, partial errors fail, no geometry calls, cache hits skip worker, paging generation stable, different principal/selector do not share cache.
- [ ] Implement worker `children` command and runtime `ReadChildrenAsync(JsonElement,CancellationToken)`. Resolve source/rule as existing observe; select exact SDK single-level overload. Apply configuration time using documented SDK field (verify reflection). Avoid hydration of unrequested descendants. Capture source/runtime failure without treating it as empty success.
- [ ] Add SQLite children cache isolated from tc_observations; retain existing snapshot integrity rules. Session/credential changes cannot reuse another user's cache. Refresh replaces only matching parent generation atomically.
- [ ] Run focused Node and .NET tests, record actual red/green evidence and interface output, self-review. Do not activate or deploy incomplete runtime alone.

### Task 2: Governed connector operation

Files: `VisMockupAdapter.cs`, simulation `capabilities/connector_contracts.py`, `connector_runtime.py`, existing atomic contract/allowlist assets and tests discovered from existing observe operation.

Shared path authorized during implementation: `local-runtime/src/Ai00.Connector.AppHost/PlanExecutionWorker.cs` for children-only timeout isolation. Children timeout waits up to five seconds for adapter cleanup; confirmed cleanup avoids host restart, while unconfirmed cleanup retains restart protection. `TeamcenterReadOnlyRuntime.cs` subprocess cleanup confirms owned-process exit within five seconds after Kill. COM timeout behavior remains unchanged.

Approved shared runtime path: `local-runtime/src/Ai00.Connector.AppHost/PlanExecutionWorker.cs` plus focused execution tests. Current blanket timeout restarts Connector. Exempt only new `teamcenter.product_structure.children.read@1`, whose independent Java process is cancelled/killed by its worker; preserve COM/native timeout restart behavior. Verify cancellation releases its runtime gate; do not turn this into a generic exemption for arbitrary read operations.

- [ ] Add failing schema/contract/dispatch tests for children operation, including closed inputs and generation paging.
- [ ] Register exact runtime DTO contract, adapter operation/hash, queue provider mappings and native capability manifests. Keep read-only risk, no confirmation bypass, no fallback to full observe.
- [ ] Run contract/provider tests and regenerate catalog through existing generator. Do not fabricate governance approval or touch production.

### Task 3: Model tree lazy browsing

Frontend files: `packages/sim-plugin/web/cad_sim/teamcenter_online_source.js`, `cad_sim.js`, `model_document_collection.js` and their focused tests; existing renderer as necessary.

- [ ] Add tests that initial add binds source then calls children (not observe), renders root+children, expansion fetches one parent, repeated click deduplicates, collapse while loading stays collapsed, environment/source changes discard late results, failures retain nodes, unknown children show disclosure, complete snapshots retain existing path.
- [ ] Keep observeAndPersist for explicit full snapshots. Add children read helper and partial-tree state using actual contract from Task 2. Reopening source uses SQLite cache through Connector; no localStorage or full background validation.
- [ ] Integrate model document add/reopen/refresh and tree disclosure; disable misleading parent selection for unloaded descendants unless VisMockup supports subtree operation independently. Never report partial local subset as whole subtree selected.
- [ ] Run frontend focused/full tests and build; report before/after production artifact checks.

Code-inspection notes for Task 3:

- `productNode()` currently prefixes node_key with `tc:` but not parent_key. Correct both for actual child records and add a forest topology test; existing one-node fixture concealed this bug.
- `_refreshModelDocuments` currently rejects a bound online source without observation_id. New source should use children browsing; only explicit snapshot path requires observation_id. Do not auto-run observe to fill it.
- `_addTeamcenterSource` must call bind-and-browse instead of observeAndPersist. Bind persists source even if first read fails: show retry on the registered document, not falsely report full import success or rebind a duplicate.
- `tree_projection_cache.bindView()` restores expansion by calling `.click()`. Restoring many unloaded disclosure controls must not implicitly read all descendants. Add explicit restoration handling: restore cached nodes only, leave uncached expansion for user input.
- Existing projection cache is SQLite UI acceleration; it must not suppress explicit refresh, bypass authenticated Connector validation for new child reads, or persist nonserializable promise state.
- Node identity for a lazy record is source/path scoped, but rendered identity also remains scoped to document_gid so repeated insertions stay separate. Parent key is `tc:${parent_occurrence_id}` except null root.
- Fresh add shows the document and root expanded once so the fetched second level is visible immediately; subsequent user collapse must be respected. Never trigger second-level child reads merely to show the already-fetched level.
- On loading additional siblings, preserve the parent's pinned generation and do not blend refreshed sibling sets with an old continuation. Show a bounded `加载更多` action rather than automatically draining all pages.
- Existing Teamcenter nodes have no document_session and cannot claim runtime visibility control. Keep safe disabled state rather than treating currently loaded children as all descendants.
- Add children capability to `_visQueuedReadCapabilities` so admission/serialization follows existing governed read path. Suppress duplicate expansion requests and stale render callbacks; do not enqueue restored UI expansions for uncached descendants.

### Task 4: Review and runtime verification

- [ ] Independent review of read-only boundaries, occurrence identity, cache partition/generation, late response handling and partial-vs-full semantics.
- [ ] Build Connector and test app, regenerate test candidate only with existing scripts. Restart owned AI00 test app if required, do not restart VisMockup or close documents.
- [ ] On W10 measure initial root/direct-child delivery and one node expansion separately; report measured time, cache-hit time, returned node counts, and no full-tree/geometry traffic. If normal authentication is unavailable, report runtime verification unverified rather than invent success.

## Preflight

Existing full observation reads all 14,416 lines and all geometry links, about 164 seconds in latest run, then fails occurrence validation. SDK reflection confirmed expandPSOneLevel (2008_06) and response shape. No server-side pagination is asserted. All tasks preserve existing full snapshot contract.
