# BOP Large-Version Memory Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make 10,000-node BOP versions safe to open, refresh, and switch without 504 or OOMKilled while preserving Craft ownership, the 11-domain boundaries, and Capability-governed access.

**Architecture:** Craft exposes bounded outline, scoped work-package, and entry-detail projections through Capability V2. The shared Gateway enforces each descriptor's frozen resource budget and process memory pressure. The Craft web page loads these projections progressively, cancels stale generations, and maintains a bounded cache. Runtime configuration, diagnostics, deterministic load fixtures, and release gates prove that the configured process and database budgets remain safe.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, OceanBase MySQL mode, pytest, Vanilla JavaScript, Node test runner, npm build pipeline, Capability V2 Catalog/Gateway.

**Spec:** `docs/superpowers/specs/2026-08-18-bop-large-version-memory-safety-design.md`

**Global constraints:**

- Craft owns all BOP SQL, projection semantics, and business errors. Base supplies only generic contracts, admission control, telemetry, and deployment validation.
- Web, plugins, agents, and other domains consume public Capability contracts; they must not query Craft tables, import Craft repositories, or add cross-domain JOINs.
- Do not change the semantics of `craft.bop.execution_structure.get@1` or `craft.bop.work_package.get@1`.
- Do not silently truncate the legacy full-list response. Large versions receive an explicit migration error.
- Preserve all unrelated dirty files, `CODEX-DESKTOP-HANDOFF.md`, `.superpowers/`, and `docs/superpowers/reviews/`. Do not push or merge.
- Use snowflake GIDs for all generated BOP records and delete test data only by the exact generated GIDs.
- Never log business payloads, database URLs, credentials, JWTs, signed image URLs, or entry names.

---

## Task 1: Add frozen execution budgets to Capability contracts

**Files:**

- Modify: `backend/capabilities/models_next.py`
- Modify: `backend/capability_v2/contracts.py`
- Modify: `backend/capability_v2/descriptor_adapter.py`
- Test: `backend/tests/test_capability_v2_contracts.py`

**Interfaces:** `CapabilitySpec.execution_budget` produces the immutable `CapabilityDescriptorV2.execution_budget` consumed by Catalog validation and Gateway admission.

- [ ] Add failing contract tests for valid defaults, invalid byte/page/concurrency limits, frozen descriptors, and adapter preservation. Use a concrete budget:

```python
budget = ExecutionBudget(
    memory_class="medium",
    max_input_bytes=64 * 1024,
    max_output_bytes=1024 * 1024,
    collection_policy="paged",
    max_page_size=200,
    max_parallel_per_consumer=1,
    max_parallel_per_tenant=4,
    overload_policy="reject",
)
```

- [ ] Run `python -m pytest backend/tests/test_capability_v2_contracts.py -q` and confirm the tests fail because the budget model and field do not exist.
- [ ] Add string enums for `memory_class`, `collection_policy`, and `overload_policy`; add `ExecutionBudget` with positive integer validation; add an optional budget to legacy `CapabilitySpec` and a required frozen budget to `CapabilityDescriptorV2`. Give adapter-generated descriptors a conservative bounded default so existing descriptors remain valid.
- [ ] Map every budget field in `adapt_capability_spec()` and add it to descriptor canonical serialization and hashing.
- [ ] Re-run the focused test and confirm it passes.
- [ ] Commit only these files: `git commit -m "feat(capability): add execution budget contracts"`.

## Task 2: Make bounded collection policy a Catalog release gate

**Files:**

- Modify: `backend/capability_v2/catalog.py`
- Modify: `backend/capability_v2/docs/generator.py`
- Modify: `backend/scripts/build_capability_catalog.py`
- Modify: `backend/scripts/generate_capability_docs.py`
- Test: `backend/tests/test_capability_catalog_release.py`
- Test: `backend/tests/test_capability_docs_generation.py`

**Interfaces:** Catalog consumes descriptor schemas and budgets; generated Catalog/docs expose the frozen budget to developers, plugins, and agents.

