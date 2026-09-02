# Capability Governance Continuous Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Continuously reduce the current unbound public-entry blockers by root-cause group and domain, while preserving Capability semantics, revision safety, and release acceptance.

**Architecture:** Treat each public REST or legacy API entry as evidence, but repair by root-cause group. Existing Capability contracts are reused first; Provider extensions are added only when the route semantics can be represented without loss. Entries with no valid semantic owner are retired or explicitly quarantined instead of being pseudo-bound.

**Tech Stack:** FastAPI routers, Python Provider Capabilities, Gateway compatibility adapter, deterministic governance scanner, pytest, offline strict acceptance.

**Spec:** Current governance snapshot `.runtime/capability-governance-scan-bop-version-update.json` and the approved continuous-governance design in this task.

**Latest checkpoint (2026-08-20):** snapshot `sha256:c24a235c7452545c7d4a59a9c7453ec081db384006aada31db93126938c93029`; 105 deterministic findings (98 blocking exposure findings and 7 provider warnings). Retiring the unsupported Ontology compatibility routes with explicit HTTP 410 removed twelve blockers; adding the bounded `craft.gbop.station_autolink.preview@1`, `craft.ebom.legacy_read@1`, `craft.ebom.vpps_check.read@1`, `craft.bop.fork_preset.read@1`, and the explicit `project_bop_lines` operation on `craft.bop.entry.legacy_read@1` removed six more. The current blocker queue is Craft 92, Agent 6; the seven warnings are provider-descriptor gaps. Remaining Craft entries are predominantly writes/imports/lifecycle transitions and must wait for typed Providers; Agent chat/confirmation flows need a separate interaction contract. No route is bound by name alone; remaining entries stay queued until semantic contracts match.

## Global Constraints

- Do not write production databases, Catalog releases, or permissions during governance work.
- Every behavior change starts with a failing test and ends with targeted tests, governance scan, and strict offline acceptance.
- A route may bind to an existing Capability only when its input, output, side effects, lifecycle, and error semantics remain valid.
- Retired or semantically mismatched Capabilities are never used as compatibility labels.
- Preserve unrelated working-tree changes.

---

### Task 1: Build the batch baseline and queue

**Files:**
- Read: `.runtime/capability-governance-scan-bop-version-update.json`
- Read: `backend/capability_governance_test/analysis.py`
- Read: `backend/capability_governance_test/rules.py`

**Interfaces:**
- Consumes: immutable scanner snapshot and deterministic analysis.
- Produces: counts grouped by domain, source file, route, and semantic candidate.

- [x] Run the offline scanner and deterministic analysis against the current worktree.
- [x] Record the baseline snapshot hash and blocker counts.
- [x] Order work by Craft BOP/GBOP, Craft secondary routers, Knowledge legacy, Agent legacy, then quarantine candidates.

### Task 2: Migrate exact BOP version routes

**Files:**
- Modify: `plugins/craft/craft_backend/routers/_bop/versions.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_versions.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_writes.py`
- Modify: `plugins/craft/craft_backend/capabilities/contracts.py`
- Test: `backend/tests/test_craft_capability_contracts.py`
- Test: `backend/tests/test_craft_bop_version_capabilities.py`
- Test: `backend/tests/test_craft_write_capabilities.py`
- Test: `backend/tests/test_bop_version_inserts.py`

**Interfaces:**
- Consumes: `craft.bop.version.get@1`, `craft.bop.version.list@1`, `craft.bop.version.create@1`, `craft.bop.draft.change.preview@1`, `craft.bop.draft.change.apply@1`.
- Produces: Gateway-backed GET/list/create/PATCH routes with revision-pinned metadata updates.

- [x] Add failing AST and Provider-contract tests.
- [x] Route exact reads and creates through Gateway.
- [x] Route supported metadata PATCH fields through preview/apply.
- [x] Move PBOM readiness validation and version-field persistence into the Provider.
- [x] Run targeted tests, scanner, and strict acceptance.

### Task 3: Migrate the next BOP/GBOP route group

**Files:**
- Inspect and modify: `plugins/craft/craft_backend/routers/_bop/entries.py`
- Inspect and modify: `plugins/craft/craft_backend/routers/gbop.py`
- Inspect and modify: `plugins/craft/craft_backend/routers/_bop/lifecycle.py`
- Inspect and modify: `plugins/craft/craft_backend/routers/_bop/fork.py`
- Test: matching Craft router and Provider test files.

**Interfaces:**
- Consumes: existing Craft BOP entry, structure, linked-parts, work-package, draft-change, and PBOM Capabilities.
- Produces: one semantic route batch at a time; unsupported lifecycle transitions remain explicit blockers until a real Provider exists.

- [x] Group routes by exact operation and lifecycle semantics before editing.
- [x] Write one failing route-binding test per selected route family.
- [x] Migrate exact reads and typed draft changes first (GBOP version inventory, BOP linked-parts, BOP version PBOM, BOP entry detail).
- [ ] Keep freeze/publish/fork routes unbound until snapshot and state-transition semantics have a Provider contract.
- [x] Migrate the exact GBOP version inventory read (`GET /api/gbop/versions`) through `craft.gbop.release.search@1` with a bounded 500-item output.
- [x] Re-run scanner and strict acceptance; update the queue.
- [x] Refresh the local Catalog release, generated Capability docs, acceptance manifest, coverage review, and User Function Registry after the Provider contract change.

