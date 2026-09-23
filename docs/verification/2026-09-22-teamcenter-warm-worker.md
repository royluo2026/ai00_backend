# Teamcenter warm-worker verification

Status: Debug test package activated and host healthy; application/TC login pending. Independent review's two Important findings corrected and regression-tested. No real login/open latency improvement is claimed.

## Change classification

Internal implementation/lifecycle change within Simulation/Connector. TC remains source authority; VisMockup remains renderer. Reuses one owned Java process, TC login and lazy FMS utility per login generation. No new public capability, schema migration, frontend change, historical identity matching or automatic replay.

## Authoritative context inspected

- `docs/contracts/teamcenter.visualization.launch@1.json`, `teamcenter.visualization.launch@2.json`: unchanged closed source selectors and receipts.
- `VisMockupAdapter.OpenTeamcenterVisualizationCoreAsync`: still captures same-open process/document evidence in the native consumer.
- `TeamcenterReadOnlyRuntime`, worker script and material helpers: existing runtime owner and source authority.
- Existing lifecycle, local-control, worker contract and source-resolution regression tests.
- Siemens Java 11/Nashorn and installed SOA/RAC classpath loaded the revised script with EOF input (no credentials, TC login or model open). Exit 0; only upstream jjs future-removal warning.

## Reuse, ownership and boundaries

Reuse existing source selector hashing, material validation, renderer retention and public launch result types. New private V2 worker envelope scopes replies to login generation and request. Source and FMS authorization are performed on each consume, regardless of retained JT bytes.

No current production caller uses the older `ITeamcenterWorker.LaunchAsync`; this increment changes the active `ConsumeVisualizationAsync` path only. The obsolete legacy opener is not newly enabled or represented as supported.

Only backend runtime implementation/test files changed. Frontend and production catalog not modified; no DB schema changes. Provider artifact hashes necessarily change, so prior signed release evidence cannot be assumed valid. Runtime Registry/Snapshot/exact-hash release bindings have not been renewed here.

## Verification evidence

- `node --test local-runtime/tests/*.test.cjs`: 20 passed, 0 failed.
- `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --no-restore --verbosity quiet -p:UseSharedCompilation=false -m:1`: final 439 passed, 0 failed, 0 skipped (`TestResults/warm-worker-final.trx`).
- Real child-pipe tests cover two consumes/one process, no per-request exit wait, malformed/duplicate/oversized/wrong-ID/wrong-generation frames, unsolicited reply cleanup, bounded noise/timing retention, crash/cancellation around consumer, generation-scoped teardown and synchronization-context independence.
- Runtime tests cover login without throwaway validation, dead-worker readiness, logout/account switch while consumer ignores cancellation, and disposal with queued operations. Java SDK fakes exercise FMS reuse plus repeat source resolution; these are simulated SDK evidence, not actual TC access.
- RED/GREEN observed for missing timing, session functions, process class, generation lifecycle, malformed parser, initial credential callback, idle protocol cleanup and UTF-8 BOM framing.
- One obsolete V1 source-literal-count assertion was removed; legacy reader behavior retained and active V2 replaced by real child-pipe tests.
- `dotnet publish .../Ai00.Connector.AppHost.csproj -c Release --no-restore -p:UseSharedCompilation=false -m:1 -o E:/Projects/ai00_v3/.runtime/connector-warm-worker-20260922`: exit 0.
- `git diff --check`: exit 0 (Windows line-ending warnings only).
- Base code revision: `8d3270084cb786815523acbbcc8c2b9f0e4cccf1` plus uncommitted warm-worker changes. No new commit or push.
- Snapshot GID/test-run GID/result hash for formal release: unverified. Detailed task logs retained in `.superpowers/sdd/2026-09-22-teamcenter-warm-worker/`.

## Staging and rollback

Active package: `E:/Projects/ai00_v3/.runtime/connector-warm-worker-debug-20260922`.

Final Debug SHA-256:

- AI00.ConnectorHost.dll: `8A32401CDAD89454531EC903B0FEABDF2590F6ED62B1D66FD7F49CFC0DF58C2F`
- Ai00.Connector.Adapters.VisMockup.dll: `27290BEC28DA3C6EF0A4A0E7CFC334EB30FE044EC4B485BD602863D7F86080A4`
- teamcenter_visualization_launch.js: `DB0734074531015805E852398979775776197DB506589A49A33A8F791B3F9319`

User authorized activation. Manifest points to the Debug package. Connector PID 292116, parent Electron PID 152952, exact package path confirmed; UI connector ready/healthy, TC logged_out, native detached. PIDs are observations, not permanent targets. No VisMockup process was stopped or model opened.

