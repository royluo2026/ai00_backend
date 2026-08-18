# Capability Governance Center Design

**Status:** Approved design, pending implementation plan  
**Date:** 2026-08-18  
**Scope:** Capability self-governance only  
**Environment:** Full control plane in test; production receives only release attestation validation  
**Identity:** Existing 64-bit snowflake GID  

## 1. Purpose

This design defines a Capability Governance Center that answers four questions for every governed Capability:

1. What contract exists and which logical Capability and Major does it belong to?
2. Is the contract implemented, exposed, persisted, tested, and currently healthy?
3. Is it duplicated, conflicting, missing, drifting, non-atomic, or incompatible within or across domains?
4. What reviewed change and evidence are required before a release may proceed?

The center is a projection-based governance control plane. It indexes authoritative code contracts, builds immutable snapshots, records evidence and findings, supports reviews and waivers, exposes controlled governance Capabilities to UI and agents, and produces release-gate attestations.

It does not become a second contract authority.

## 2. Relationship to Existing Designs

This document consolidates and refines:

- `2026-08-14-capability-governance-test-center-design.md`
- `2026-08-14-capability-service-contract-classification-design.md`

The formal classification remains:

- A Capability is a governed **Service Operation**.
- `service_operation` is a single externally meaningful business effect.
- `service_facade` orchestrates several governed operations behind one stable operation boundary.
- `internal_operation` is governed but not a general consumer-facing operation.
- `business_effect` describes exactly one business effect, not an implementation step list.

This document adds the persistent GID model, normalized governance database, implementation graph, agent-facing governance Capability surface, dual-Catalog isolation, self-governance rules, full UI information architecture, and production exclusion controls.

## 3. Scope

### 3.1 Included

- Capability logical identity and Major identity
- Lifecycle and semantic classification
- `business_effect`
- Domain ownership
- Input, output, error, permission, confirmation, idempotency, side-effect, consistency, concurrency, and execution policies
- Descriptor, Provider, Handler, Domain Port, Repository, migration, and table implementation chain
- Technical exposure declarations: REST, legacy API, Mount, Agent Tool, MCP Tool, worker, and local runtime
- Tests, evidence, runtime probes, health, and release-gate results
- Duplicate, semantic-overlap, conflict, gap, drift, compatibility, non-atomic facade, and lifecycle-pair analysis
- Change proposals, review, time-bound waiver, audit, and repair-prompt generation
- Search and analysis interfaces for delegated agents

### 3.2 Explicitly Excluded

- Application Use Cases
- Business workflows and business process modeling
- Mapping to concrete UI pages, plugins, or agent workflows as consumers
- Capability-combination discovery for business automation
- Low-code or workflow authoring
- Direct editing or deletion of Capability contracts in the governance UI

These are separate upper-layer topics. The present design provides reliable governed primitives for them without defining them.

## 4. Current Baseline and Domains

The current product Catalog contains **267 Capability descriptors** in release `rel_ff6093704bd2b3500496c5731300b7a7` at design time. Counts are read from the selected Catalog Release and must never be hard-coded into the product.

The official domain list is:

1. `agent`
2. `base`
3. `craft`
4. `device`
5. `digital_model`
6. `factory`
7. `integration`
8. `knowledge`
9. `ontology`
10. `project_management`
11. `simulation`

The Governance Center belongs to `base`. It does not create a twelfth domain.

## 5. Authority Model

### 5.1 Authoritative Sources

The sole contract authorities are:

1. Code Descriptor
2. Signed or formally generated Catalog Release

Provider registrations, implementation code, migrations, routes, and tests are evidence about implementation. They do not redefine the contract.

### 5.2 Governance Database

The database stores:

- stable identities
- projections
- immutable snapshots
- implementation nodes and relations
- findings and evidence
- analysis and test results
- proposals, reviews, and waivers
- health rollups and audit events

Database values never overwrite Descriptor or Catalog content. A mismatch creates a Finding or Proposal.

### 5.3 UI Authority

The UI may:

- search and inspect
- rerun scans and checks
- request analysis
- confirm or reject candidate findings
- submit proposals
- approve or reject within permission
- create and revoke time-bound waivers
- run tests and evaluate release gates
- generate redacted repair prompts

