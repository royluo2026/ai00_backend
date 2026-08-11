# Capability V2 Domain Rearchitecture Program Roadmap

**Design:** docs/superpowers/specs/2026-08-11-capability-v2-domain-rearchitecture-design.md

## Purpose

This roadmap decomposes the approved multi-domain specification into independently executable implementation plans. It is an ordering and dependency document, not a substitute for the task-level plans. Every plan must leave the repository in a working, reviewable state and must use inline execution; the repository owner explicitly prohibited subagents.

## Plan Sequence

| Order | Plan | Deliverable | Depends on |
|---|---|---|---|
| 01 | Domain foundation | Manifest-driven Provider bootstrap, domain DB/migration contracts, internal Capability client, event contracts, governance gates | Approved design |
| 02 | Base platform | Tenant, Approval, Notification, Workspace, System providers, Plugin Platform and removal of pseudo-capabilities | 01 |
| 03 | Project Management | Independent Project, Member, Task, Issue, List, Follow, Collaboration and Share Link domain | 01, 02 |
| 04 | Factory | Independent physical structure, resource catalog and physical asset domain | 01, 02 |
| 05 | Knowledge | Space, Document, immutable Revision, ACL, favorite, pin and Knowledge Proposal domain | 01, 02 |
| 06 | Ontology | Concept reads, Proposal/Review and Release/Activation domain | 01, 02 |
| 07 | Craft PBOM | PBOM draft/version/import/part capabilities and removal of eBOM naming | 03, 05, 06 |
| 08 | Craft BOP | Six-level BOP plan model, typed draft changes, publish, execution plan and PBOM/Factory bindings | 04, 06, 07 |
| 09 | Craft GBOP and Rules | GBOP draft/release lifecycle, rule releases, validation and waivers | 05, 06, 08 |
| 10 | Digital Model | Model identity, immutable Version and trusted component extraction | 01, 02, 03 |
| 11 | Simulation | Immutable inputs, reproducible Environment, separate Run/Operation and Result comparison | 08, 10 |
| 12 | Integration | Connector, credentials, schema discovery, mapping and governed sync orchestration | 01, 02 and target domain Providers |
| 13 | Local Runtime | Device enrollment/revocation, local Operation control and explicit VisMockup actions | 01, 02, 10 |
| 14 | Agent | Definition, Flow, Skill, Session, Run, Memory, Trace and generated Catalog tools | 02-13 |
| 15 | Consumer cutover and deletion | Web/REST/Plugin/Agent/MCP parity, removal of compatibility paths, old tables and governance baselines | 02-14 |

## Program Rules

- Do not run two plans that write the same files concurrently.
- Do not begin a dependent domain until the Provider contracts it consumes are stable.
- Do not dual-write old and new business tables.
- A compatibility REST adapter may exist only while its consumer is being moved and must invoke the Gateway.
- Each domain receives its own database, runtime credential, DDL credential, migration ledger, artifact and test command.
- Each plan ends with Catalog regeneration, strict registry validation, boundary validation and its domain tests.
- The next detailed plan is Plan 01, domain foundation.

## Completion Checkpoints

After Plans 01, 02, 04, 08, 14 and 15, run a full architecture checkpoint. A checkpoint verifies that implementation has not introduced catch-all capabilities, consumer-specific business services, cross-domain SQL, implicit Tenant fallback or a second Catalog source of truth.
