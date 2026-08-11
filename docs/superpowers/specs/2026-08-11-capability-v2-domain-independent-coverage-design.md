# Capability V2 Domain-Independent Coverage Design

**Date:** 2026-08-11

**Status:** Proposed for implementation planning

## 1. Purpose

Close every unresolved stable User Function Registry record without turning transport routes into one-for-one Capabilities, while making every first-class domain independently maintainable and releasable at both code and database boundaries.

Completion means all stable records have a reviewed disposition, every mapped Capability is real and executable through `CapabilityGatewayService`, consumer exposure is explicit, and no domain depends on another domain's Router, Repository, ORM, migration implementation, or privately owned tables.

## 2. Current State

- The Registry contains 822 discovered functions, including 753 stable functions.
- 119 stable records map to a Capability and 6 have a valid reviewed exclusion.
- 628 stable records remain unresolved: Craft 342, Base Platform 146, Agent 67, Ontology 27, Project Management 22, Knowledge 21, and Local Integration 3.
- The frozen Catalog contains 87 stable Capabilities. Their contract and acceptance coverage is green, but that does not prove product-function coverage.
- The current domain coverage test filters out records whose `target_capability` is null. It therefore proves only that existing mappings resolve, not that every stable function has a disposition.
- The dependency baseline contains seven historical module-level cross-domain implementation imports.
- The deeper domain-boundary baseline contains 292 historical violations: 262 cross-domain SQL accesses and 30 internal implementation imports. The table inventory currently assigns 162 tables to runtime domains.
- Project Management still owns source files physically hosted below `plugins/craft`, and its migrations still use Craft-prefixed filenames. That is ownership metadata, not independent maintenance.

## 3. Design Principles

1. A route, screen helper, Agent tool, or runtime endpoint is evidence of a function, not automatically a Capability.
2. Capabilities model stable business outcomes. Multiple transports and consumers may map to one Capability.
3. Web, REST compatibility, Plugin, Agent, MCP, and Local Runtime share one Capability ID, Descriptor, Provider, Gateway pipeline, and version history for the same business outcome. No consumer-specific business implementation is allowed.
4. Existing Capabilities are reused before proposing new ones.
5. A new Capability is permitted only when no existing business outcome covers the function without weakening schemas, authorization, resource selection, or audit meaning.
6. Broad catch-all Capabilities and union-schema command buses are prohibited.
7. Every exclusion names the concrete reason, source evidence, reviewer, owner, and review date. Generic labels such as `internal endpoint` are insufficient.
8. Domain independence is part of Capability completion, not a later refactor.

## 4. Domain Independence Contract

The first-class domains are Base Platform, Agent, Craft, Digital Model, Project Management, Simulation, Ontology, Knowledge, and Local Integration.

Each domain owns and versions:

- its application services and public Application Ports;
- its Capability descriptors and Provider implementation;
- its tables, repositories, migrations, seed data, and rollback procedure;
- its contract, provider, migration, and domain tests;
- its generated Capability documentation;
- its artifact name, version, schema hash, and CODEOWNERS entries.

A domain may consume another domain only through a versioned public port, `CapabilityGatewayService`, `ResourceRef`, `ArtifactRef`, `OperationRef`, or a versioned domain event. It may not import another domain's Router, Repository, ORM model, migration, concrete service, or database connection helper.

Every table and migration has exactly one owning domain. Shared physical database infrastructure is allowed, but schema ownership and migration release units remain independent. A domain cannot write another domain's tables. Cross-domain workflows use ports and outbox-backed events, not multi-domain table transactions.

The current exceptions in `docs/governance/domain-dependency-baseline.json` and `backend/governance/boundary_baseline.json` are debt to remove. Both baselines must reach zero; neither can be retained as the completion state.

## 5. Five Coupled Inventories

The audit produces five version-controlled views generated from one reviewed source document.

### 5.1 Function Disposition Inventory

One row per stable discovered function:

- `function_id`
- `source_paths`
- `owning_domain`
- `business_outcome`
- `resolution`: `existing_capability`, `new_capability`, or `excluded`
- `target_capability`
- `exclusion_classification`
- `exclusion_reason`
- `evidence`
- `reviewer`
- `reviewed_at`
- `migration_status`

Every stable row must have exactly one resolution. `unreviewed` and `candidate` are forbidden at release.

### 5.2 Capability Candidate Inventory

One row per proposed new Capability:

- stable Capability ID and owner domain;
- business outcome and explicit non-goals;
- source function IDs consolidated into it;
- input, output, error, resource, data, concurrency, idempotency, approval, Evidence, Outcome, and audit contracts;
- Application Port and Provider artifact;
- owned tables and migrations;
- required tests and documentation;
- lifecycle state and replacement relationship, if any.

The inventory must show why each candidate cannot map to an existing Capability. Candidate approval occurs before implementation.

### 5.3 Consumer Exposure Inventory

For every mapped Capability, record independent access decisions for Web, REST compatibility, Plugin, Agent, MCP, and Local Runtime. These decisions select consumers of one shared Capability; they never create parallel Web, Plugin, or Agent implementations.

