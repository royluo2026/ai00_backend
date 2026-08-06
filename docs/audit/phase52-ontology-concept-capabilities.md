# Phase 52 — Ontology concept and mapping Capabilities

Date: 2026-08-06
Branch: `codex/capability-wave-a`

## Implemented interfaces

- `ontology.concept.resolve`
- `ontology.concept.get`
- `ontology.mapping.assess`

All reads resolve either an explicitly requested immutable release or the active release and return its GID and SHA-256 evidence. `concept.get.view` is constrained to `summary|schema`; no arbitrary graph path, raw table, SPARQL, or GraphQL input is exposed.

## Resolution policy

Resolution is deterministic and honest:

1. stable object GID;
2. external ID;
3. exact canonical name, localized label, or alias;
4. fuzzy candidates only.

Multiple exact matches return `ambiguous`. Fuzzy similarity never silently becomes a resolved identity.

## Mapping assessment policy

`ontology.mapping.assess` is a read-only assessment and never persists a mapping. It checks stable identities, object kinds, deprecation, property type/cardinality, relation roles, existing mapping uniqueness, and mapping cycles. Deterministic contradictions return `incompatible`; deterministic identity/contract matches can return `compatible`; insufficient semantic evidence returns `expert_review_required`. Names alone can never establish compatibility.

## Repository boundary

Release/object reads use only `workmanship_base_ontology_*` immutable storage. No Capability exposes legacy Craft ontology tables or arbitrary query language.

## Verification

Task 8 concept, mapping, immutable repository, Craft boundary, Capability kernel, and OceanBase tests passed: `26 passed in 1.14s`.

No database connection, deployment, push, or remote mutation was performed.
