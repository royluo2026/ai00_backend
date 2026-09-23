# Viewer short-path live follow-up — not complete

This supersedes the deployment and native-window status in the earlier short-path report; it is not release approval.

## Deployed local test artifacts

- Connector: `.runtime/connector-shortpath-window-20260922`, PID 240220 at deployment; Electron PID 290928, backend PID 317680.
- Native module SHA256: DD7FA3782D1401193C175AD28FFF9B430732D4B19D58F1599D9F826444D0B94C.
- Rollback artifacts: root `.runtime/shortpath-window-rollback-20260922` (including backend-dist backup).
- Local unpublished Catalog includes experimental bind@3. Official release evidence remains unchanged.
- User reauthenticated; final read reports Teamcenter ready. No further Connector restart occurred.

## Verified changes

- Captured document resolves its own ViewByHandle; title challenge cannot target an independently captured application view. Native attach pins exact HWND and OS marker and checks both before showing.
- Connector suite: 451 passed. Main/controller: 31 passed. Compiled isolated Win32 native contract harness passed. Independent review found the narrowed document/view ownership issue resolved.
- Isolated real Siemens probe attached the exact diagnostic document window. This does NOT establish compatibility with the existing multi-document process; sandbox child-process errors also prevent treating it as a clean whole-app test.
- Current desktop actually serves its iframe from localhost:5173. `?v=` cached old bootstrap scripts despite source changes; `_openLocalViewerFromLaunch` was missing. Changed viewer_interaction and live_document_bootstrap to new `?rev=` values; runtime now exposes both openFromLaunch entry points. Two related frontend suites: 19 passed.
- Backend port8080 also had stale dist assets (viewer_interaction.js returned404). Rebuilt test-governance frontend, backed up backend dist, and copied generated assets. Served script bytes verified equal to source before the final cache-version-only rebuild/sync.

## Real diagnostic bolt results and remaining blocker

- First launch request: 7790.6ms; binding failed because old cached bootstrap lacked the new entry point. Source load571.96ms, dataset resolve638.28ms, native consumer154.99ms.
- Page development hot reload discarded in-memory pending state. Retrying the persisted signed launch receipt after its freshness window failed closed with launch_evidence_unavailable; no verification checks bypassed.
- Subsequent explicit diagnostic launch: 5524.8ms; total failure12183ms, viewer_mapping_unavailable. Source load78.90ms, dataset resolve130.70ms, native consumer69.05ms. This is NOT successful open-to-visible latency.
- Production adapter diagnostic on existing process164164 reveals inner error vismockup_document_window_unavailable, NativeDocumentWindow.cs title-challenge match count.
- Direct COM experiment scoped to the active cached diagnostic bolt: ViewByHandle Title setter returned without changing Title. Readback remained original filename at0/100/400/1400ms; no challenged HWND found. Finally restored the original title. Unlike the isolated new process, the current multi-document process does not support this assumed title mutation behavior.
- Therefore exact-window association remains unresolved in the real app. No evidence yet of successful complete open, embedded render, or control latency for this revision. Do not relax matching to filename/PID guesses or increase generic timeouts and call it fixed.
- Original VisMockup process and other models were not closed; no whole-vehicle launch. Teamcenter remains logged in; native status detached.

Existing full-project gate limitations documented in the earlier report remain; source transport allowlist regression is now fixed and passing.
