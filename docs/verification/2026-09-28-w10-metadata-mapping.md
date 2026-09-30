# W10 node mapping correction — 2026-09-28

Implementation fix in the VisMockup adapter; no wire contract, Capability definition, database, or migration change. Working-tree base: `8d3c459a3`. Not committed or released.

## Cause and change

The installed `D:/Siemens/Visualization14/Program/VisAutomation.tlb` declares `IVisDispMetaDataList.GetPropertyByName` (DISPID 3) as a void method taking a BSTR name and an **out VARIANT pointer**. The C# adapter passed only the name, expected a return value, and swallowed the resulting exception as empty metadata. Consequently, occurrence resolution treated real product nodes as identityless wrappers and traversed unrelated branches until the existing 511-child budget was exhausted. Historical W10 diagnostics recorded parent `12095`, 148 children, and only 7 budget remaining.

`DynamicNode.ReadOccurrenceMetadata` now supplies `out object property` and converts that output. `ModelId` uses the same corrected reader. The node budget, ambiguity refusal, CAD identity recheck, session fencing and authorization checks are unchanged. No name/order-based matching was added.

## Automated evidence

- Added `VisMockupMetadataTests.Native_occurrence_metadata_uses_the_required_output_parameter`, exercising the actual DynamicNode with a metadata object exposing the native two-argument signature. Before the change it failed: expected `tc-occurrence`, actual empty string.
- After correction, metadata plus ViewerNodeRegistry tests: **36 passed, 0 failed**.
- Broader Viewer/VisMockup suite in normal Windows permissions: **234 passed, 1 failed** (235 total). The failure is the existing `ColdDocumentPreparationHasItsOwnBudgetWithoutRelaxingNodeMapping` assertion expecting 5 seconds; the committed HEAD implementation already uses 25 seconds for `resolve_nodes`. Neither that test nor the timeout was changed here. Do not report the broader suite as fully passing.
- The initial sandbox run had five additional access-denied failures involving pipes/key files; those passed when rerun outside the sandbox.
- Read-only code review found no actionable issue in the implementation and regression test. `git diff --check` passed.

