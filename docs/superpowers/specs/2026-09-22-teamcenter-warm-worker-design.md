# Teamcenter visualization worker reuse

Status: user-approved design, plan and activation (2026-09-22); Debug test host healthy after review fixes, application/TC login pending. No authenticated model-open latency claim.

## Intent and measured baseline

Reduce model-open latency while retaining the approved source → open → current runtime identity → embed/control → runtime association flow. Teamcenter remains source authority; VisMockup remains renderer. No historical identity matching is reintroduced.

The diagnostic W01-89184128 JT is 65,983 bytes and already exists in renderer cache. Observed initial open-to-ready was 31.47s; an instrumented subsequent open was 28.44s: launch 19.23s, native attach including cloud identity read 3.02s, binding 3.13s, workspace refresh 0.98s, local grant setup 2.06s. Stored launch outcomes show 14–15s inside Connector execution. These do not isolate Java, TC, FMS and COM costs yet.

Installed Siemens evidence: TCCS initializes FMSClientCache and configures a 240-minute idle lifetime; FCC has whole-file and segment-cache configuration. FoundationViewer and SingleEmbeddedViewer supply embedded/FMS-ticket interfaces. This establishes available mechanisms, not proof that our current API can use streaming or that a particular phase causes all 14s.

## Selected scope

Reuse an AI00-owned visualization worker and its authenticated TC connection for the current local login generation. Reuse the official FMS utility/cache. No process pool, renderer replacement, public API, new Capability, database migration, external-client credential extraction, or Siemens configuration changes.

Alternative A: only add timing, preserving per-open startup/login; lowest risk but does not remove identified repeated work. Alternative B (selected): one serial worker per local login generation. Alternative C: adopt embedded FMS streaming interfaces; defer because of substantially wider integration/licensing and assembly validation requirements.

The current readonly structure/search worker stays unchanged in this increment. Visualization worker authentication must complete as part of explicit login before reporting readiness; avoid an additional throwaway credential-validation login for this path. Measure login time separately: moving work to login is not free performance improvement.

## Ownership and protocol

- TeamcenterReadOnlyRuntime owns the login generation and invalidates its worker on logout, account change, authentication expiry, disposal or Connector shutdown.
- The existing serialized gate prevents concurrent material requests. Use one child process, not one per model and not a pool.
- Credentials are sent only once over inherited private stdin for that generation, never command arguments, files, logs or renderer IPC. Java clears password references after authentication where SDK callbacks permit; parent retains only the existing credential policy required by other readonly operations. Do not claim Java String zeroization.
- Internal versioned, bounded request/response frames carry request IDs. A response must match both the request ID and worker generation. Existing public launch@1/@2 input/output, signatures and source receipts remain unchanged.
- Each consume request repeats authorized source resolution and FMS access using the live session. A cached filename is never proof of permission, source identity or current revision.
- Retain material_ready → native consumer → material_consumed/material_failed → final result handshake. Report native outcome exactly once. Do not wait for JVM exit after a successful request; JVM exit is a lifecycle event, not a per-open completion condition.
- Clean only that request's secured transient material directory after its result; preserve the existing content-addressed renderer material lifetime. No arbitrary path cleanup.
- Drain stdout/stderr continuously with bounded frames and retained diagnostics, not an ever-growing session buffer. Only whitelisted phase names and numeric timings may be logged; raw SDK stderr is not forwarded.

## Failure and teardown

- Worker exit, protocol corruption or cancellation discards the worker and fences late replies. Never automatically replay the current open/insert or fall back to the old opener.
- If native invocation began, preserve consumer outcome/unknown semantics; a worker failure must not become a no-effect result. Unknown writes remain subject to existing quarantine/recovery policy.
- A dead/expired worker cannot retain a ready session. A later explicit login establishes a new generation; no silent reuse across accounts.
- Logout/account switch must revoke readiness immediately and coordinate cancellation/cleanup without waiting indefinitely behind an in-flight gate. Teardown attempts logout with a bound, then terminates only the owned child if necessary. Parent shutdown/EOF also releases the child/session.
- No lifetime-wide in-memory idempotency ledger is added: existing plan/journal authority remains responsible for execution deduplication.

## Timing and acceptance

Finish pending diagnostic TDD changes before deployment; the existing parser stub/new failing tests are not a runnable feature.

Record separate durations for process startup, login, source load/launch-info, dataset resolution, FMS initialization/file retrieval, material retention, native consumer, acknowledgement/final result and teardown. Do not include paths, UID values, tickets or credentials in timing output.

Tests must cover two sequential requests using one process/session, explicit logout and account switch, expired session, crash/EOF, malformed/oversized/mismatched frames, cancellation before and after native dispatch, late response fencing, material isolation, bounded diagnostics, and no replay. Test actual protocol behavior, not source-string presence alone. Preserve launch v1/v2 and local-control regressions.

Runtime validation uses only the authorized diagnostic bolt. Measure separately: login-to-ready, first open after login, repeated opens, native attach, grant setup, and total click-to-ready. Verify PID reuse and continued low-latency local control/audit. No whole-vehicle test or unrelated document close. A lower second-open number alone does not prove true first-open improvement; report all phases and uncertainties.

## Governance and rollout

Classification: internal runtime implementation/lifecycle change under Simulation/Connector ownership. Public Capability effects, permissions, source verification and receipt contracts remain unchanged; internal worker protocol compatibility is versioned. Re-evaluate runtime artifact bindings and regression evidence before test activation. This is not an approval or signed release.

Formal machine_passed, human_approved and runtime_verified are unverified for this change; AI remains advisory. Test in an isolated staged Connector package with the current verified package retained for rollback. Do not alter the running installation before tests and user design/implementation-plan review.
