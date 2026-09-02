# Integration Structural Owner Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all 12 unresolved Integration Web route occurrences with exact, governed Integration capabilities backed by one owner application boundary, without preserving plaintext credentials, arbitrary SQL, synthetic sync success, or route-shaped providers.

**Architecture:** `IntegrationApplication` remains the only public business boundary. Connector persistence, credential enrollment, bounded connector-runtime calls, mapping grammar, target-Catalog validation, batch updates, and durable import operations are expressed through narrow ports and Integration-owned repositories. The Web page calls exact stable capabilities through `AI00ExistingCapabilityClient`; REST-shaped compatibility calls are removed from the immutable frontend commit.

**Tech Stack:** Python 3.12, MySQL/OceanBase domain migrations, Capability V2 contracts/providers, vanilla JavaScript, Node.js/jsdom, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-structural-owner-services-design.md`

## Global Constraints

- Scope is exactly the 12 groups / 12 occurrences in `docs/governance/integration-structural-web-remediation.json`.
- Integration owns only `plugins/integration/**`, its domain migration path, its public provider, and the Web adapter in `web/ext_datasource/ext_ds.js`; it must not query or write another domain's tables.
- Connector create/update accepts an opaque one-time credential-enrollment handle or `credential_ref`; raw passwords and credentials must never enter a Capability payload, audit event, repository row, or generated evidence.
- External discovery, preview, connection test, and import are bounded by explicit timeout and result limits; unknown external outcomes are durable and reconcilable, never reported as success.
- Mapping definitions use a closed schema and allowlisted transform grammar. SQL fragments such as `filter_sql` are forbidden.
- Mapping targets pin exact `target_capability_id`, `target_major_version`, and minimum Catalog release; validation occurs before persistence or dispatch.
- Writes require actor/team scope, optimistic revision where applicable, idempotency, confirmation, and durable audit/operation evidence.
- Do not reduce unresolved counts through BFF, operations exclusion, legacy registration, or another domain's Capability.
- Preserve the already closed Base 16/16 groups and 33/33 occurrences and immutable deployable scanning rules.
- Backend baseline: `4f54229bbf93eb74fa37f3fb04789effdabcfba9`.
- Frontend baseline: `964233cf30aebddfc1167a5ac3eff1252cfc28eb`.

---

### Task 1: Integration owner boundary, exact contracts, and durable ports

**Files:**
- Create: `plugins/integration/integration_backend/application/ports.py`
- Create: `plugins/integration/integration_backend/application/operations.py`
- Modify: `plugins/integration/integration_backend/application/service.py`
- Modify: `plugins/integration/integration_backend/application/__init__.py`
- Modify: `plugins/integration/integration_backend/capabilities/contracts.py`
- Modify: `plugins/integration/integration_backend/capabilities/descriptors.py`
- Modify: `plugins/integration/integration_backend/capabilities/provider.py`
- Modify: `plugins/integration/integration_backend/infrastructure/repository.py`
- Create: `backend/db/migrations/domains/integration/0002_integration_structural_operations.sql`
- Test: `plugins/integration/tests/test_integration_owner_services.py`
- Test: `plugins/integration/tests/test_integration_provider.py`

**Interfaces:**
- Consumes: `CapabilityContext`, Integration domain DB, immutable Catalog resolver, credential-vault enrollment port, connector-runtime port, operation clock/ID port.
- Produces: stable exact capabilities `integration.connector.search@1`, `integration.connector.create@1`, `integration.connector.update@1`, `integration.connector.schema.discover@1`, `integration.connector.connection.test@1`, `integration.mapping.search@1`, `integration.field_mapping.search@1`, `integration.mapping.source_columns.discover@1`, `integration.mapping.preview@1`, `integration.mapping.create@1`, `integration.field_mapping.batch.update@1`, and `integration.mapping.import.start@1`.

- [ ] **Step 1: Write failing contract and owner-service tests**

Assert closed schemas for all 12 targets; exact 1..200 list/preview limits; no `password`, `credentials`, `filter_sql`, arbitrary config, or unknown fields; connector writes accept only `credential_enrollment_handle`/`credential_ref`; field mappings use `source_field`, `target_field`, and allowlisted `transform_expression`; target capability/version/release are mandatory. Assert actor/team scoping, optimistic revision, idempotent replay/conflict, target-Catalog rejection, network-policy rejection, bounded runtime timeout/result caps, and durable `accepted/succeeded/failed/outcome_unknown` operation transitions.

- [ ] **Step 2: Run red tests**

Run: `python -m pytest -q -p no:cacheprovider plugins/integration/tests/test_integration_owner_services.py plugins/integration/tests/test_integration_provider.py`

Expected: failures because the four exact field/source/import capabilities, credential enrollment port, target-Catalog validation, batch semantics, and durable operation store do not exist.

- [ ] **Step 3: Add narrow ports and migration**

Define protocols for credential enrollment (`consume(handle, actor_gid, team_gid) -> credential_ref`), Catalog validation (`require_stable(capability_id, major_version, minimum_release)`), connector runtime (`test/discover/source_columns/preview` with timeout and caps), and operation persistence/reconciliation. Add Integration-owned idempotency/audit/operation rows in forward migration 0002 with unique `(owner_gid, capability_id, idempotency_key)` and no credential material.

- [ ] **Step 4: Implement exact owner outcomes**

Split `IntegrationApplication.invoke()` dispatch into cohesive connector, mapping-read, mapping-write, and import methods while retaining one public owner boundary. Translate repository misses/conflicts into declared business errors, redact runtime output, reject arbitrary SQL/transforms, and persist unknown external outcomes before returning. The provider is a thin schema/descriptor adapter only.

- [ ] **Step 5: Run focused and migration gates**

Run the two test modules, `backend/tests/test_domain_migrations.py`, `backend/tests/test_versioned_migrations.py`, `backend/tests/test_domain_dependency_rules.py`, and `git diff --check`.

Expected: all pass; mutations that accept plaintext passwords, omit target release validation, exceed caps, or return synthetic success fail.

- [ ] **Step 6: Commit**

Commit message: `feat: harden Integration owner services`.

### Task 2: Connector lifecycle Web migration as one governed package

**Files:**
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/ext_datasource/ext_ds.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/ext_datasource/index.html` if credential enrollment UI loading is required
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_integration_connector_capability_migrations.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/package.json`
- Test: `plugins/integration/tests/test_integration_connector_adapters.py`

**Interfaces:**
- Consumes: the five exact connector capabilities and credential-enrollment client from Task 1.
- Produces: governed equivalents for GET/POST `/api/ext-datasources`, PATCH `/api/ext-datasources/{gid}`, GET `/tables`, and POST `/test`, with no route fallback.

- [ ] **Step 1: Write failing browser and adapter-equivalence tests**

Execute the real page module with a fake Capability client. Assert search projection, create/update revision handling, one-time credential enrollment, bounded discovery/test inputs, visible errors, and zero `_cf()` calls for the five connector routes. Assert no raw password appears in recorded capability calls. Add owner-service/provider equivalence tests for the same input/output projections.

- [ ] **Step 2: Run red tests**

Run the new Node test and focused Python adapter test.

Expected: the page still calls five legacy routes and sends `password`, `db_type`, and `database` in legacy shapes.

- [ ] **Step 3: Replace the five connector route calls together**

Replace the password field with a one-time `credential_enrollment_handle` field obtained from the environment's credential-vault enrollment workflow; this page never accepts or transports the secret itself. `IntegrationApplication` consumes the handle through its vault port and persists only the returned `credential_ref`. Map UI fields to `connector_type` and `database_name`, include `expected_revision` on update, use exact caps, and treat `outcome_unknown` as pending/reconciling rather than success.

- [ ] **Step 4: Run behavior, syntax, and official build**

Run the new Node test, existing Web capability migration suites, `node --check web/ext_datasource/ext_ds.js`, and `npm run build:web`.

Expected: all pass and immutable source/dist contain none of the five connector route literals.

- [ ] **Step 5: Commit frontend**

Commit source, test, package entry, and intended `dist-production` output as `feat: govern Integration connector UI`.

### Task 3: Mapping reads, field mappings, discovery, and preview

**Files:**
- Modify: `plugins/integration/integration_backend/application/service.py`
- Modify: `plugins/integration/integration_backend/infrastructure/repository.py`
- Modify: `plugins/integration/integration_backend/capabilities/contracts.py`
- Test: `plugins/integration/tests/test_integration_mapping_queries.py`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/ext_datasource/ext_ds.js`
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_integration_mapping_read_capability_migrations.js`

**Interfaces:**
- Consumes: mapping/connector ownership and bounded runtime ports from Task 1.
- Produces: exact governed replacements for GET `/api/ext-mappings`, GET `/api/ext-field-mappings`, GET `/columns`, and GET `/preview`.

- [ ] **Step 1: Write failing query/projection tests**

Assert mapping search filters by owned `datasource_gid`; field mapping search returns a bounded collection rather than singular `mapping.get`; source-column discovery binds the owned mapping to its connector; preview returns at most the requested cap, separates raw/redacted projections, and exposes structured timeout/outcome state. Browser tests must assert the four exact capability IDs and no route fallback.

- [ ] **Step 2: Run red tests**

Expected: current service lacks `integration.field_mapping.search` and `integration.mapping.source_columns.discover`, while the page calls four legacy routes.

- [ ] **Step 3: Implement repository/service projections and migrate Web reads**

Keep DB rows private to Integration; return closed browser DTOs. Never expose credential refs, arbitrary connector config, or unrestricted raw preview values. Update the page to consume `items`, `objects/columns`, and bounded preview output explicitly.

- [ ] **Step 4: Run focused suites and build**

Run mapping query tests, Node behavior test, all existing Integration provider tests, syntax check, and official build.

Expected: all pass and the four route occurrences disappear from a fresh immutable source scan.

- [ ] **Step 5: Commit backend and frontend separately**

Commit messages: `feat: add governed Integration mapping queries` and `feat: migrate Integration mapping reads`.

### Task 4: Mapping create, bounded batch update, and durable import

**Files:**
- Modify: `plugins/integration/integration_backend/application/service.py`
- Modify: `plugins/integration/integration_backend/application/operations.py`
- Modify: `plugins/integration/integration_backend/infrastructure/repository.py`
- Modify: `plugins/integration/integration_backend/capabilities/contracts.py`
- Test: `plugins/integration/tests/test_integration_mapping_commands.py`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/ext_datasource/ext_ds.js`
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_integration_mapping_write_capability_migrations.js`

**Interfaces:**
- Consumes: exact target-Catalog validation, idempotency/audit store, and durable operation store from Task 1.
- Produces: governed replacements for POST `/api/ext-mappings`, PUT `/api/ext-field-mappings/batch`, and POST `/import`.

- [ ] **Step 1: Write failing command tests**

Assert mapping create rejects `filter_sql`, requires exact stable target version/release, and stores only restricted transforms. Assert batch size is 1..200, every item has a deterministic identity/revision, transaction policy is explicitly all-or-nothing, revision conflicts are returned without partial writes, and idempotent replay is byte-equivalent. Assert import creates one durable run bound to mapping/target/release/idempotency and returns accepted; retry reconciles accepted/outcome-unknown instead of generating a second run.

- [ ] **Step 2: Run red tests**

Expected: current create accepts a contract unrelated to the page, batch update is a generic single mapping update, and sync start fabricates IDs without persistence.

- [ ] **Step 3: Implement commands and migrate browser calls**

Translate the UI's ontology selection into an exact target capability reference through a finite adapter; do not forward ontology IDs as executable rules. Replace the three route calls with exact capabilities, pass revision/idempotency/confirmation, and display accepted/pending/outcome-unknown honestly.

- [ ] **Step 4: Run focused suites, syntax, and build**

Run command tests, target-gateway tests, Node migration tests, syntax checks, and official build.

Expected: all pass and none of the three write route occurrences remain.

- [ ] **Step 5: Commit backend and frontend separately**

Commit messages: `feat: govern Integration mapping commands` and `feat: migrate Integration mapping writes`.

### Task 5: Immutable Integration closure and release evidence

**Files:**
- Modify: `backend/scripts/build_integration_structural_web_remediation.py`
- Modify: `backend/tests/test_integration_structural_remediation_manifest.py`
- Regenerate: immutable route inventory, root-cause ledger, atomic contracts, Integration manifest, structural plan, provider trust, Catalog, docs, acceptance manifest, and deployable evidence.
- Create: `.superpowers/sdd/2026-08-28-integration-structural-owner-services/task-5-report.md`

**Interfaces:**
- Consumes: committed backend/frontend heads from Tasks 1-4.
- Produces: immutable evidence showing Integration 12/12 migrated groups and 12/12 migrated occurrences, with the canonical remainder reduced from 26/29 to 14/17.

- [ ] **Step 1: Add failing source-derived closure tests**

Require exact occurrence identities, immutable frontend commit/blob hashes, provider/service/contract anchors, no route literal fallback, no plaintext credential field, no arbitrary SQL, and exact union arithmetic: Base 16/33 plus Integration 12/12 removed, leaving only Craft/Agent/Project 14 groups / 17 occurrences.

- [ ] **Step 2: Run red closure tests**

Expected: Integration manifest remains 0/12 migrated and canonical remainder remains 26/29.

- [ ] **Step 3: Commit the official frontend build and regenerate in dependency order**

Freeze the exact frontend commit first. Regenerate deployable scan, wrapper contracts, route inventory, ledger, atomic contracts, Integration manifest, structural plan, provider trust, Catalog, docs, and acceptance manifest. Every builder must pass `--check` without worktree-derived revision labels.

- [ ] **Step 4: Run final verification**

Run all Integration tests, route/ledger/atomic/Integration/Base/structural tests, domain dependency and migration gates, frontend behavior suites/build, all generator checks, and `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`.

Expected: Integration 12/12 and 12/12; Base preserved 16/16 and 33/33; canonical unresolved 14 groups / 17 occurrences; strict acceptance zero failed/skipped. Record separate pre-existing advisories without changing their counts.

- [ ] **Step 5: Commit and request whole-batch review**

Commit generated backend evidence as `docs: close Integration structural governance`. Record exact backend/frontend commits, report hashes, Catalog release, acceptance report ID, test counts, and any non-Integration advisories in the task report.

### Task 6: Production execution and control-plane closure

**Files:**
- Modify: `plugins/integration/integration_backend/application/service.py`
- Modify: `plugins/integration/integration_backend/application/sync.py`
- Modify: `plugins/integration/integration_backend/infrastructure/repository.py`
- Modify: `plugins/integration/integration_backend/infrastructure/target_catalog.py`
- Modify: Integration composition, contracts, descriptors, provider, migrations, and focused tests.
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/ext_datasource/ext_ds.js`
- Modify: Integration Web migration tests and immutable evidence builders.
- Regenerate: provider trust, Catalog, docs, acceptance, Integration manifest, and deployable evidence.

**Interfaces:**
- Consumes: Task 1-5 owner services, durable operations, tenant-scoped target Catalog, Catalog lineage, and committed frontend evidence.
- Produces: a production-consumable import dispatcher, governed target-binding control plane, callable connection test, execution-time release-floor enforcement, and canonical secret-safe preview evidence.

- [ ] **Step 1: Write failing production-composition tests**

Cover accepted-run atomic claim, actor/team-scoped reload, bounded extraction and restricted transforms, real `DomainCapabilityClient` target dispatch, terminal/outcome-unknown transitions, retry reconciliation, and release-floor cases (older, equal, compatible-newer, breaking-newer). Cover cross-tenant claims and duplicate workers. Cover governed binding upsert/rebind with authorization, exact stable Catalog validation, revision, idempotency, audit, and explicit legacy-mapping disposition. Cover connection test through the real browser client and Gateway write envelope. Cover returned and persisted preview redaction for canonical secret aliases, credential URIs, and PEM material.

- [ ] **Step 2: Confirm red for the five whole-batch findings**

Expected: no production dispatcher consumes accepted runs; connection test lacks its write envelope; target bindings have no governed writer; dispatch ignores the persisted release floor; preview leaks common credential aliases.

- [ ] **Step 3: Implement the minimal owner-domain closure**

Add an atomic claim/load/transition repository boundary and production-composed dispatcher that invokes the persisted exact target through `DomainCapabilityClient`. Keep extraction bounded and transforms finite. Add an Integration-owned privileged binding provisioning/rebinding Capability; never rely on manual steady-state table edits. Leave legacy mappings explicitly `binding_required` until governed rebind rather than inventing a target. Keep connection test classified as an external write and supply confirmation/idempotency through Web. Enforce Catalog lineage at dispatch. Reuse the platform canonical secret detector for both output and persisted operation evidence.

- [ ] **Step 4: Regenerate and verify the full evidence chain**

Regenerate trust, Catalog, docs, acceptance and Integration evidence only after committed source/build identities are fixed. Run focused production dispatcher/control-plane/Gateway/redaction tests, Integration and migration suites, Web behavior/build, domain gates, all generator checks, and strict offline acceptance on a clean commit.

- [ ] **Step 5: Commit and request final whole-batch re-review**

Commit backend and frontend separately when changed. Record exact revisions, Catalog release, acceptance report ID, immutable frontend blob identities, terminal worker evidence, and unchanged Base/Integration/remainder arithmetic in `task-6-report.md`.