- [ ] Add failing tests proving a stable descriptor whose output contains an array is rejected unless it has one of: schema `maxItems`, `collection_policy="paged"` with `max_page_size`, or `collection_policy="artifact"`. Also prove a budget change alters the release digest.
- [ ] Run `python -m pytest backend/tests/test_capability_catalog_release.py backend/tests/test_capability_docs_generation.py -q` and observe the missing validation/documentation failures.
- [ ] Implement recursive array discovery across `properties`, `$defs`, `items`, `anyOf`, and `oneOf`; return an error containing descriptor ID, JSON path, and the missing boundary.
- [ ] Render the nine execution-budget fields in generated JSON and Markdown. Keep ordering deterministic.
- [ ] Run the focused tests, then run `python backend/scripts/build_capability_catalog.py --check` and `python backend/scripts/generate_capability_docs.py --check`; the check commands may now report stale generated files but must not report validation defects.
- [ ] Commit the validation and generators: `git commit -m "feat(capability): gate unbounded collection contracts"`.

## Task 3: Add process and cgroup memory-pressure sampling

**Files:**

- Create: `backend/capability_v2/resource_budget.py`
- Test: `backend/tests/test_capability_resource_budget.py`

**Interfaces:** `MemoryPressureSampler.snapshot()` produces RSS, cgroup usage/limit, ratio, and level; `ResourceAdmissionController.acquire()` returns an async lease released in `finally`.

- [ ] Write failing tests with injected file readers for cgroup v2 (`memory.current`, `memory.max`), cgroup v1, unlimited/missing cgroups, and process RSS fallback. Cover exact levels: `<0.60 normal`, `0.60 warning`, `0.75 constrained`, `0.85 reject_large`, `0.90 not_ready`.
- [ ] Write failing async tests proving concurrency is keyed independently by `(tenant, capability)` and `(consumer, capability)`, waiters time out with `capacity_unavailable`, cancellation does not leak permits, and `large` is rejected at 85% with `resource_pressure`.
- [ ] Run `python -m pytest backend/tests/test_capability_resource_budget.py -q` and confirm module import failure.
- [ ] Implement a dependency-injected sampler and controller. Do not create background threads. Resolve cgroup files per sample, treat `max` and non-positive limits as unlimited, and use RSS only for diagnostics when no finite container limit exists.
- [ ] Implement `AdmissionLease` as an async context manager and guarantee both counters decrement exactly once.
- [ ] Re-run the focused test and commit: `git commit -m "feat(runtime): add capability resource admission"`.

## Task 4: Enforce budgets and emit sanitized measurements in the Gateway

**Files:**

- Modify: `backend/capability_v2/gateway.py`
- Create: `backend/capability_v2/metrics.py`
- Test: `backend/tests/test_capability_gateway_pipeline.py`
- Test: `backend/tests/test_capability_gateway_resource_budget.py`

**Interfaces:** Gateway consumes descriptor budgets and admission leases; it produces standard errors `capacity_unavailable`, `resource_pressure`, and `capability_output_limit_exceeded` plus structured aggregate metrics.

- [ ] Add failing tests for UTF-8 canonical input size, per-consumer/tenant rejection, lease release after provider exception/cancellation, output size enforcement before projection leaves the Gateway, and sanitized metrics.
- [ ] Run `python -m pytest backend/tests/test_capability_gateway_pipeline.py backend/tests/test_capability_gateway_resource_budget.py -q` and record the expected failures.
- [ ] In `invoke()`, serialize validated input with compact deterministic JSON, check `max_input_bytes`, acquire before provider dispatch, and release in `finally`. Serialize the validated provider result once, check `max_output_bytes`, and pass the same normalized value to projection.
- [ ] Record capability ID/version/domain, consumer type plus hashed consumer key, elapsed milliseconds, output bytes, before/after RSS, cgroup ratio, in-flight count, cancellation, and error code. Do not emit arguments or result data.
- [ ] Re-run the focused tests and commit: `git commit -m "feat(gateway): enforce capability resource budgets"`.

## Task 5: Build Craft's direct scoped navigation repository

**Files:**

- Create: `plugins/craft/craft_backend/services/bop_navigation.py`
- Create: `backend/db/migrations/domains/craft/0002_bop_navigation_indexes.sql`
- Modify: `backend/capability_v2/official_domains.json`
- Test: `backend/tests/test_craft_bop_navigation_repository.py`

**Interfaces:** `BopNavigationRepository` consumes only the Craft connection factory and produces outline pages, scoped work-package pages, and one-entry details for a fixed `(version_gid, revision)`.