The UI may not:

- edit a Descriptor
- change a Catalog contract directly
- delete a Capability, Finding, Evidence, Review, or Audit Event
- turn an AI recommendation into an approved change without the review path

## 6. Architecture

```text
Descriptor / Provider / Routes / Ports / Repositories / Migrations / Tests
                                  |
                                  v
                    Deterministic governed scanner
                                  |
                                  v
                       Immutable scan snapshot
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
       Identity projection   Implementation graph   Evidence
              |                   |                   |
              +-------------------+-------------------+
                                  |
                                  v
                Deterministic rules + AI advisory review
                                  |
                                  v
              Finding / Proposal / Review / Waiver / Test
                                  |
                                  v
                         Release-gate attestation
```

The deterministic scanner and rule engine are authoritative for release gates. AI is advisory.

## 7. Snowflake GID Model

The existing `backend.platform_sdk.ids.next_gid()` implementation is used.

Its layout is:

- 1 sign bit
- 41 timestamp bits
- 10 machine-ID bits
- 12 sequence bits
- epoch: 2025-01-01 UTC

### 7.1 Two-Level Capability Identity

- `capability_gid`: stable logical identity across lifecycle and Majors
- `capability_version_gid`: stable identity for one Major

The business key remains `capability_id@major`. It is searchable and unique, but relationships use GIDs.

### 7.2 Transport Rules

- Database: signed `BIGINT`
- Python: integer
- JSON, browser, plugin, and agent surfaces: decimal string
- JavaScript must never parse a GID as `Number`

### 7.3 Generator Safety

- `machine_id` is deployment-assigned and not identically hard-coded across concurrent generators.
- Clock rollback, sequence exhaustion, and ID collision are explicit errors.
- A detected collision is a blocking Finding and release failure.
- The database does not silently regenerate or overwrite an existing GID.

All Snapshot, Scan Run, Node, Relation, Finding, Finding Subject, Evidence, Analysis Run, Proposal, Review, Waiver, Test Run, Test Result, Health Rollup, Release Report, and Audit Event entities receive independent snowflake GIDs.

## 8. Database Design

### 8.1 Placement and Conventions

- Physical database follows the existing single-database deployment.
- Tables use the `workmanship_base_` prefix.
- Full governance tables are test-environment migrations.
- The existing `workmanship_base_capability_catalog_releases` table is reused.
- Important query attributes are normal typed columns.
- Extensible structured payloads use canonical JSON serialized into `LONGTEXT`, validated by the application and hashed.
- Mutable rows use `row_version` optimistic locking.
- Immutable rows do not expose update operations.
- Capability identities and governance history have no hard-delete path.
- Common mutable fields are `created_at`, `updated_at`, `created_by_gid`, `updated_by_gid`, and `row_version` as applicable.

### 8.2 Identity and Version Projection

#### `workmanship_base_capability_entries`

- `capability_gid` PK
- `capability_id` unique
- `owner_domain`
- `current_major_version`
- `current_lifecycle_status`
- `first_seen_at`
- `last_seen_at`
- `row_version`

#### `workmanship_base_capability_versions`

- `capability_version_gid` PK
- `capability_gid` FK
- `major_version`
- `semantic_class`
- `business_effect`
- `lifecycle_status`
- `first_seen_snapshot_gid`
- `latest_snapshot_gid`
- `retired_at`
- `row_version`

Unique: `(capability_gid, major_version)`.

### 8.3 Scans and Immutable Snapshots

#### `workmanship_base_capability_scan_runs`

- `scan_run_gid` PK
- `environment_key`
- `trigger_type`
- `code_revision`
- `catalog_release_id`
- `requested_by_gid`
- `idempotency_key`
- `status`
- `started_at`
- `finished_at`
- `error_summary`

#### `workmanship_base_capability_snapshots`

- `snapshot_gid` PK
- `scan_run_gid` FK
- `snapshot_hash` unique
- `code_revision`
- `catalog_release_id`
- `descriptor_count`
- `created_at`

#### `workmanship_base_capability_snapshot_entries`