Initial Release activation exited 1: AppHostOptions accepts --development local only in DEBUG. Rebuilt Debug without changing that security gate. Release package remains at `.runtime/connector-warm-worker-20260922` but is not running. Prior working `.runtime/connector-local-viewer-20260922` remains intact. Rollback manifest: `E:/Projects/ai00_v3/.runtime/warm-worker-predeploy-20260922/connector-host.dev.manifest.json`. Activation used the existing Electron supervisor. Final Debug apphost EXE hash: `CAF54B77E00CDEDE1D80654A92B75CFEBAA953653357806FB32728C0B9628507`.

## Governance status

- machine_passed: unverified (local test pass is not a persisted governance gate).
- human_approved: unverified (chat approval of implementation is not exact-hash platform approval).
- runtime_verified: unverified (diagnostic opens/control succeeded, but full acceptance and persisted governance gate remain incomplete).
- advisory: true.

## Remaining acceptance

Authenticated measurements on 2026-09-22 (diagnostic workspace `227728039260360704`, document `227728051386093569`, W01-89184128):

| Stage | Measurement A | Measurement B |
| --- | ---: | ---: |
| UI open to local interaction ready | 16,303 ms | 19,187 ms |
| Launch request through receipt | 7,761 ms | 9,906 ms |
| Connector launch step (stored signed outcome timestamps) | 2,831 ms | 3,650 ms |
| Attach including identity request | 2,105 ms | 2,647 ms |
| Runtime association bind | 3,278 ms | 3,338 ms |
| Workspace refresh | 996 ms | 1,203 ms |
| Local interaction grant/open | 2,126 ms | 2,064 ms |

Both calls completed with local interaction ready. Four diagnostic local actions succeeded: hide200.2ms/show47.5ms/highlight47.4ms/unhighlight30.8ms. These are callback timings, not pixel timing. Audit snapshot427/427 events had grant proof (cumulative; not all attributable to this run).

Important limitations: retained JT cache was not removed; login total was not captured. User confirmed logging in/reconnecting between A and B, consistent with Java PID176444 then296588; this is NOT a same-session PID-reuse comparison. Earlier server records contain other opens, so A is the first instrumented open of this turn, not proven cold-renderer first open. Prior 28.44–31.47s UI /14–15s Connector timings are historical comparison, not a controlled benchmark.

User changed workspace during validation; scope guards refused subsequent tree/control actions. No full-vehicle operation or unrelated document close was performed by these diagnostics. Additional open attempt waited at login and has no valid timing result.

Current blocker: Connector disappeared. Restarting only AI00 Electron (PID305096 to298260) preserved existing VisView_NG PID164164 but did not restore Connector. Captured startup logs show RuntimeSessionWorker registration throws runtime_plans_unresolved, unhandled BackgroundService exception stops host; supervisor reaches restart_limit. Read-only database check found plan `vismockup-command-fde3ce4ec9f856c97fb7bb7e2a33e092be435d04ea7ee24e7d5bc79c6113bcb7`, created05:59:38Z, launch@2, leased with no outcome. Its model scope is not established. No database status rewrite, journal deletion, execution replay or manual resolution has been done. Recovery disposition needs verification/authorization; do not claim activation currently healthy.

Remaining: restore unresolved-plan recovery safely, capture same-session PID reuse and first-open/login phase timing, verify actual tree clicks. No full-vehicle test or unrelated document close.

## Independent review and rulings

- Important: pre-dispatch dead worker could quarantine a write. Fixed at visualization admission; signed write-plan test proves failed_without_effect, zero consumer calls and no quarantine. Native-started unknown semantics remain covered.
- Important: externally registered runtime was not disposed by host. Production DI factory transfers ownership; registration teardown test proves disposal. Real-child test terminates an owned process that ignores logout within the bound.
- No Critical or Minor findings. One TDD fix pass; no repeated review requested.
- Ruling: use existing Java.type timing seam; wrong seam would hide SDK timing failures.
- Ruling: replace obsolete V1 literal count with actual V2 transport tests; legacy reader behavior retained.
- Ruling: leave uncalled legacy LaunchAsync unchanged; not an alternate supported opener.
- Ruling: review uncommitted diff plus explicit new-file list because no new commit requested; prevents untracked files being silently missed.
- Ruling: transfer DI ownership rather than only using declaration, allowing direct production registration test; recheck if registration is ever no longer resolved.
- Ruling: Debug required for local development supervisor; do not weaken Release gate. Cost was a second App restart.
- Declined-to-judge live authorization/cache/render/performance and rollout acceptance require actual runtime evidence, not static inference.