### Task 4: Migrate Craft secondary domains

**Files:**
- Inspect and modify: `plugins/craft/craft_backend/routers/craft_library.py`
- Inspect and modify: `plugins/craft/craft_backend/routers/import_export.py`
- Inspect and modify: `plugins/craft/craft_backend/routers/ontology.py`
- Inspect and modify: `plugins/craft/craft_backend/routers/rules.py`
- Inspect and modify: `plugins/craft/craft_backend/routers/canvases.py`
- Test: corresponding existing Craft capability and router tests.

**Interfaces:**
- Consumes: factory resource, rule, ontology, export, canvas, and data-exchange Capabilities where contracts match.
- Produces: Gateway-backed secondary Craft routes or explicit retirement decisions.

- [ ] Bind existing exact Capability matches.
- [ ] Extend Providers only for fields and errors already represented by the domain contract.
- [x] Retire stale Ontology aliases and placeholders with explicit 410 responses when no valid Capability exists.
- [x] Add the bounded `craft.gbop.station_autolink.preview@1` Provider and Gateway adapter.
- [x] Add the bounded `craft.ebom.legacy_read@1` Provider and Gateway adapter for snapshot diff.
- [x] Add the bounded `craft.ebom.vpps_check.read@1` Provider and Gateway adapter for the four-rule VPPS validation projection.
- [x] Add the bounded `craft.bop.fork_preset.read@1` Provider and Gateway adapters for fork-preset list/detail reads.
- [x] Extend `craft.bop.entry.legacy_read@1` with the bounded `project_bop_lines` projection and migrate the Project route through Gateway.
- [x] Re-run scanner and strict acceptance.

### Task 5: Migrate Knowledge and Agent legacy APIs

**Files:**
- Inspect and modify: `plugins/knowledge/knowledge_backend/api/knowledge_hub_legacy.py`
- Inspect and modify: `plugins/knowledge/knowledge_backend/api/knowledge_entries_legacy.py`
- Inspect and modify: `plugins/agent/agent_backend/routers/ai_chat.py`
- Inspect and modify: `plugins/agent/agent_backend/routers/ai_audit.py`
- Inspect and modify: `plugins/agent/agent_backend/routers/flows.py`
- Test: corresponding Knowledge and Agent capability contract tests.

**Interfaces:**
- Consumes: existing Knowledge document/search/revision Capabilities and Agent session/flow/audit Capabilities.
- Produces: Gateway-backed legacy compatibility routes with preserved response envelopes.

- [x] Group legacy routes by target Capability and response adapter.
- [x] Add failing route-binding tests before edits.
- [x] Migrate the exact Knowledge entry GET read through `knowledge.get`.
- [x] Extend scanner coverage so explicit Capability literals in `legacy_api` handlers become evidence.
- [x] Migrate reads first, then writes requiring explicit idempotency or approval (Knowledge legacy entry list is now Gateway-backed).
- [x] Migrate Agent audit record and super-admin audit-log reads through `agent.audit.record@1` and `agent.audit.read@1`.
- [x] Migrate Agent session list/get/create/delete routes through `agent.session.read@1` and `agent.session.change.apply@1`.
- [x] Retire the unsupported Agent `/api/ai/balance` placeholder with an explicit 410 response; keep semantically distinct chat/tool/admin flows queued.
- [x] Retire the always-rejected Agent `/api/ai/admin-config` write placeholder with an explicit 410 response.
- [x] Move `/api/flows/gen-script` behind the new `agent.script.generate@1` Gateway/Provider boundary with bounded input/output contracts.
- [x] Move `GET /api/ai/admin-config` behind `agent.runtime.config.read@1`, preserving Pi-runtime and environment metadata semantics.
- [x] Extend PBOM version contracts with legacy metadata and migrate snapshot list/create/get adapters through the native PBOM Capabilities.
- [x] Extend bounded PBOM part search output and migrate the legacy snapshot-parts read adapter.
- [x] Extend `knowledge.entry.change.apply` with legacy field/permission semantics and migrate Knowledge entry create/update/delete adapters.
- [ ] Retire remaining routes whose legacy behavior has no safe Capability equivalent.
- [x] Re-run scanner and strict acceptance.

### Task 6: Close the loop

**Files:**
- Read: `.runtime/capability-governance-scan-*.json`
- Read: generated acceptance reports in `.runtime/`

**Interfaces:**
- Consumes: current snapshot and deterministic findings.
- Produces: next batch queue or a blocked report with exact route/provider evidence.

- [x] Recompute finding count versus root-cause group count after each batch.
- [x] Verify every remaining blocker is either queued with a safe owner or explicitly quarantined.
- [x] Run the relevant Craft/Knowledge/Agent pytest suites (182 passed), `compileall`, `git diff --check`, governance scan, and strict acceptance.
- [ ] Stop only when the next item requires a new domain decision, production migration, or missing external authority.