- `snapshot_entry_gid` PK
- `snapshot_gid` FK
- `capability_version_gid` FK
- `descriptor_hash`
- `input_schema_hash`
- `output_schema_hash`
- `error_schema_hash`
- `policy_hash`
- `provider_hash`
- `descriptor_json`
- `created_at`

Unique: `(snapshot_gid, capability_version_gid)`.

### 8.4 Implementation Graph

#### `workmanship_base_capability_implementation_nodes`

- `implementation_node_gid` PK
- `snapshot_gid` FK
- `owner_domain`
- `node_type`
- `canonical_key`
- `source_path`
- `source_symbol`
- `http_method`
- `route_path`
- `artifact_hash`
- `metadata_json`

Supported node types include descriptor, provider, handler, domain_port, repository, rest_route, legacy_api, mount_binding, agent_tool, mcp_tool, database_table, migration, worker, local_runtime, and test_case.

#### `workmanship_base_capability_bindings`

- `binding_gid` PK
- `snapshot_gid` FK
- `capability_version_gid` FK
- `implementation_node_gid` FK
- `binding_type`
- `binding_hash`

Binding types include `implemented_by`, `exposed_by`, `persists_through`, `covered_by`, and `declared_in`.

#### `workmanship_base_capability_implementation_relations`

- `relation_gid` PK
- `snapshot_gid` FK
- `from_node_gid` FK
- `to_node_gid` FK
- `relation_type`
- `relation_hash`

Typed node and relation tables are preferred over an unconstrained polymorphic relation table because they preserve referential integrity.

### 8.5 Evidence, Tests, and Health

#### `workmanship_base_capability_evidence`

- `evidence_gid` PK
- `snapshot_gid` FK
- `capability_version_gid` FK
- `implementation_node_gid` nullable FK
- `evidence_type`
- `evidence_level`
- `result_status`
- `source_hash`
- `observed_at`
- `expires_at`
- `summary`
- `detail_json`

#### `workmanship_base_capability_test_runs`

- `test_run_gid` PK
- `snapshot_gid` FK
- `profile`
- `environment_key`
- `requested_by_gid`
- `idempotency_key`
- `status`
- `started_at`
- `finished_at`
- `summary_json`

#### `workmanship_base_capability_test_results`

- `test_result_gid` PK
- `test_run_gid` FK
- `capability_version_gid` FK
- `case_key`
- `evidence_level`
- `status`
- `duration_ms`
- `error_code`
- `redacted_detail_json`

#### `workmanship_base_capability_health_rollups`

- `health_rollup_gid` PK
- `snapshot_gid` FK
- `capability_version_gid` FK
- `health_status`
- `evidence_coverage`
- `blocking_finding_count`
- `warning_finding_count`
- `last_verified_at`
- `computed_at`

### 8.6 Analysis and Findings

#### `workmanship_base_capability_analysis_runs`

- `analysis_run_gid` PK
- `snapshot_gid` FK
- `analysis_type`
- `scope_type`
- `scope_json`
- `deterministic_status`
- `ai_advisory_status`
- `requested_by_gid`
- `idempotency_key`
- `started_at`
- `finished_at`
- `model_ref`
- `prompt_hash`
- `result_summary_json`

#### `workmanship_base_capability_findings`

- `finding_gid` PK
- `analysis_run_gid` nullable FK
- `snapshot_gid` FK
- `finding_type`
- `severity`
- `status`
- `source_type`
- `confidence`
- `finding_fingerprint`
- `title`
- `summary`
- `recommendation`
- `confirmed_by_gid`
- `confirmed_at`
- `row_version`

#### `workmanship_base_capability_finding_subjects`

- `finding_subject_gid` PK
- `finding_gid` FK
- `capability_version_gid` FK
- `subject_role`
- `evidence_gid` nullable FK

The subject table is required because a cross-domain duplicate or conflict may involve two or more Capability Majors.

### 8.7 Change, Review, and Waiver

#### `workmanship_base_capability_change_proposals`

- `proposal_gid` PK
- `proposal_batch_gid` nullable
- `capability_version_gid` FK
- `base_snapshot_gid` FK
- `proposed_descriptor_hash`
- `change_type`
- `risk_level`
- `status`
- `submitted_by_gid`
- `submitted_at`
- `stale_at`
- `summary`
- `change_json`
- `row_version`