Commands (from the backend worktree):

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore --filter 'FullyQualifiedName~VisMockupMetadataTests|FullyQualifiedName~ViewerNodeRegistryTests' --verbosity minimal -m:1 -nr:false -p:UseSharedCompilation=false
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-build --no-restore --filter 'FullyQualifiedName~Viewer|FullyQualifiedName~VisMockup' --verbosity quiet -m:1 -nr:false
```

## Controlled Test App observations

Real UI controller → Electron Main → Connector pipe → VisMockup, using W10 environment `226175746748616704`. The existing VisMockup PID 35012 was preserved while AI00 Test was gracefully restarted with the rebuilt Connector. No full-tree scan/export or load-all-geometry command was used.

- W10-HTM, occurrence path depth 1: highlight and unhighlight both successful; unhighlight 171 ms. First highlight total was 57,776 ms, including open confirmation/reconnection, and is **not** a mapping-only latency measurement.
- Two different instances of `W01-89184128/00;1`, path depth 3: each completed highlight and unhighlight successfully. First-instance highlight 1,936 ms; second-instance highlight 655 ms. These are controller call timings, not screen-paint measurements.
- First bolt instance: show 236 ms, hide 218 ms, show 201 ms; all returned the expected confirmed visibility. The sample was left shown, with both test highlights cleared.
- Route ended at `本地交互 · 就绪`; none of these actions returned `viewer_mapping_budget_exceeded`.

Raw controlled-run response files are retained at `E:/Projects/ai00_v3/.runtime/w10-metadata-htm-result.json` and `E:/Projects/ai00_v3/.runtime/w10-metadata-deep-result.json`. Connector diagnostics: `.runtime/w10-metadata-fix.err.log`.

The corrected adapter DLL is loaded by the running Test App and copied to the default frontend `build/connector-debug` directory. SHA-256 of both copies: `ebc21299a35dee7978b74879c83b2e5cc26dbbea32fb6ce2cca07f5f2f4c6015`. Previous default DLL retained in `.runtime/w10-metadata-original`.

Scope of the conclusion: the reported W10 mapping failure is corrected and the listed real assembly/part operations passed. This is not exhaustive verification of every W10 node, nor a claim of an entirely passing suite or formal governance release approval. The actual Git root basename `orchestration-merge-backend-20260905` is outside the AI00 governance skill's scope gate; no formal `machine_passed`, `human_approved`, or `runtime_verified` release state was asserted or changed.

## User follow-up: later visibility failure

At 10:12 Asia/Shanghai the user reported errors after several further operations. Read-only inspection of the W10 Test audit table found:

- Sequence 10, received 10:11:49.047633: visibility change completed, COM 23.1989 ms.
- Sequence 11, received 10:11:53.852661: visibility change completed, COM 38.0027 ms.
- Sequence 12, received 10:12:08.278457: visibility change returned `outcome_unknown` / `invocation_outcome_unknown`, COM 5012.1775 ms, total 5019.0227 ms. Request `0974e8fb-0847-4d70-bf7d-6612e3b6d227`.

The current page showed `结果未知 · 控制已暂停`. This failure reached execution with a resolved node reference; it is not another observed `viewer_mapping_budget_exceeded`. The duration aligns with `ViewerInteractionExecutor`'s default five-second `pending.WaitAsync` limit. Timeout and other execution exceptions are currently collapsed into the same code, so the audit alone does not conclusively distinguish timeout from a native error occurring at that boundary, identify show versus hide, or establish whether geometry loading caused the delay. No operation was replayed and quarantine was not cleared during diagnosis.

Raw sanitized audit projection: `E:/Projects/ai00_v3/.runtime/w10-latest-audit-20260928.jsonl`. This later execution failure remains unresolved; the earlier sample success must not be interpreted as complete W10 control acceptance.

## 2026-09-28 visibility / diagnostics follow-up

The 10:12 failure was a distinct write-path timeout: the audit recorded approximately 5012 ms in native execution and an immutable `outcome_unknown`. This did not establish that native work stopped. The previous default was five seconds per target; a timeout permanently quarantined this host.

Implemented:
- A 60-second budget for the entire admitted execute request (not 60 seconds multiplied by target count). Main pipe waits 75 seconds; direct frame execute waits 90 seconds; executeIntent retains its 120-second mapping + execution envelope. A real deadline, cancellation, native error or journal failure still quarantines the runtime. No automatic write replay or unknown-outcome erasure.
- Native visibility readback still gates success. Each successful synthetic-root child updates the stored tree immediately; an uncertain target becomes unknown. All retained rows derive from the shared stored tree, including lazy child arrivals; incomplete pages cannot prove whole-branch visibility. One forest/index is shared per synchronization pass.
- User-approved symbols: all visible = blue check; confirmed partial visibility = grey check; unknown = question mark; hidden = empty box. Unknown is neither checked nor indeterminate. Accessible labels remain available without visible explanatory text.
- Persistent structured diagnostics: Main records intent, scope, mapping, request ID, action, target and elapsed/COM/journal time. Connector records admission, mapping budget, native start/settlement, visibility readback and exception type/HRESULT/failed stage. Grant/session credentials and raw COM payloads are not logged. Connector diagnostics are independent of the compacted upload journal and rotate at 5 MiB, retaining three previous files; Main uses its existing rotation. Logging failures do not change operation results.

Validation:
- 239 Viewer/VisMockup .NET tests passed, including a 5.2-second native operation, timeout + late completion quarantine, diagnostic sink failure and file rotation. Corrected the pre-existing preparation test's stale resolve_nodes expectation from 5 seconds to the already-committed 25-second mapping budget.
- 146 focused frontend tests passed, including unknown symbols, partial batch effects, lazy ancestor synchronization, incomplete child pages and timing/credential exclusion.
- Actual W10 Test session: two different depth-3 W01-89184128 instances each hidden and shown via their real tree checkboxes (four operations, 373–699 ms each). Every native visibility_readback matched expected, both leaf flags matched, parents changed to grey checks after hiding and blue checks after showing. Unknown root retained `checked=false`, `indeterminate=false`, and computed question-mark content. Final tested parts were shown. Evidence: `E:/Projects/ai00_v3/.runtime/w10-visibility-ui-result.json`.
- The broader desktop boundary scanner still reports 10 findings outside this fix in web/core/business_facade.js, web/core/web_compat.js, web/main.js and web/share/issues.html. The modified viewer bridge has its reviewed source hash and is allowlisted; the complete module is not declared release-ready on this evidence.

Runtime diagnostics:
- `C:/Users/luoyi8/AppData/Roaming/AI00-Test/logs/main.log` (`[SimulationViewer]` records)
- `C:/Users/luoyi8/AppData/Local/AI00/App/Connector-Test/logs/viewer-interaction.jsonl`

App PID at verification: 46884; Connector PID: 44636. Running test host uses build/connector-w10-visibility-fix. The same published files were copied into default build/connector-debug and its development host digest refreshed for the next normal Test launch. Existing VisMockup document was retained.
