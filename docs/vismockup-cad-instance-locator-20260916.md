# VisMockup cached-instance relocation — 2026-09-16

## Scope

Recover node controls after explicit document rebinding without rescanning the full product tree for every control. Product structures, Teamcenter data and alternate hierarchies are not edited by relocation. Existing signed command and document binding checks remain in place.

## Evidence

Installed Visualization14 type library exposes `IVisDisp3DNode.CADID` (DISPID 19) and `IVisDisp3DView.GetNodeFromCADID` (DISPID 33). CADID contains the full occurrence path, including per-instance suffixes. Do not substitute display names or runtime numeric node keys.

Read-only probes against current W10 document handle 390 inspected 8 parts under W10-MDL2001, including six identical-name/version W01-89184128/00;1 parts. Their CADIDs were distinct. Native lookup returned each original node separately. It also worked on two unloaded assembly samples without calling geometry load or display operations. `catiaOccurrenceName` was available on loaded leaf samples but empty on assembly samples; it was not queried on unloaded samples.

The production .NET adapter repeated the 8-part lookup successfully. Initial dynamic dispatch/JIT cost was approximately 400–550 ms; subsequent lookups including verification were approximately 8–25 ms. These are small warm samples, not large-tree or cold-Teamcenter performance guarantees.

**Actual close/reopen stability is not yet runtime-verified.** No user document was closed, reloaded or switched. Session changes and reordered same-name instances are covered by deterministic tests. An unmapped native path fails closed; it never falls back to names or child order.

## Implementation

- Interactive tree reads collect lightweight CADID, not JT metadata. Optional fields default to empty for older readers/caches.
- SQLite `vm_cache_nodes` gains `cad_id` and indexed `control_key`. The key is `cad:` plus SHA-256 of the document source identity hash and complete CADID. Raw node keys and tree hierarchy remain unchanged.
- Tree results include `control_key`; existing frontend projection persistence retains it. Frontend actions accept an old-session node only when this locator is present, after checking the current environment/document binding.
- Runtime resolves the key in the newest retained source-scoped cache generation containing it, then uses native lookup and checks exact returned CADID and printable name. Multiple cache instances sharing one path are rejected. It does not cache raw runtime handles across node insertion/deletion.
- Later PLMXML snapshot projections or shallower reads do not immediately invalidate older locators. Existing cache budget/eviction still applies; evicted locators require recapture.
- Successful relocation does **not** mark the old structure snapshot fresh or prove unchanged geometry/version/configuration. It only identifies the node for the requested view operation.
- Old caches lacking IDs cannot be safely upgraded by guessing. One explicit structure refresh captures the missing locators. Subsequent session changes use native lookup where the paths resolve.

## Additional visibility bug

The pre-existing `CreateNodeList` dispatch discarded its return value, then attempted to add a node to `DBNull.Value`. Added a return-valued dispatch helper for that call only. A live same-state show operation on an already-visible bolt failed before this fix and completed after it with visibility unchanged. No all-model display/load operation was used.

## Verification

- Regression first failed for missing `control_key`, then passed after implementation.
- Snapshot replacement regression failed before the retained-generation lookup fix, then passed.
- Tests cover different runtime keys/order, same-name duplicates, different source rejection, stale native result rejection, SQLite readback, and colliding cached paths.
- 106 VisMockup tests passed; frontend 179 tests passed during this change.
- Live Python and .NET diagnostics: `E:/Projects/ai00_v3/.runtime/vis_probe/read_occurrence_identity_sample.py` and `E:/Projects/ai00_v3/.runtime/vis-cad-locator-check`.
- UI end-to-end after first locator capture, actual close/reopen, source configuration changes, and large cold-tree timings remain unverified. No production publication or remote push is implied.