#### `workmanship_base_capability_reviews`

- `review_gid` PK
- `proposal_gid` FK
- `review_stage`
- `decision`
- `reviewer_gid`
- `decision_reason`
- `evidence_snapshot_gid`
- `decided_at`

#### `workmanship_base_capability_waivers`

- `waiver_gid` PK
- `finding_gid` FK
- `capability_version_gid` FK
- `scope`
- `reason`
- `granted_by_gid`
- `starts_at`
- `expires_at`
- `revoked_at`
- `status`
- `row_version`

Waivers are always bounded, owned, expiring, and auditable. Permanent waiver is not supported.

#### `workmanship_base_capability_release_reports`

- `release_report_gid` PK
- `code_revision`
- `product_catalog_release_id`
- `snapshot_gid` FK
- `test_run_gid` FK
- `conclusion`
- `blockers_json`
- `report_hash`
- `signing_key_id`
- `signature`
- `evaluated_by_gid`
- `evaluated_at`
- `expired_at`

Release reports are immutable and signed over their canonical payload. A changed pinned input does not update a prior report; it marks the prior conclusion expired and requires a new report GID.

### 8.8 Audit

#### `workmanship_base_capability_audit_events`

- `audit_event_gid` PK
- `event_type`
- `entity_type`
- `entity_gid`
- `actor_type`
- `actor_gid`
- `request_gid`
- `before_hash`
- `after_hash`
- `redacted_detail_json`
- `occurred_at`

Audit events are append-only.

## 9. Lifecycle Models

### 9.1 Capability Lifecycle

```text
experimental -> stable -> deprecated -> retired
```

- Transitions require code change, validation, and review.
- `retired` is a tombstone, not deletion.
- Reusing a retired Capability ID for a different business meaning is forbidden.

### 9.2 Proposal Lifecycle

```text
detected -> draft -> submitted -> checking -> pending_approval
         -> approved -> released
```

Side states:

- `checks_failed`
- `rejected`
- `withdrawn`
- `superseded`
- `expired`
- `stale`

A code, Descriptor, Catalog, or evidence hash change makes an existing approval stale.

### 9.3 Finding Lifecycle

```text
candidate -> confirmed -> resolving -> resolved
          -> rejected
          -> waived (time bounded)
```

AI creates only `candidate` findings. Deterministic validation or a human reviewer is required for confirmation.

## 10. Scanning and Analysis

### 10.1 Deterministic Scanner

The scanner reads only approved repository roots and declared manifests. It statically parses and performs bounded runtime introspection of:

- Descriptors and Catalog
- official-domain and Provider assembly
- Gateway registration
- Handler, Domain Port, and Repository bindings
- routes and technical exposure bindings
- migrations and referenced tables
- tests and acceptance manifests

It does not execute arbitrary source code, shell commands, SQL, user paths, or environment-file reads.

### 10.2 Deterministic Findings

The release-authoritative engine detects at minimum:

- Descriptor without Provider
- Provider without declared Descriptor
- exposed route or Mount without a valid Capability
- declared strong write without transactional participant
- repository/table/migration mismatch
- permissions or confirmation-policy mismatch
- schemas or domain errors drifting from Catalog
- missing required tests or evidence
- stale evidence after code change
- lifecycle incompatibility
- governance test artifacts in a production build

### 10.3 Cross-Domain Semantic Analysis

Candidate generation uses:

- business effect
- business object
- input and output schemas
- permissions
- side effects
- consistency and transaction boundary
- Provider behavior
- lifecycle and related operation pairs

Names alone are insufficient.

To avoid quadratic AI work, deterministic blocking and similarity rules first produce a bounded candidate set. AI reviews candidates only.

### 10.4 AI Advisory Analysis

AI may identify:

- duplicate operations
- semantic overlap with different names
- conflicting domain ownership
- missing operations or lifecycle pairs
- non-atomic facades
- unclear business effects
- likely contract/implementation mismatch

It returns evidence, confidence, recommendation, and optionally a redacted external-agent repair prompt. It cannot approve, modify, waive, delete, or release.

Every AI result records model reference, analysis-policy version, prompt hash, snapshot GID, and output hash.

## 11. Test Evidence and Health