- Web and REST compatibility may be broader than extension exposure, but their adapters contain no business logic and invoke the same Gateway and Provider as every other consumer.
- Plugin exposure requires a stable extension use case and mount-scoped permissions.
- Agent and MCP exposure require bounded semantics, safe automation level, deterministic schemas, resource scoping, and data projection.
- Internal, operational, webhook, transport, and UI-transient functions are not made Agent tools merely to resolve Registry rows.
- A stable user-visible business outcome used only by Web still belongs to the shared Catalog. A transient UI composition or transport helper is excluded instead of becoming a Web-only Capability.

### 5.4 Code Ownership and Extraction Inventory

For every domain, list:

- current and target code paths;
- public ports and allowed dependencies;
- Provider entry points;
- files physically located in another domain;
- direct implementation imports to remove;
- artifact build and independent test command;
- CODEOWNERS coverage.

Project Management code currently hosted below `plugins/craft` must move into `plugins/project_management`; compatibility adapters may remain temporarily but cannot own business logic.

### 5.5 Database Ownership and Migration Inventory

For every table and migration, list:

- owning domain;
- repository and write paths;
- readers in other domains;
- current migration file and target domain migration stream;
- schema version and rollback boundary;
- cross-domain writes or joins requiring replacement;
- data backfill and cutover evidence.

Project Management migrations currently named as Craft migrations must be replaced by a Project Management-owned migration stream. Applied historical migrations remain immutable; corrective ownership migrations and compatibility views/adapters are added rather than rewriting deployed history.

## 6. Audit and Migration Flow

Work proceeds in dependency order:

1. Base Platform establishes shared ports and removes domain-specific behavior from the platform layer.
2. Project Management is physically extracted from Craft, including code, repositories, tables, and migration ownership.
3. Knowledge and Ontology remove direct Base implementation dependencies and publish their own repositories and storage adapters.
4. Agent tools are mapped to domain Capabilities; Agent retains orchestration, run, memory, and delegation behavior only.
5. Craft is audited after Project Management and Ontology extraction so its candidate count is not inflated by misplaced behavior.
6. Local Integration retains device and local-operation protocols only.
7. Digital Model and Simulation are rechecked for coverage and independence even when no unresolved Registry rows are currently reported.

For each domain:

1. classify every unresolved function;
2. map to existing Capabilities where semantics match;
3. record evidence-backed exclusions;
4. present the remaining new Capability candidates for review;
5. implement approved candidates as complete vertical slices;
6. migrate consumers through the Gateway;
7. remove cross-domain implementation and table dependencies;
8. run domain-local and global gates before moving to the next domain.

## 7. Count Control

There is no target quota that can override correct domain semantics. The expected result is the existing 87 stable Capabilities plus tens of reviewed additions, not hundreds of route-shaped additions.

The audit must report, per domain:

- functions mapped to existing Capabilities;
- reviewed exclusions;
- proposed new Capabilities;
- average and maximum functions consolidated per Capability;
- Capabilities exposed to Plugin;
- Capabilities exposed to Agent or MCP.

If the proposed stable Catalog exceeds 170 Capabilities, or any domain proposes more than 40 additions, implementation pauses for architecture review. This is a review threshold, not permission to merge unrelated outcomes into generic commands.

## 8. Validation Gates

Release requires all of the following:

- stable Registry unresolved count is zero;
- every mapped target exists in the frozen Catalog;
- every target owner matches the reviewed function domain;
- every stable Capability has a loadable Provider and complete mandatory acceptance cases;
- every consumer uses `CapabilityGatewayService.invoke()` or a compatibility adapter that invokes it;
- the same business outcome has one Capability and one Provider implementation across Web, REST, Plugin, Agent, MCP, and Local Runtime; consumer-specific duplicate business services are zero;
- consumer exposure matches the reviewed matrix;
- every owned table and migration has exactly one domain owner;
- cross-domain table writes are zero;
- cross-domain Router, Repository, ORM, migration, concrete service, and database-helper imports are zero;
- `docs/governance/domain-dependency-baseline.json` contains zero violations;
- `backend/governance/boundary_baseline.json` contains zero cross-domain SQL and internal-import violations;
- each domain builds, migrates, tests, publishes, and rolls back without requiring another domain's private implementation;
- generated Registry, Catalog, SDK, documentation, CODEOWNERS, and acceptance artifacts have no drift;
- offline strict acceptance passes with no mandatory skips;
- Release Candidate remains blocked until isolated OceanBase, OIS, JWT/OAuth, Local Runtime, and Windows .NET evidence passes.

## 9. Error Handling and Safety

- Ambiguous ownership blocks the row; it is never silently assigned to Base or Craft.
- An exclusion without specific evidence fails strict validation.
- A mapping to a missing, deprecated-without-replacement, or owner-mismatched Capability fails validation.
- A Capability requiring another domain's private implementation remains experimental and cannot resolve a stable function for release.
- Historical migrations are never edited after deployment; ownership corrections use new migrations.
- No production database, production OIS, real device, or release channel is used during this work.

## 10. Deliverables

1. A reviewed cross-domain audit document containing all five inventories.
2. Registry schema and validators enforcing reviewed dispositions and ownership evidence.
3. Exact per-domain implementation plans generated only after candidate review.
4. Independently owned code, Provider, database migration stream, tests, docs, artifact, and rollback boundary for each domain.
5. A final acceptance report proving both Capability quality coverage and product-function governance coverage.