- [ ] Add repository tests using a recording cursor. Assert keyset predicates use `(sort_order > %s OR (sort_order = %s AND gid > %s))`, page queries use `LIMIT page_size + 1`, relation queries receive only current-page GIDs, and no call reaches `ExecutionStructureRepository.load_bop_aggregate()`.
- [ ] Add tests for invalid cursors, scope ownership, stable ordering when sort orders tie, no orphaned scope ancestry, and `revision_conflict` when the revision differs before or after assembly.
- [ ] Run `python -m pytest backend/tests/test_craft_bop_navigation_repository.py -q` and confirm failure.
- [ ] Implement opaque URL-safe base64 JSON cursors containing schema version, sort order, and GID. Reject extra keys and mismatched schema versions.
- [ ] Implement `get_outline_page(version_gid, revision, cursor, page_size)`, `get_work_package_page(version_gid, revision, scope_kind, scope_gid, cursor, page_size)`, and `get_entry_detail(version_gid, revision, entry_gid)`. Select narrow entry columns first; fetch links/references in a second batch only for the returned page.
- [ ] Add only the composite indexes justified by those predicates, including version/node/parent/sort/GID access. Verify the migration is idempotent using the repository's existing OceanBase migration convention rather than MySQL `ENGINE=InnoDB` clauses.
- [ ] Re-run repository tests and commit: `git commit -m "feat(craft): add scoped BOP navigation repository"`.

## Task 6: Publish the three bounded Craft capabilities

**Files:**

- Create: `plugins/craft/craft_backend/capabilities/bop_navigation.py`
- Modify: `plugins/craft/craft_backend/capabilities/contracts.py`
- Modify: `plugins/craft/craft_backend/capabilities/provider.py`
- Modify: `plugins/craft/craft_backend/capabilities/__init__.py`
- Test: `backend/tests/test_craft_capability_contracts.py`
- Test: `backend/tests/test_craft_bop_navigation_capabilities.py`

**Interfaces:** Publish `craft.bop.structure.outline.get@1`, `craft.bop.work_package.get@2`, and `craft.bop.entry.detail.get@1` through the existing Native Capability Provider.

- [ ] Add failing descriptor tests for owner `craft`, read effect, `web/plugin/agent` exposure, `craft-bop-version` resource selectors, closed schemas, integer revision, opaque cursor, and page limits.
- [ ] Add handler tests for error translation (`revision_conflict`, `invalid_cursor`, `scope_not_found`) and output budgets exactly matching the approved spec: 512 KiB/100/1/8, 1 MiB/200/1/4, and 512 KiB/no page/4/16.
- [ ] Run `python -m pytest backend/tests/test_craft_capability_contracts.py backend/tests/test_craft_bop_navigation_capabilities.py -q` and confirm missing registrations.
- [ ] Change schema lookup to a version-aware key such as `(capability_id, major_version)` with a compatibility helper that falls back to existing ID-only schemas. This must allow work-package `@1` and `@2` to coexist without changing `@1`.
- [ ] Register the three handlers and delegate only to `BopNavigationRepository`. Validate `page_size` again in the handler before issuing SQL.
- [ ] Re-run focused tests and commit: `git commit -m "feat(craft): publish bounded BOP navigation capabilities"`.

## Task 7: Protect and deprecate the legacy full entries endpoint

**Files:**

- Modify: `plugins/craft/craft_backend/routers/_bop/entries.py`
- Modify: `plugins/craft/craft_backend/routers/_bop/_helpers.py`
- Test: `backend/tests/test_bop_entries_size_guard.py`

**Interfaces:** `GET /api/bop/versions/{version_gid}/entries` remains compatible for small versions and returns HTTP 409 with code `dataset_too_large_use_paged_capability` before the wide SQL for large versions.

- [ ] Add failing tests proving count `<= AI00_CRAFT_LEGACY_ENTRIES_MAX` executes the existing query, count above the limit never executes `_ENTRY_LIST_SQL`, an unset value uses a conservative default, and invalid configuration fails startup validation.
- [ ] Run `python -m pytest backend/tests/test_bop_entries_size_guard.py -q` and confirm the guard is absent.
- [ ] Add a lightweight `COUNT(*)` preflight scoped by version. Return structured details containing only `entry_count`, configured limit, and the three replacement Capability references.
- [ ] Add a deprecation response header for successful small responses and an aggregate counter for remaining consumers; do not extend proxy or SQL timeouts.
- [ ] Re-run the focused test and commit: `git commit -m "fix(craft): bound legacy BOP entries reads"`.

## Task 8: Implement a generation-safe frontend load coordinator

**Files (frontend repository `E:\Projects\ai00\workmanship-web`):**

- Create: `packages/craft-plugin/web/lineage_view/lineage_load_coordinator.js`
- Create: `packages/craft-plugin/web/lineage_view/lineage_load_coordinator.test.js`
- Modify: `web/tests/run_tests.js`

