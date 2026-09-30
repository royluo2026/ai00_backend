# One environment, one native document

## Single model-tree root — September 29 follow-up

The corrected coordinate path below still created one imported hierarchy per open. The user therefore saw three identical environment roots after opening a bolt, its mount assembly and the front suspension. One document alone did not satisfy one environment root.

The environment now opens a named, empty PLMXML container and keeps exactly one replaceable assembly inside it. Expansion stages a cumulative assembly with each occurrence once, validates all cached world matrices, restores hidden states by occurrence identity, then removes the previous inserted assembly. The document handle and binding remain stable. An already loaded scope does not trigger replacement. No COM transform setter or name-based adoption is used.

Before replacement, the adapter checks that the existing inserted assembly is exactly the one it owns. It does not remove external/manual inserts. Expired previous JT dependencies cause an explicit no-effect error before replacing any geometry; temporary cache files are not assumed to exist permanently. Staging/validation failures attempt rollback to the prior assembly and fence further writes if the outcome cannot be trusted. Successful replacement logs `cache_environment_root_replaced` with the root and geometry counts.

A disposable native VisMockup probe opened the empty container, loaded one bolt, replaced its assembly with 39 occurrences and checked all matrices against the cache. Exactly one inserted assembly remained and the hidden bolt stayed hidden. The empty container has an internal hierarchy but no model-tree root. Evidence: workspace `.runtime/environment-placement-probe/single-root-probe-result.json`.

The regression first failed with zero replaceable assemblies, then passed. Current focused Connector suite: 62 passing tests, including single-root expansion, per-part scope, previous visibility, transform mismatch rollback, missing JT no-effect and protection of external inserts. Windows pipe/DPAPI tests required execution outside the restricted sandbox; all 62 passed there. The frontend suite passes 120 tests and its production build passes.

The self-contained Debug Connector was updated in AI00-Test (PID 239700). The assistant-created W10 test2 document was closed only after all 159 original matrices and visibility values were saved and confirmed unchanged. Actual App/Gateway/Connector checks:

- Bolt: operation `vismockup-command-e594c94a45a2a5fe51d2847cd28406dafb96389030aafec54624ebdb9c6b7558`, native handle 639, one assembly, one correctly positioned occurrence. Hide succeeded.
- Mount: `vismockup-command-7e2ee63eb728e4c7635bf5c44e1033a8dd482bc434d8611239d1b4efecc1de01`, same handle/session, one root, 39 unique occurrences and matching transforms; prior hidden bolt preserved. Four subsequent App actions verified assembly hide, selected-bolt show with same-revision sibling hidden and parent mixed, bolt hide and assembly show. The shared action path refreshed the existing tree without a manual post-action DOM sync.
- Front suspension: `vismockup-command-f8e11778d360cbdf4f1e512048719f4f1e395924551ac9644274bcb2f1bcd77a`, same handle/session, one root, 159 unique occurrences. Independent COM readback matched every cached world matrix and every pre-rebuild visibility value: 120 suspension occurrences visible, the prior 39 hidden.

Evidence: workspace `.runtime/single-root-native-1.json`, `single-root-native-39.json`, `single-root-native-159.json`, `single-root-before-reopen.json`, `single-root-mount-ui-proof.json`. Parent/suspension requests used their previously verified file receipts through normal cache-source admission; this is not evidence of fresh FMS download latency. The development page reloaded after a line-ending cleanup; its runtime tree context then required re-establishment. An attempt to rebind the prior admission failed with `cache_open_evidence_unavailable`; no native model write was attempted through that failed recovery. Final tree calibration uses fresh normal admission instead.

Final fresh admissions `vismockup-command-752796ac4581484d8f517a19cc1f2188474d889578ba332a23953ca7f034e5e9` (mount) and `vismockup-command-978c25fd6ab1ddeba62b256c578ad49d7196c178919281caf6df583709b78a72` (suspension) reused the same document with zero inserted geometry. The normally reloaded production bootstrap refreshed existing DOM rows: mount native/stored/checkbox all hidden; suspension native/stored/checkbox all visible and checked. The merged map contains 173 logical nodes. Evidence: `.runtime/single-root-final-tree-proof.json` and `single-root-suspension-ui-proof.json`. A separate standard native RootNode read returned the environment name and 159 children, confirming the empty container does not break ordinary product-root traversal. Temporary Main inspector is closed after verification. No full-W10, permanent JT retention, or formal release approval is claimed.

