# Capability V2 Domain Rearchitecture Program Roadmap

**Design:** docs/superpowers/specs/2026-08-11-capability-v2-domain-rearchitecture-design.md

## Purpose

This roadmap decomposes the approved multi-domain specification into independently executable implementation plans. It is an ordering and dependency document, not a substitute for the task-level plans. Every plan must leave the repository in a working, reviewable state and must use inline execution; the repository owner explicitly prohibited subagents.

## Plan Sequence

| Order | Plan | Deliverable | Depends on |
|---|---|---|---|
| 01 | Domain foundation | Manifest-driven Provider bootstrap, search exports, event subscriptions, domain DB/migration contracts, internal Capability client, event contracts and governance gates | Approved design |
| 02 | Base platform | Tenant, Approval including external cancellation, Notification, Workspace, manifest-driven System providers, Plugin Platform and removal of pseudo-capabilities | 01 |
| 03 | Project Management | Independent Project, Member, Task, Issue, List, Follow, Collaboration and Share Link domain | 01, 02 |
| 04 | Factory | Independent physical structure, resource catalog and physical asset domain | 01, 02 |
| 05 | Knowledge | Space, Document, immutable Revision, ACL, favorite, pin and Knowledge Proposal domain | 01, 02 |
| 06 | Ontology | Concept reads, Proposal/Review and Release/Activation domain | 01, 02 |
| 07 | Craft PBOM | PBOM draft/version/import/part capabilities, native V2 Provider, CraftPbomRevisionAdapter and complete removal of eBOM naming | 03, 05, 06 |
| 08 | Craft BOP | Six-level BOP plan model, typed draft changes, publish, execution plan, PBOM/Factory bindings and CraftBopRevisionAdapter | 04, 06, 07 |
| 09 | Craft GBOP and Rules | GBOP draft/release lifecycle, rule releases, validation and waivers | 05, 06, 08 |
| 10 | Digital Model | Model identity, immutable Version and trusted component extraction | 01, 02, 03 |
| 11 | Simulation | Immutable inputs, reproducible Environment, separate Run/Operation and Result comparison | 08, 10 |
| 12 | Integration | Core Connector/mapping/sync orchestration after 01-02, plus independently enabled target-domain Adapters after each target Provider | 01, 02; each Adapter also depends on its target Provider |
| 13 | Local Runtime | Device enrollment/revocation, local Operation control and explicit VisMockup actions | 01, 02, 10 |
| 14 | Agent | Definition, Flow, Skill, Session, Run, Memory, Trace, pending-Approval cancellation and generated Catalog tools | 02-13 |
| 15 | Consumer cutover and deletion | Web/REST/Plugin/Agent/MCP parity, removal of compatibility paths, old tables and governance baselines | 02-14 |

## Program Rules

- Domain-local development may run only on disjoint files. Domain development commits must not include central governance or frozen generated artifacts.
- Exactly one designated integrator owns finalization on the latest integration HEAD. Finalization regenerates and commits central files serially; the next plan cannot finalize until the prior central freeze commit lands.
- Before freezing, capture integration HEAD and official_domains.json sha256 and pass both as expected-head and expected-manifest-sha256. A stale value or domain patch touching central files fails closed and returns to the queue.
- Do not begin a dependent domain until the Provider contracts it consumes are stable.
- Do not dual-write old and new business tables.
- A compatibility REST adapter may exist only while its consumer is being moved and must invoke the Gateway.
- Each domain receives its own database, runtime credential, DDL credential, migration ledger, artifact and test command.
- Each plan ends with Catalog regeneration, strict registry validation, boundary validation and its domain tests.
- The next detailed plan is Plan 01, domain foundation.

## Required Contracts for Later Detailed Plans

- Plan 02 builds `system.search` targets exclusively from `DomainManifest.search_export`; it does not maintain a mutable handwritten Provider registry. Base Approval persists subject_ref, supports pending search by subject_ref, and makes per-approval cancel idempotent with expected pending state.
- Plans 03-06 may develop domain-local code independently, but their detailed plans split domain commits from the designated integrator's central freeze commit.
- Plan 07 removes eBOM from filenames, routes, code symbols, tests, governance records, generated documents and table names; it converts PBOM CapabilitySpec registrations to native V2 Descriptor/Provider and implements CraftPbomRevisionAdapter.
- Plan 08 converts BOP CapabilitySpec registrations to native V2 Descriptor/Provider, implements the §14.6 PreviewRef contract, records BOP CommitRef through CraftBopRevisionAdapter and links the exact PBOM CommitRef. Factory mutable references go to the Base impact projection through events, not fake commits.
- Plan 09 adds GBOP/Rule native V2 Providers and GBOP lineage edges without changing already published BOP or PBOM commits.
- Plan 12 first delivers Integration Core after Plans 01-02. A Knowledge sync Adapter can ship after Plan 05; every later Adapter declares and waits for its own target Provider rather than blocking Core on all domains.
- Plan 14 freezes legacy handwritten Agent tools until removal, replaces them with Catalog-generated tools, and cancels all pending ApprovalRequests for a Run before completing `system.job.cancel`.
- Plan 15 removes the V1 adapter, legacy Agent token forwarding, compatibility routes, old PBOM/eBOM surfaces and reclassified boundary baseline only after all consumers pass parity tests.

## Completion Checkpoints

After Plans 01, 02, 04, 08, 14 and 15, run a full architecture checkpoint. A checkpoint verifies that implementation has not introduced catch-all capabilities, consumer-specific business services, cross-domain SQL, implicit Tenant fallback or a second Catalog source of truth.