**Interfaces:** `LineageLoadCoordinator.begin(versionGid)` produces `{generation, signal}`; `runSingleFlight(key, fn)` suppresses duplicate refreshes; `isCurrent(token, revision)` prevents stale rendering.

- [ ] Add Node tests with deferred promises proving a new generation aborts the old controller, stale completion cannot commit, two refresh calls share one promise, rejection clears the single-flight slot, and `dispose()` aborts every request.
- [ ] Run `node packages/craft-plugin/web/lineage_view/lineage_load_coordinator.test.js` and confirm failure.
- [ ] Implement the coordinator as a browser/Node-compatible IIFE export. Generate monotonic integer tokens; do not depend on `crypto.randomUUID` or parent-frame DOM access.
- [ ] Pass `AbortSignal` through the injected fetch callback and treat `AbortError` as cancellation rather than a user-visible load failure.
- [ ] Run the test directly and through `npm test`; commit in the frontend repository: `git commit -m "feat(craft-web): add generation-safe lineage loading"`.

## Task 9: Implement the bounded frontend projection store

**Files (frontend repository):**

- Create: `packages/craft-plugin/web/lineage_view/lineage_projection_store.js`
- Create: `packages/craft-plugin/web/lineage_view/lineage_projection_store.test.js`
- Modify: `web/tests/run_tests.js`

**Interfaces:** Store keys are `(version_gid, revision, scope_kind, scope_gid)`; it produces lightweight rows for the active scope and separately stores at most one selected detail.

- [ ] Add tests for outline replacement, idempotent cursor-page merge, LRU order, maximum 3 scopes, node ceiling, estimated-byte ceiling, detail eviction, version/revision separation, and full teardown.
- [ ] Run the new Node test and confirm module absence.
- [ ] Implement byte estimation with `TextEncoder` when available and UTF-8 fallback in Node. Enforce all limits after every mutation; evict whole least-recently-used scopes, never partial pages.
- [ ] Expose `replaceOutline`, `appendScopePage`, `selectDetail`, `touchScope`, `rowsForActiveScope`, `clearHeavyData`, and `dispose`. Do not merge detail payloads into lightweight rows.
- [ ] Run the direct test and `npm test`; commit: `git commit -m "feat(craft-web): add bounded lineage projection cache"`.

## Task 10: Migrate the lineage page to progressive Capability loading

**Files (frontend repository):**

- Modify: `packages/craft-plugin/web/lineage_view/index.html`
- Modify: `packages/craft-plugin/web/lineage_view/lineage.js`
- Modify: `packages/craft-plugin/web/lineage_view/layout_mode.js`
- Modify: `packages/craft-plugin/web/lineage_view/layout_detail_panel.js`
- Create: `packages/craft-plugin/web/lineage_view/lineage_progressive_loading.test.js`

**Interfaces:** The page invokes the generic Capability endpoint for version, outline, work-package pages, and detail; no large-version path invokes `/api/bop/versions/{gid}/entries`.

- [ ] Add a source-level integration test that loads the scripts in index order with a fake Capability client. Assert first paint requires only version + outline, selecting a line fetches pages of at most 200, selecting an entry fetches one detail, one refresh cancels old work and issues one new chain, and stale responses never call render.
- [ ] Add teardown assertions for `_rows`, `_rowByGid`, `_childMap`, `_depthByGid`, `_statsMap`, canvas nodes, requestAnimationFrame handles, observers, and drag handlers.
- [ ] Run the test and observe failures against the current full-list `_load()`/`_reload()` implementation.
- [ ] Load the coordinator/store scripts before `lineage.js`. Replace the initial and refresh flow with `craft.bop.version.get@1` then outline; retain only compatibility comparison data for explicitly selected extra versions, fetched progressively.
- [ ] Adapt `_buildIndexes()` and layout rendering to the active scope projection. Add `destroyHeavyState()` to the layout module and call it before each generation. Disable refresh/version inputs while the single-flight promise is pending.
- [ ] Fetch `craft.bop.entry.detail.get@1` from the detail panel on selection and discard it on close or scope eviction. Map `revision_conflict`, `resource_pressure`, and `capacity_unavailable` to concise retryable messages.
- [ ] Run the new test, existing `lineage.test.js`, and full `npm test`; commit: `git commit -m "fix(craft-web): load large BOPs progressively"`.

## Task 11: Make process count and readiness obey the memory budget