## Coordinate correction — supersedes the initial assembly-correctness conclusion

The initial verification below established document count and visibility only. The user's fastener screenshot exposed a real placement regression: each geometry instance had been made a PLMXML root, and VisMockup ignored that root's Transform. Independent native readback found all 39 matrices reduced to JT unit scaling with zero translation. Therefore the original run is not evidence of correct assembly placement.

The corrected adapter always retains an identity assembly root, including a single-part package. Geometry children keep the validated cached world matrices. Additional geometry is inserted as one positioned hierarchy, then loaded with AllNodesOn/UpdateView. Previously hidden native nodes are restored using both node key and CAD identity, including when loading throws. No COM transform setter is used. A direct setter experiment proved unstable and was abandoned.

After opening/appending, the adapter reads every expected geometry instance's GlobalTransformation and compares all 16 finite affine elements to the cached matrix (absolute tolerance 1e-8). Missing or mismatched transforms fail the operation and fence the environment until reopening. Logs include the offending occurrence and expected/actual matrix; successful checks record verified geometry count. Existing geometry is checked again after an append.

The disposable native probe passed with one document, 39 geometry instances, 39 matching matrices, and the previously hidden bolt still hidden. Evidence: `.runtime/environment-placement-probe/combined-result.json`.

## Corrected production App verification

Updated the App-owned Debug Connector using a self-contained win-x64 publish. The running native test process is 251228; the new Connector is 235452. Verified through the actual AI00-Test frontend/Gateway/Connector path in W10 test2:

1. First bolt open operation `vismockup-command-2463d3848f277095426e229792d80a08c016fe480e534e44549746a435dd67fd`: the adapter logged `cache_environment_transform_verified` with count 1. Independent COM readback matched the cached world matrix, including translation `(0.0635, 0.311, 0.330000004989237)` metres. The UI hide action left it hidden.
2. Parent open operation `vismockup-command-21d1f487b580995b193e93bb779daa702be20939f06f16a2f9f4abbd24f0d049` reused the 19 existing verified file receipts and retained session `sha256:16e133e236d6bb9d5a76224f6fae933ec8c36a7e8f41b591e5a086f4e7f56d0f`. Independent COM readback: **1 document, 2 internal hierarchies, 39 geometry instances, 39 matching cached world matrices, 38 visible**. The original bolt remained hidden. Geometry was appended as one hierarchy, not 38 flattened inserts.
3. App actions hid the parent, showed the selected bolt only, hid that bolt, and showed the parent again. The same-revision sibling stayed hidden when the selected bolt was shown, the parent reported mixed, and the final 40 loaded logical nodes reported visible. No separate document was created.

Local evidence: `.runtime/environment-app-coordinates-part.json`, `.runtime/environment-app-coordinates-parent.json`, `.runtime/environment-coordinate-final-ui.json`. The comparison source is the validated geometry/world transforms retained from the cached packages; this proves the native importer preserves those transforms, not that every historical TC cache value is correct. Missing cache placement remains excluded/unknown under the existing user-selected policy.

The final independent matrix read (`environment-app-coordinates-final.json`) again matched all 39 transforms and one document. Visibility was then 0: the controlled UI test had finished at 10:27:08Z, and the live logs recorded a subsequent hide/calibration at 10:27:34Z and a new front-suspension open request. These later actions were outside the controlled test. They were not overwritten. The saved UI proof reports the controlled sequence, not a permanent claim about the current user's visibility state.

Combined automated evidence after integration: Connector 74 passed; frontend 117 passed; backend 140 passed; production frontend build passed. No permanent local JT cache is required. The native document-manager DLL still requires an AI00 Main restart to replace the previously loaded module; COM provides the authoritative document count for this run.

## Change classification
Simulation implementation fix: the user requires one VisMockup document per environment, named after the environment, with tree-node scoped visibility. Selecting an assembly affects its subtree; selecting a part affects that occurrence only. Existing branches retain their state when another branch loads.

## Authoritative context inspected
CacheSourceOpenProvider, cache_snapshot_package, ManagedCacheOpen, AppArtifactMaterializer, ViewerNodeRegistry, frontend cache_snapshot_viewer and live_document_adoption, exact open@2 receipt/binding contracts. Native VisAutomation.tlb and a disposable real VisMockup insertion probe were inspected.

