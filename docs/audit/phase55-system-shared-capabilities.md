# Phase 55 — Shared system composition Capabilities

Date: 2026-08-06
Branch: `codex/capability-wave-a`

## Implemented interfaces

- `system.search`
- `system.activity.search`
- `system.job.get`
- `system.job.cancel`
- `identity.principal.search`
- `system.lineage.get`
- `system.change_impact.preview`
- `semantic.context.get`
- `base.project.search`

## Boundary model

Shared Capabilities contain no domain SQL. They compose registered providers, and provider results cross the boundary only as bounded stable references or typed summaries. Search strips ungoverned provider fields. Project search remains a Base composition Capability but obtains project refs from the owning domain provider.

Semantic context only accepts named views `object_neighborhood|decision_context|knowledge_links`, depth 1–3, and at most 100 nodes. It exposes no arbitrary path, SPARQL, GraphQL, or raw table input.

Lineage reports immutable events, breaks, and completeness. Change impact accepts only server-issued `preview://` or `diff://` refs and preserves unknown impacts. Job cancellation is a cancellation request and always reports `rolled_back=false`.

## Verification

Shared-system, domain governance, evidence separation, Capability kernel, and OceanBase tests passed: `22 passed in 1.24s`.

No database connection, deployment, push, or remote mutation was performed.