**Files:**

- Modify: `backend/gunicorn.conf.py`
- Modify: `backend/Dockerfile`
- Modify: `backend/routers/health.py`
- Modify: `backend/main.py`
- Create: `backend/routers/runtime_diagnostics.py`
- Modify: `backend/tests/test_runtime_entrypoints.py`
- Create: `backend/tests/test_runtime_memory_readiness.py`

**Interfaces:** `AI00_WEB_WORKERS` defaults to `1`; `/ready` rejects new traffic at 90%; an existing admin-only diagnostics route exposes aggregate process/cgroup/capability measurements.

- [ ] Add failing tests proving there is no CPU-derived worker formula, invalid/zero worker configuration fails fast, Docker and service entrypoints use the same worker mechanism, and readiness changes only at the defined 90% threshold.
- [ ] Add authorization and redaction tests for diagnostics. Its response may include PID, worker count, RSS, cgroup current/limit/ratio, pressure level, and recent top capability aggregates, but not invocation payloads or secrets.
- [ ] Run `python -m pytest backend/tests/test_runtime_entrypoints.py backend/tests/test_runtime_memory_readiness.py -q` and confirm failures.
- [ ] Read `AI00_WEB_WORKERS` explicitly with default 1. Keep `max_requests` plus jitter as a configurable safety fuse, not the primary solution. Use the same app/worker configuration in container and documented Windows service startup.
- [ ] Keep `/health` cheap. Extend `/ready` with the sampler and mount diagnostics behind the existing administrator permission dependency.
- [ ] Re-run focused tests and commit: `git commit -m "fix(runtime): align workers with memory readiness"`.

## Task 12: Keep domain pools independent while validating their aggregate cost

**Files:**

- Create: `backend/capability_v2/domain_resource_config.py`
- Modify: `backend/db/connection.py`
- Modify: `plugins/agent/agent_backend/data/connection.py`
- Modify: `plugins/craft/craft_backend/data/connection.py`
- Modify: `plugins/device/device_backend/data/connection.py`
- Modify: `plugins/digital_model/digital_model_backend/data/connection.py`
- Modify: `plugins/factory/factory_backend/infrastructure/connection.py`
- Modify: `plugins/integration/integration_backend/data/connection.py`
- Modify: `plugins/knowledge/knowledge_backend/data/connection.py`
- Modify: `plugins/ontology/ontology_backend/infrastructure/connection.py`
- Modify: `plugins/project_management/project_management_backend/data/connection.py`
- Modify: `plugins/simulation/simulation_backend/data/connection.py`
- Create: `backend/scripts/check_runtime_resource_budget.py`
- Create: `backend/tests/test_domain_pool_configuration.py`

**Interfaces:** Each domain consumes its own `AI00_<DOMAIN>_DB_POOL_MIN/MAX`; the deployment checker reads configuration only and reports the aggregate maximum connections per worker.

- [ ] First capture the exact connection modules and their current defaults in the test parameter table. Add failing tests that each domain has a unique environment prefix and unique pool object, and that `sum(pool_max) * AI00_WEB_WORKERS` over the configured deployment ceiling fails validation.
- [ ] Run `python -m pytest backend/tests/test_domain_pool_configuration.py -q` and confirm hard-coded settings fail.
- [ ] Add a shared parser for positive bounded integers, but leave pool construction and credentials in each owning domain module. Do not create a shared database account or shared pool.
- [ ] Implement `check_runtime_resource_budget.py --strict` to print only domain, min/max, workers, and total; redact all URLs and passwords. Add it to the existing deployment-check sequence.
- [ ] Re-run tests and the checker; commit: `git commit -m "feat(runtime): validate independent domain pool budgets"`.

## Task 13: Add deterministic 1k/5k/10k BOP stability acceptance

**Files:**

- Create: `backend/scripts/run_bop_large_version_acceptance.py`
- Create: `backend/tests/fixtures/bop_large_version_factory.py`
- Create: `backend/tests/test_bop_large_version_acceptance.py`
- Modify: `backend/scripts/run_capability_v2_acceptance.py`

**Interfaces:** The harness creates Craft-owned fixtures, invokes public capabilities through Gateway, samples process/container memory, emits one JSON report, and deletes only its exact GIDs.