## Reuse, atomicity, and ownership result
Reuse the verified cache-open pipeline and native document InsertDocument. A multi-instance inserted PLMXML registers a hierarchy before loading its geometry into the active view. The corrected adapter activates that hierarchy and restores prior hidden states; it does not flatten geometry into roots. AllNodes identity and matrix readback verifies every expected occurrence before committing the logical graph; RootNode traversal alone misses inserted hierarchies.

## Implementation boundary
The simulation provider adds owned workspace/source-document context to the signed XML artifact. The native adapter maintains one environment document and a logical occurrence graph. World-coordinate geometry is inserted once per source occurrence; overlapping requests update the logical graph without inserting duplicate geometry. Visibility resolves the clicked logical node to its exact geometry descendants across native hierarchies. Names are labels, never binding identities. Existing online TC behavior remains on its existing path.

The current cache exporter already separates identity-transform logical groups from geometry children with validated absolute transforms. Only this explicitly marked layout may use the environment insertion path; arbitrary PLMXML and legacy packages retain their existing behavior. Local derived files preserve those absolute placements and refer only to already verified dependencies. Document lookup binds process start, native handle, and source path.

## Initial verification evidence (placement not verified; superseded above)
Automated verification on 2026-09-29:

- Backend package/open/binding/materialization tests: 58 passed.
- Connector CacheEnvironmentDocumentTests, ManagedCacheOpenTests, ViewerNodeRegistryTests: 72 passed. Includes first assembly open, overlapping part/parent requests, repeated opens, separate environments, safe names, retained hidden state, exact occurrence visibility, and registered-but-missing native geometry.
- Frontend cache_snapshot_viewer, cache_snapshot_ui, live_document_adoption, viewer_interaction: 81 passed.
- Compiled N-API and isolated Win32 selector/management tests passed under Node and Electron 41.8.0. New component-MDI regression failed before the production fix, then passed.

Real AI00-Test / VisMockup 14.2 verification used environment `230291366528323584` (`W10 test2 20260928193519`) and model document `230293311259316224`:

1. Open one bolt through the frontend cache controller; calibrate actual visibility, then hide it. Native readback confirmed hidden.
2. Open its 40-node parent through verified Gateway preparation using existing 19-file receipts. Operation `vismockup-command-08eae342555e9cee25646901cb786720c7054a446cfeb92f259a6fbfb774ffc1` retained document session `sha256:6a6ae94b2c36d24c0f943a9a6189834330a6def99d0606122225a3b8c12396f4` and the hidden bolt. This parent check reused receipts directly; it did not repeat the controller's FMS acquisition loop.
3. Hide the assembly; show only the chosen bolt. That occurrence was visible, another occurrence of the same revision stayed hidden, and the parent read back mixed. Hide the bolt and show the assembly: all 40 loaded logical nodes read back visible.
4. Independent native COM readback: exactly one document, handle `388`, filename `W10 test2 20260928193519.plmxml`, 39 native geometry instances, 39 distinct occurrence IDs, all 39 visible. The 39 internal hierarchies are inserts within that single document, not 39 documents.

Local evidence is saved under workspace `.runtime`: `environment-final-ui-proof.json`, `environment-native-verified.json`, `environment-electron-native-proof.json`. Old `environment-native-after-parent.json` documents the failed multi-instance approach and is not success evidence.

The native document list also selected the hidden in-process Visio `VISIOA` frame's empty MDIClient. Restricting frame discovery to the owning MFC frame fixes this. The corrected Electron module independently enumerated exactly one document with the environment filename. Its binary has been installed for the next AI00 restart; the currently running Main process still holds the old loaded module. The live environment/visibility Connector changes are already active. The current model was retained to avoid interrupting other AI00 pages.

## Governance status
No formal machine_passed or human_approved decision is asserted. Runtime evidence covers the exact real scenarios above; no full-W10 or every-device claim is made. No Catalog publication or database migration is part of this change.

## Findings and unresolved risks
Existing legacy per-branch windows require migration/closure only after their modification state is known. User-authorized test windows were closed before validation. A Connector restart with an old managed environment still open fails with `cache_environment_requires_reopen`, rather than adopting by display name or creating another document. Cold open previously hit `vismockup_document_limit_unverifiable`; this verification launched/probed the native application before opening and does not establish that transient issue as fixed. Cache materialization/preparation latency and the earlier front-suspension FMS failure are outside the proven fix. Temporary JT lifetime remains temporary; this change does not require permanent user-PC caching.