### 11.1 Profiles

Each Capability Major has a test profile such as:

- read
- CRUD
- state transition
- async job
- external connector
- service facade with required branch coverage

### 11.2 Evidence Levels

1. contract
2. provider
3. repository and codec
4. gateway
5. technical exposure
6. runtime probe
7. runtime end-to-end

Evidence binds code, Catalog, Provider, Schema, Migration, and fixture hashes. A changed dependency makes evidence stale.

### 11.3 Health States

- `healthy`: required evidence is complete and current
- `degraded`: non-critical checks are failing
- `broken`: a required contract, implementation, or runtime call fails
- `unverified`: required evidence has not been obtained
- `stale`: evidence no longer matches current inputs

Contract-only success is never displayed as healthy.

### 11.4 Scheduling

- Frequent checks are read-only, bounded, and low cost.
- Real writes, state transitions, and full OceanBase end-to-end tests run explicitly before a formal release.
- Health polling never writes business data.
- A governance failure does not stop normal runtime calls, but required failures block release.

## 12. Governance Capability Surface

The full interface is in the test-only governance Catalog extension and is owned by `base`.

### 12.1 Agent-Oriented Read and Analysis

#### `base.capability_registry.search@1`

Searches by Capability ID, GID, business effect, domain, semantic class, lifecycle, health, or Finding type.

#### `base.capability_registry.get@1`

Returns one Major's contract projection, lifecycle, implementation chain, exposures, persistence dependencies, evidence, health, and open findings.

#### `base.capability_graph.get@1`

Returns a bounded local graph. Depth, node count, and edge count are mandatory limits.

#### `base.capability_finding.search@1`

Returns authorized duplicate, overlap, conflict, gap, drift, compatibility, and blocking findings.

#### `base.capability_analysis.run@1`

Starts deterministic and optional AI advisory analysis pinned to a Snapshot. Inputs are structured scope and check types; arbitrary SQL, path, command, or system prompt is forbidden.

#### `base.capability_analysis.get@1`

Returns run state, summaries, and candidate Finding GIDs.

#### `base.capability_repair_prompt.generate@1`

Generates a redacted, evidence-bound prompt containing change boundary, required tests, forbidden changes, and acceptance conditions.

### 12.2 Administrator Governance

- `base.capability_scan.run@1`
- `base.capability_test.run@1`
- `base.capability_proposal.submit@1`
- `base.capability_review.decide@1`
- `base.capability_waiver.grant@1`
- `base.capability_waiver.revoke@1`
- `base.capability_release_gate.evaluate@1`

### 12.3 Permissions

- `system.capability.read`
- `system.capability.analyze`
- `system.capability.govern`
- `system.capability.release`

Agents receive short-lived delegated identity and normally only `read` and `analyze`. An agent cannot approve its own proposal or finding.

### 12.4 Standard Agent Flow

```text
registry.search
  -> registry.get / graph.get
  -> analysis.run
  -> analysis.get
  -> finding.search
  -> repair_prompt.generate
  -> external coding agent changes code
  -> rescan and Proposal
  -> independent review
```

## 13. Governance UI

The full UI is test-only. Contract fields are read-only.

### 13.1 Global Overview

- product Capability count and governance-extension count shown separately
- real 11-domain summary
- evidence coverage
- open and blocking findings
- release-gate state
- global search and filters

### 13.2 Capability Inventory

Columns include:

- snowflake GID
- Capability ID and Major
- single business effect
- domain
- semantic class
- lifecycle
- health and evidence age
- Finding count

Selection opens a details view with contract, implementation graph, evidence, test history, and governance actions.

### 13.3 Finding Center

The default is global and cross-domain. A Finding displays all subjects together, evidence, deterministic or AI reasoning, confidence, history, and actions.

Allowed actions are confirm, reject candidate, rerun analysis, grant/revoke bounded waiver, create Proposal, and generate repair prompt.

### 13.4 Change and Review

The UI shows structured contract diffs, base Snapshot, code revision, evidence, risk, approval matrix, and stale status. Approval controls are disabled when hashes change.

### 13.5 Test and Health

The global matrix uses the 11 domains as rows and evidence levels as columns. It displays pass, fail, unverified, and stale counts with text and icons, not color alone.

