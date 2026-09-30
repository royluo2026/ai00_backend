# Cache Visualization integration plan

Goal: inspect the other implementation, integrate compatible code, and jointly test it without regressing one document per environment or frozen-cache visibility.

Architecture: reuse the existing Visualization request/operation boundary for explicit online sources. Merge exact cache-node identity resolution and closed request contracts. Keep the fixed-snapshot checkbox consumer unchanged until an online environment binding can prove occurrence identity, placement and retained visibility.

Execution: inline, as requested by the user; preserve both dirty worktrees and do not message other threads.

1. Import source tests, add request-version provenance assertions, observe failures before implementation.
2. Port only the cache-node repository method, request contracts, request registration, governance metadata and frontend request helper. Fix provenance/version issues found during review.
3. Test malformed stored identities, permissions, old/new request versions, one-step plans and absence of JT/OIS acquisition in the new request.
4. Run combined existing frozen-cache, native environment, online helper and binding suites; build the frontend and record exact evidence and limitations.

Review findings before editing:

- The submitted frontend handles online documents whose tree source is `teamcenter_cloud_cache`; it does not implement the explicit `teamcenter_cache_snapshot` document consumer.
- New-document launch deliberately creates a native document per selected node; it does not preserve the user's one-environment document invariant.
- Native viewport attachment alone does not create the environment source association/grant needed by checkbox interactions.
- Insert targets the active document, with no new environment-scoped receipt or occurrence mapping.
- A cached ItemRevision is an identity reference. Reopening it with TC revision rule/date is not proof of frozen occurrence structure/placements or byte identity.
- The submitted request @3/@2 handlers produce plans labeled @2/@1. Reusing a local operation must not downgrade capability provenance.

Ruling: integrate the compatible backend and request-helper changes; do not enable the node-menu replacement or replace the frozen checkbox path. These require additional environment binding and frozen/online semantic design, not a blind merge. No production TC/FCC deletion or new live document is needed to validate a consumer that remains unenabled.

Governance: implementation/advisory evidence only; no formal Catalog approval or publication is asserted. The literal worktree basenames fall outside the skill's scope gate; domain metadata and tests are nevertheless preserved during porting.

## Execution and verification

Compatible request contracts, cache-node resolver, request helper, registrations, and provider metadata have been integrated into the existing integration worktrees. Cache launch @3 and insert @2 retain those exact versions in their plans while reusing local launch @2 / insert @1. Opened-source evidence accepts launch request versions 2 and 3, rejects unknown versions, and keeps all identity/signature checks. Desktop consumer references remain version 1. Malformed stored structure fails with a stable error; project permission is checked before cache-state or node lookup.

- Backend combined cache/open/binding/Visualization suites: 140 passed (33 existing SQLite datetime deprecation warnings).
- Frontend cache/online helper/native view/visibility/interaction/document-manager suites: 117 passed.
- Connector placement/environment/open/mapping suites: 74 passed.
- Production frontend build passed. The sandbox's initial esbuild EPERM was resolved by running the same local build with the required process permissions.
- Full official Catalog generation remains blocked by existing `provider_artifact_mismatch: project_management`. No unrelated provider hashes or formal release files were rewritten. The unpublished local test Catalog uses the changed simulation provider's verified artifact hash and has been loaded by the restarted test backend.

The user subsequently reported lost fastener coordinates. Native evidence confirmed geometry-root transforms were ignored. The adapter now retains identity assembly parents, explicitly loads inserted hierarchies, restores prior visibility, and checks all world matrices before reporting success. See `docs/verification/2026-09-29-one-environment-document.md` for the correction and runtime evidence.

No new independent-document frontend menu was enabled. No cold-FCC streaming claim is made for that unenabled consumer. These changes are integrated locally, not published as a release or merged wholesale into a clean main branch: both destination worktrees contain existing work that must be preserved.
