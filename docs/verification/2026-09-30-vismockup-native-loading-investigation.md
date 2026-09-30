# Installed VisMockup loading mechanisms

Read-only investigation of `D:/Siemens/Visualization14` on 2026-09-30, following the user's request to compare native loading with AI00. No Siemens files, settings or model transforms were modified. This is installation/interface evidence, not Siemens source code or a native cold-open benchmark.

## Confirmed installed interfaces

The embedded type libraries in `Program/VisAutomation.dll`, `VFMDoc.dll`, `PLMXMLLoader.dll` and `FMSService.dll` expose:

| Concern | Installed interfaces | Implication and limit |
| --- | --- | --- |
| Geometry loading separate from structure | `IDirectModelDoc.SetLateLoadShapes/GetLateLoadShapes`, `SetUnloadShapes/GetUnloadShapes` | Delayed geometry loading and unloading exist. Their active setting for a particular TC-open workflow was not read. |
| Load a selected set | `IDMScenegraph.LoadParts/GetLoadedParts`; automation `LoadedNodes/NumLoadedNodes`; node `IsLoaded` | Loaded state is distinct from visibility. Internal interfaces are not necessarily directly callable through the app's current IDispatch wrapper. |
| Batch visibility | `IVisDisp3DView.SetNodesVisible/SetNodesInVisible/CreateNodeList`; `IVisibilityManager.SetNodeSetVisible/SetNodeSetInvisible` | Supports the already deployed one-list, one-dispatch visibility implementation. |
| FMS streams versus whole-file retrieval | `IFMSService.OpenStream` and `GetFile`; `IFMSStream.Init/GetMoniker` | Native installation has a streaming route in addition to whole-file retrieval. This is not proof every native open uses streaming. |
| Read-ahead and segment cache | FMS diagnostic strings `READ AHEAD`, `RENDER`, `RENDER WAIT`, `FCC_ScheduleRange`, memory-mapped cache and pipe fallback | Strong implementation evidence of segment-oriented reads and prefetch. Per-session hit rates and actual read ranges were not traced. |

`IDirectModelView.SetIdleLoad/GetIdleLoad` also exists, but its help metadata explicitly marks it **OBSOLETE**. Do not use it as a proposed supported integration API. `IVisDispPLMXMLLoadOptions` exposes units and default product-view application; it does not expose a simple automation late-load switch.

The current native process loaded `FMSService.dll`, `WebStream.dll` and `PLMXMLLoader.dll`. The shell's `FMS_HOME` resolves to `D:/Siemens/Teamcenter14/tccs`. Its `fcc.xml` documents whole-file cache, segment cache, maximum sizes, age and purge options, but these sample properties are commented out: their sample numbers are not verified effective settings. Do not edit them to mask application latency. Temporary local cache is compatible with this design; cache eviction must lead to reacquisition, not lost structure/position identity.

Local help redirects to the Siemens documentation portal rather than supplying a full offline SDK manual. The installed type libraries establish available interfaces, not a supported end-to-end recipe for attaching historical cached structure to FMS streams.

## AI00's measured extra work

The real rear-suspension checkbox took 623.644 seconds after the journal append fix. It needed 55 files, of which 38 newly fetched files totaled about 153 MiB. New-file read plus local hash took 176.332 seconds; upload took 210.864 seconds. Other time includes startup/preflight, plan orchestration, package preparation, cloud materialization, native insertion, binding and tree readback. The remaining time has not all been separately attributed.

Code-confirmed sequence:

1. Frontend `cache_snapshot_viewer.js` awaits all acquisition batches before requesting package open; each batch contains up to eight files.
2. `teamcenter_readonly_worker.js` retrieves one complete file through `FileManagementUtility.getFiles([file])`. It constructs and terminates a file-management utility per file despite retaining the worker connection.
3. `PlanExecutionWorker` waits for each `UploadModelAsync` receipt, then deletes that temporary local JT.
4. The open contract names cloud `artifact_ref` dependencies. `AppArtifactMaterializer` requests grants and obtains dependencies in parallel (limit four), reusing its own verified shared cache when available.
5. The just-fetched FMS files are not seeded into that shared cache. A first open therefore uploads freshly obtained local bytes and can then download those same bytes again.

The cloud round trip is imposed by AI00's current materialization contract. It is not an inherent requirement of PLMXML. A package-phase elapsed time must not be reported as XML generation CPU time without finer instrumentation.

## Direction for the performance fix

Keep the selected historical cache batch as the authoritative occurrence tree, instance identities and assembly transforms. Resolve that batch's file identities through FMS into a disposable, verified local cache. Build or retrieve the compact assembly description independently of whole-file cloud archival, and let opening consume those local files. Cloud archival, if needed, should have separate completion/progress and should not gate local viewing.

A local-file route needs an explicit contract for verified file receipts, workspace/snapshot binding, allowed local paths, hashes, expiry and cache-miss reacquisition. Do not simply skip artifact validation or silently open the newest TC structure. Seed/reuse the existing content cache as an incremental optimization, but that alone leaves the measured 211-second upload prerequisite intact.

Explore supported native FMS streaming after establishing this shorter route. It requires confirmation of ticket/moniker integration and historical file revision semantics; the presence of an internal COM interface is not sufficient to ship a call against it. Avoid relying on obsolete idle-load interfaces.

Validate on an assembly not previously opened by this app, without clearing the user's shared FCC cache. Record whether FCC and the app cache hit; distinguish first-to-app from fully network-cold. Measure structure preparation, FMS reads, cloud upload (if any), local materialization, native insertion, identity mapping and tree readback separately. Preserve one environment document/root, exact selected scope and transforms, and verify batch hide/show afterward.

## Evidence

Workspace `.runtime/siemens-loading-typelibs.json`, `siemens-loading-focused.json` and `siemens-load-options.json` contain extracted member names and help metadata. Inspection scripts use `GetTypeAttr().cFuncs` for function enumeration. `siemens-loading-evidence.json` provides initial filtered diagnostic strings; its initial automation enumeration was incomplete and is superseded by the corrected type-library files.

Cold-open timings and independent native coordinate/visibility verification are recorded in `2026-09-30-cold-cache-journal-latency.md` and the linked workspace evidence files.