### 13.6 Release Gate

Every evaluation pins:

- `code_revision`
- `catalog_release_id`
- `snapshot_gid`
- `test_run_gid`

The only conclusions are `pass`, `fail`, and `expired`. A pass creates an immutable report GID and hash.

### 13.7 Audit

Audit is searchable by entity GID, actor GID and type, Capability, event, request GID, and time. It is exportable but not editable or deletable.

## 14. Test and Production Isolation

### 14.1 Dual Catalog

Test loads:

```text
Product Catalog + Test Governance Catalog Extension
```

Production loads:

```text
Product Catalog only
```

The two Catalogs are checked for ID, Major, owner, Provider, and schema-hash collisions before union. Product and governance counts remain separate.

### 14.2 Test-Only Packages

Suggested locations:

```text
backend/capability_governance_test/
dist/web/admin/capability-governance/
backend/db/migrations/test_governance/
docs/governance/test-extension/
```

### 14.3 Production Allowlist Build

Production uses an explicit artifact allowlist. The build fails if it contains:

- governance Python package
- governance UI assets
- governance migrations
- governance Catalog extension
- governance routes
- governance Provider registration
- test fixtures or temporary identities

A runtime feature flag alone is not sufficient isolation.

Production retains only the Product Catalog, Provider and Migration attestation manifests, a signed release-gate report, and a minimal startup validator.

## 15. Security

### 15.1 Database Account

The test center may reuse the existing Base runtime account. It receives exact table-level SELECT/INSERT/UPDATE grants for governance tables, read access to required Catalog metadata, and no DDL, system-table access, arbitrary business-domain table access, or ordinary hard-delete permission.

DDL credentials are used only during migration.

### 15.2 Scanner

The scanner reads whitelisted repository paths only. It cannot accept arbitrary paths, execute shell commands, execute scanned source, read environment files, inspect browser/DBeaver/SSH state, or access user directories.

### 15.3 AI and Prompt Redaction

AI receives structured, minimal, authorized data. Database URLs, credentials, tokens, cookies, business payloads, complete logs, environment variables, and unauthorized files are excluded.

Generated prompts are redacted and evidence-bound. Raw AI requests are not persisted; only model reference, hashes, and redacted summaries are retained.

### 15.4 Idempotency and Concurrency

- Scan, Analysis, Test, Proposal, Review, Waiver, and release actions use unique idempotency keys.
- A code revision and Catalog combination has one active effective Snapshot.
- Finding fingerprints deduplicate repeated detection.
- Analysis workers use leases.
- Mutable governance actions require current `row_version`.
- Agent retry must not duplicate writes.

## 16. Failure and Degradation

| Failure | Required behavior |
|---|---|
| Governance DB unavailable | UI unavailable/degraded; business Capabilities continue |
| Scanner unavailable | Snapshot becomes stale; release blocked |
| AI unavailable | deterministic analysis continues; absence is not a pass |
| Test runner unavailable | required state is unverified; release blocked where required |
| Catalog/code mismatch | blocking Finding |
| Provider unavailable | affected Capability broken |
| Report missing or expired | production release fails |
| Governance UI unavailable | query Capability may remain available; approval cannot be bypassed |

Governance failure must not take down normal business execution, but release checks fail closed.

## 17. Retention

- Capability Entry and Version: permanent
- Proposal, Review, Waiver, Finding state history, and release reports: permanent
- Audit Event: long-term retention
- Snapshot: 180 days plus all release-referenced snapshots
- Test details: 180 days
- Health rollups: one year
- Raw AI request: not stored
- AI result: redacted summary and hashes only

Cleanup removes only expired technical detail. It never deletes identity, review, audit, or release evidence.

## 18. Self-Governance and Bootstrap

Governance Capabilities are themselves described and scanned in the test Governance Catalog extension. They are not privileged exceptions.

To prevent circular self-approval:

- governance Capabilities may scan themselves but cannot approve their own changes
- AI cannot confirm its own findings
- release-gate authority is a separate deterministic validator
- governance DB outage produces degraded/unavailable state, never an implicit pass
- governance Capability changes require Base ownership review and platform release review
- every analysis and approval is pinned to immutable hashes and Snapshot GID