- [ ] Add failing unit tests for deterministic topology counts, snowflake GID generation, exact-ID cleanup order, report redaction, and pass/fail calculations.
- [ ] Run `python -m pytest backend/tests/test_bop_large_version_acceptance.py -q` and confirm failure.
- [ ] Generate 1,000, 5,000, and 10,000 nodes across root/line/station/process/operation/part/tool shapes with few image references. Use the Craft test database account and tag every row with one run ID.
- [ ] Exercise first open, one refresh, 20 refreshes, rapid version switches, cancellation while loading, 5 concurrent consumers, and a simultaneous non-Craft Capability. Record page sizes, output bytes, latency, error codes, RSS/cgroup samples, and worker restarts.
- [ ] Fail when a full entries request occurs for 10k, any page exceeds its descriptor, any 504/OOM/restart occurs, peak reaches 75% of cgroup limit, the last 10 refresh peaks have a positive linear-growth slope above the configured tolerance, or the non-Craft call error rate increases.
- [ ] Put fixture cleanup in `finally`: archive where required, then delete links, entries, versions, BOP root, and temporary identity records by exact GID; query for zero residue. Print only the report path and aggregate JSON.
- [ ] Run the unit test. When a test database is available, run `python backend/scripts/run_bop_large_version_acceptance.py --sizes 1000 5000 10000 --strict` and retain the report under `.runtime/acceptance/` without committing it.
- [ ] Commit: `git commit -m "test(craft): add large BOP memory acceptance"`.

## Task 14: Regenerate, build, deploy, and verify without touching unrelated work

**Files:**

- Regenerate: Capability Catalog and generated Capability documentation files reported by the two generator scripts
- Build in frontend repository: `E:\Projects\ai00\workmanship-web`
- Synchronize only build-owned files into: `dist/`
- Modify: deployment check manifest if new lineage scripts are not yet covered

**Interfaces:** The frontend source build produces deployment assets; the Capability V2 service serves the new assets and Catalog on its configured LAN address without changing other services.

- [ ] In the backend worktree, run:

```powershell
python backend/scripts/build_capability_catalog.py
python backend/scripts/generate_capability_docs.py
python backend/scripts/build_capability_acceptance_manifest.py
python backend/scripts/check_domain_dependencies.py
python backend/scripts/check_runtime_resource_budget.py --strict
```

- [ ] Run focused backend suites, then `python -m pytest -q`. Resolve failures by ownership: Base budget failures in Base, BOP query failures in Craft, and UI behavior failures in the frontend repository.
- [ ] Run `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict` and require zero failures and zero skips for the changed stable scope.
- [ ] In `E:\Projects\ai00\workmanship-web`, run `npm test` and `npm run build:web`. Inspect `git status --short` before committing so unrelated frontend changes are not included.
- [ ] Synchronize the complete build output through the existing build/deployment command. Do not hand-edit generated `dist` JavaScript and do not delete unrelated user files.
- [ ] Restart only `AI00Backend-CapabilityV2`. Verify the configured bind address, `/health`, `/ready`, Catalog release, outline/work-package/detail invocation, lineage asset HTTP 200s, and no new Traceback, 404, 504, OOM, Mount 403, or frontend syntax error in the new startup cycle.
- [ ] Run the 10k browser scenario: first open, one refresh, 20 refreshes, rapid switch, detail open/close, and 5 concurrent sessions. Capture the acceptance JSON and browser console evidence outside Git.
- [ ] Commit frontend source separately in the frontend repository, then commit only generated Catalog/docs, build-owned `dist` assets, and deployment checks in the backend worktree. Do not include the handoff, reviews, `.runtime`, `.superpowers`, or unrelated dirty files. Do not push.

## Final release checklist

- [ ] `craft.bop.structure.outline.get@1`, `craft.bop.work_package.get@2`, and `craft.bop.entry.detail.get@1` are in the frozen Catalog with approved budgets and closed schemas.
- [ ] The large-version lineage path has no full `/entries` request and no full `load_bop_aggregate()` filtering.
- [ ] Old small-version clients still work; large legacy reads fail explicitly without query materialization.
- [ ] 10k first load, refresh, 20-cycle refresh, fast switch, and 5-user tests meet the 75% memory ceiling and show no linear retained-memory growth.
- [ ] Runtime workers and each domain's independent connection pool are explicit, auditable, and within the deployment ceiling.
- [ ] `/health` remains cheap, `/ready` reflects memory admission, and diagnostics are administrator-only and payload-free.
- [ ] Full backend, frontend, strict offline acceptance, domain boundary, deployment HTTP, and browser-console checks pass.
- [ ] Unrelated files are unchanged; commits remain local until the user separately authorizes a push.
