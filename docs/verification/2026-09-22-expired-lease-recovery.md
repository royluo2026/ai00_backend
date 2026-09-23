# Expired lease recovery repair

Implementation fix for recovery.search/recovery.resolve and AppHost registration. No public schema or database migration, no execution replay. Existing owner/tenant/generation/fingerprint/confirmation/audit fences remain.

Cause: expired leased/executing writes block runtime registration but were excluded from manual recovery search. Registration raised an unhandled error and stopped the host. A later live run also exposed an unhandled registration HTTP connection reset.

Search now includes expired leases in its single read snapshot, projecting outcome_unknown without altering persisted state. Such rows permit abandonment only. Resolve rechecks lease expiry under existing device/plan locks; it archives only the reviewed task, preserving any outcome. Registration waits five seconds for unresolved work or transient transport errors; authentication errors remain fatal. No automatic model re-execution.

Evidence:

- SQL tests RED on both leased/executing missing rows; separate RED on output status contract.
- SQL suite 150 passed,149 skipped (native MySQL URL absent). Final boundary additions:2 passed,2 skipped; future leases hidden, other actors excluded, unexpired resolution rejected.
- Connector RED on unresolved registration, then RED on HTTP/transient errors. Final full .NET suite443 passed,0 failed.
- Project-wide pytest stops during collection at test_base_self_annotation_routes.py: provider_artifact_mismatch:simulation. Not a full-suite pass.
- Local development backend needed an updated exact artifact manifest. `.runtime/recovery-local-domains.json` pins current simulation bytes; local runner passes it through the normal hash-checking loader and existing unpublished local Catalog. Checked-in official manifest/release evidence unchanged. This does not constitute release approval.
- Live recovery page now lists exactly plan vismockup-command-fde3ce4ec9f856c97fb7bb7e2a33e092be435d04ea7ee24e7d5bc79c6113bcb7, abandonment only. No disposition submitted.
- Final package `.runtime/connector-recovery-final-20260922`; Host DLL SHA256 A5EFF37373E41313C7B0DF128EE58C0BC80C0A15830D0D251F61B234D6D37D29. Prior packages preserved. Independent VisView_NG PID164164 retained throughout app restarts.

Remaining: human disposition and subsequent registration/TC login verification. Performance acceptance remains unfinished. No commit/push. Formal machine_passed/human_approved/runtime_verified gates unverified; advisory evidence only.

## Follow-up after user login

User archived blocked plan at06:36:46Z (database cancelled/no fabricated outcome). Same Connector PID274456, created14:23:07 local, remained alive through recovery and two successful diagnostic launches. TC ready; Java PID48100 created14:37:09 unchanged across both opens. Electron public diagnostic still retains recovery_required after recovery despite successful launches; stale diagnostic remains a UI/status follow-up, not an unresolved server task.

Two opens in one login generation:17,414.7ms then16,367.5ms, both local interaction ready. Cached JT retained and VisMockup already running; not cold-renderer/cold-disk measurements. First Connector launch step2,485ms. First launch request7,398ms, attach2,320ms, association3,593ms, refresh1,492ms, local grant2,584ms. Second request6,301ms, attach3,041ms, association3,136ms, refresh1,517ms, local grant2,358ms.

Sanitized worker logs: one process_start12.19ms and login1043.08ms (SDK login only, not full UI login latency); first source_load547.94/launch_info92.04/dataset_resolve598.88/fms_init21.70/file_load57.48/fms_get_files59.91/material_retain8.54/native_consumer368.92/ack_final63.60ms. Second source_load78.16/launch_info62.14/dataset_resolve134.39/file_load39.58/fms_get_files44.24/material_retain4.26/native_consumer1064.55/ack_final4.40ms. No second login or fms_init; live reuse verified.

Actual tree checkbox callbacks199.7/60.9/74.4ms; hide41.1/show48.1/highlight47.0/unhighlight45.7ms all succeeded. Left bolt visible/unhighlighted. Audit rose427→434, all434 have grant proof; seven new events match three clicks plus four actions. Callback timings are not pixel-latency measurement. No full-vehicle operations performed. Main remaining performance cost is orchestration/association/grant, not per-open Java login.