## 19. Risks and Controls

### 19.1 Pairwise Analysis Explosion

Use deterministic candidate generation and bounded AI review instead of full pairwise AI comparison.

### 19.2 AI Model Drift

Pin model reference and hashes; keep AI advisory; never use it as the sole release proof.

### 19.3 Waiver Debt

Require owner, reason, scope, expiry, reminder, and automatic expiration. No permanent waiver.

### 19.4 Authority Inversion

Enforce one-way projection from Descriptor/Catalog to database. Database/UI/AI never rewrite the contract.

### 19.5 Stale Decisions

Hash-bound proposals, reviews, waivers, tests, and reports expire when dependencies change.

### 19.6 Catalog Contamination

Keep Product Catalog and Governance Extension distinct; union only in test with collision checks.

### 19.7 Sensitive Evidence Leakage

Apply structured collection, field-level redaction, size bounds, authorization, and audit before data reaches UI, agents, exports, or AI.

## 20. Implementation Phases

### Phase 0: Baseline and Identity

- correct the official 11-domain presentation
- pin the current Product Catalog baseline
- configure snowflake machine IDs
- import Entry and Version identities
- prove repeat scans map the same business keys to the same GIDs

### Phase 1: Database and Projection

- create test governance migrations
- build Scan Run and immutable Snapshot persistence
- project Entry, Version, and Snapshot entries
- enforce one-way authority

### Phase 2: Deterministic Scan and Graph

- scan Descriptor, Provider, API, Port, Repository, Migration, exposure, and tests
- persist implementation nodes, bindings, and relations
- detect missing implementation, drift, transaction-provider, persistence, permission, and evidence problems

### Phase 3: Findings and Global Analysis

- implement multi-subject cross-domain Findings
- implement stable fingerprints
- implement duplicate, conflict, gap, drift, compatibility, atomicity, and lifecycle-pair rules
- keep AI disabled initially

### Phase 4: Governance Capabilities and Core UI

- create the test Governance Catalog extension
- implement agent read and analysis interfaces
- implement overview, inventory, Finding center, and details
- verify permission separation

### Phase 5: Change, Review, Test, and Release Gate

- implement Proposal, Review, Waiver, Evidence, Test, Health, Gate, and Audit flows
- perform full OceanBase release acceptance

### Phase 6: AI Advisory

- implement candidate-set review
- implement Candidate Finding creation
- implement redacted repair-prompt generation
- verify human/deterministic confirmation and audit

### Phase 7: Production Exclusion Rehearsal

- build the production allowlist artifact
- prove absence of all governance test components
- validate signed release attestation
- rehearse test-to-production promotion

## 21. Acceptance Criteria

The design is successfully implemented only when:

1. Every product Capability Major has a stable logical and version GID.
2. Repeated unchanged scans produce the same effective identities and snapshot hash.
3. The implementation graph links contracts to Provider, Port, Repository, table/migration, exposure, and tests where applicable.
4. Cross-domain Findings support multiple Capability subjects and evidence.
5. Contract-only evidence cannot produce healthy state.
6. Strong writes without a transactional participant are detected before release.
7. Agents can search, inspect, analyze, query Findings, and generate redacted prompts through governed Capabilities only.
8. Agents cannot approve, edit, delete, waive permanently, or bypass review.
9. A changed code or Catalog hash invalidates stale approvals, tests, waivers, and release reports.
10. The UI contains no contract edit or delete operation.
11. Full real writes and OceanBase E2E run before formal release, not as periodic health writes.
12. Governance outage does not take down business execution, while release checks fail closed.
13. Production artifacts contain no governance UI, scanner, AI analyzer, migrations, Provider, routes, fixtures, or Catalog extension.
14. Product and Governance Catalog counts remain distinct and collision-free.
15. All governance mutations are idempotent, optimistic-lock protected, and audited by snowflake GID.

## 22. Deferred Work

The following require separate future designs:

- Application Use Case and business workflow model
- concrete UI/plugin/agent-workflow consumer registry
- business material, knowledge, and rule dependency graph
- capability-combination emergence and automation suggestions
- the proposed loose-programming language and its IR/compiler

This Governance Center intentionally stops at reliable Capability self-governance.
