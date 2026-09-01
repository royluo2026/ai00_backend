# Capability Business Governance V2.5 Design

**Status:** Approved design, pending implementation plan  
**Date:** 2026-09-01  
**Scope:** Business purpose, business-rule evidence, relationship analysis, human approval, audit, and release gating  
**Approval role for phase 1:** `super_admin`  
**Migration rule:** Existing stable Capabilities remain testable and are reviewed incrementally

## 1. Goal

Extend the existing Capability governance stack so that a stable Capability proves not only that its technical invocation path is governed, but also:

1. why the Capability exists;
2. which business result it promises;
3. which business rules protect that result;
4. where those rules are enforced and tested;
5. whether the Capability duplicates, covers, overlaps, or conflicts with another Capability;
6. which exact definition a human approved; and
7. whether the approved definition is the definition being released and run.

This design must not stop current testing while the existing Catalog is migrated. New or materially changed Capabilities follow V2.5 immediately; unchanged legacy Capabilities enter an explicit review backlog.

## 2. Non-goals

- Do not make the Gateway a universal business-rule interpreter.
- Do not create a central dynamic business-rule engine.
- Do not create a second approval subsystem beside the existing Base approval and Governance Center review facilities.
- Do not let AI approve, reject, merge, deprecate, or assign blocking severity by itself.
- Do not require 479 bespoke approval workflows or 479 bespoke test files.
- Do not treat generated prose, a test path, or a successful smoke test as proof of a business rule.

## 3. Governing Decisions

1. The authoritative business rule remains in the owning domain's Provider or domain policy. Static schema and database constraints may provide additional defenses.
2. The Gateway continues to enforce cross-cutting controls such as identity, authorization, confirmation, schema, idempotency, reliability, transaction, evidence, and output validation.
3. The Governance Center stores immutable projections, analysis evidence, review history, decisions, and effectiveness evidence. It does not overwrite Descriptor authority.
4. Phase 1 human approval is performed by `super_admin` only. The record shape keeps approver role and subject identity so domain or multi-party approval can be added later without data migration.
5. Deterministic analysis supplies reproducible evidence. AI supplies advisory semantic interpretation only.
6. Approval binds an exact semantic definition hash. A material semantic change expires approval automatically.
7. Runtime status and governance status are independent, so legacy review does not misrepresent runtime availability.

## 4. Capability Model

### 4.1 Compatibility-first contract extension

`business_effect` remains a string in phase 1 to avoid breaking existing descriptors and generated consumers. V2.5 produces the following joined governance view:

```yaml
business_effect: Modify the height recorded in a person's profile
business_acceptance_criteria:
  - A successful read returns the submitted normalized height
business_invariants:
  - rule_id: person.height.valid_range
    version: 1
    statement: A person's normalized height must be between 0.3 m and 2.5 m
    applies_when: A person height is created or changed
    enforcement_ref: person/provider.py:validate_height
    error_code: invalid_person_height
    test_refs:
      - tests/test_person_height.py::test_height_range
no_business_invariant_reason: null
governance_status: approved
review_ref: review_opaque_gid
definition_hash: sha256:...
```

The author-controlled Descriptor contains `business_effect`, `business_acceptance_criteria`, `business_invariants`, and `no_business_invariant_reason`. The generated Catalog adds `definition_hash`. The Governance Center joins `governance_status` and `review_ref` from immutable review records. Dynamic approval state is not written back into Descriptor authority, which avoids an approval-to-contract mutation cycle.

`business_invariants` and `no_business_invariant_reason` are mutually exclusive. One of them must be present for V2.5 approval. A no-rule reason is reviewed like a rule and is not an automatic waiver.

### 4.2 Business purpose

The business purpose consists of:

- a non-generated `business_effect`;
- one or more observable acceptance criteria;
- an owning domain; and
- examples of successful and rejected outcomes suitable for review.

`description`, `title`, `Execute the governed ... outcome`, and `Business outcome: <description>` are candidate text only. They cannot satisfy approval without an explicit human decision.

### 4.3 Business invariant

Each invariant has a stable `rule_id` within the Capability major, its own version, a human-readable statement, applicability, enforcement reference, stable error code, and rule-specific test references.

Shared rules may be defined once and referenced by multiple Capabilities. Each Capability still records that the rule applies to its own semantic definition.

### 4.4 Identity and hashes

The review subject hash covers:

```text
Capability ID + major version
+ business effect + acceptance criteria
+ business invariants or approved no-rule reason
+ critical input/output schema semantics
+ Provider binding
+ declared data-write scope
```

Formatting-only changes do not expire the semantic approval. A change to purpose, invariant meaning, Provider authority, critical schema behavior, or write scope does.

## 5. Lifecycle and Migration

### 5.1 Independent statuses

Existing lifecycle status is retained as runtime status. V2.5 adds governance status:

```text
runtime_status: draft | stable | deprecated | retired
governance_status:
  legacy_pending_review | machine_reviewed | pending_human_review |
  approved | rejected | review_expired
```

New Capabilities progress through machine review, human review, approval, and only then stable publication. An existing stable Capability may remain runtime-stable while its governance status is `legacy_pending_review`.

### 5.2 Material-change rule

New and materially changed Capabilities must reach human approval before stable publication. Material changes include:

- business purpose or acceptance criteria;
- invariant applicability or result;
- critical input/output semantics;
- Provider authority;
- declared write scope; or
- a breaking public contract.

Internal refactoring, defect repair that restores the already approved behavior, and test additions do not require a new semantic approval, but must regenerate implementation and execution evidence.

### 5.3 Legacy migration priority

Legacy review is ordered by risk rather than Catalog order:

1. write Capabilities without proven business rules;
2. delete, approve, authorize, publish, and state-transition operations;
3. Capabilities sharing writes to the same critical data;
4. existing duplicate, coverage, overlap, or conflict candidates;
5. remaining writes; and
6. reads.

The test environment does not block solely on `legacy_pending_review`. Production enforcement may tighten by risk class and declared migration deadline.

## 6. Governance Center Architecture

### 6.1 Reuse existing infrastructure

The Governance Center remains the projection and evidence control plane. Existing Base approval provides the authorization and decision workflow primitive. Governance Center records carry the business-specific subject, evidence, relation candidates, immutable decision, and definition hash.

The minimum new first-class records are:

- `BusinessPurposeRecord`
- `BusinessRuleRecord`
- `CapabilityRelationCandidate`
- `CapabilityReviewRecord`
- `RuleEffectivenessRecord`

These records are normalized governance projections. Descriptor and signed Catalog releases remain contract authorities.

### 6.2 Scanner correction

The scanner must read authoritative `business_effect` and invariant data. It must not silently substitute `description` or `title` as approved business purpose. Generated or templated values produce structured findings.

For each Capability the scanner builds a business fingerprint from:

- domain;
- business object;
- action;
- business purpose;
- input and output semantics;
- read and write scope;
- invariants;
- Provider;
- public entries and consumers; and
- Capability graph dependencies.

The scan persists both raw evidence and normalized fingerprint fields so later analysis is reproducible.

### 6.3 Relationship analysis

Four analyzers operate on a narrowed candidate set:

- `DuplicateAnalyzer`
- `CoverageAnalyzer`
- `ConflictAnalyzer`
- `BoundaryAnalyzer`

Candidate narrowing uses deterministic evidence such as shared objects, tables, fields, routes, consumers, Provider bindings, graph edges, actions, and schema containment. AI receives only the narrowed candidates and produces an explanation with cited fields and uncertainty.

Relationship meanings are:

- **duplicate:** business object, action, purpose, contract, and rules are materially the same;
- **coverage:** one Capability's contract or effect contains another's;
- **conflict:** the same object under the same applicable conditions has incompatible outcomes or rules; and
- **boundary overlap:** part of the responsibility is shared, but purpose, scenario, or ownership may legitimately differ.

Similarity scores rank review candidates. They do not create blockers by themselves.

### 6.4 Human review

The Governance Center review surface presents:

1. plain-language purpose and success/failure examples;
2. invariants, applicability, enforcement location, and error behavior;
3. rule-specific test results;
4. public entries, consumers, Provider, and data-write scope;
5. duplicate, coverage, conflict, and boundary candidates with a field-level comparison;
6. deterministic evidence separated from AI advisory text; and
7. the exact semantic definition hash.

The `super_admin` can approve, reject, request changes, confirm a relationship, or mark an advisory as a false positive. Every decision records actor, role, decision, rationale, timestamp, subject version, and definition hash. A review cannot mutate Descriptor or Catalog content.

## 7. Seven-layer Audit Model

Every Capability receives an independent result for:

| Layer | Subject | Question |
|---|---|---|
| A | Business purpose | Why does the Capability exist, and what observable result is promised? |
| B | Atomic boundary | Does it carry one independently governed business responsibility? |
| C | Business rules | Which conditions must never be violated, or why are none applicable? |
| D | Enforcement mapping | Where is each rule actually enforced, and can it be bypassed? |
| E | Test evidence | Do executable tests prove accepted, boundary, and rejected outcomes? |
| F | Relationship governance | Is the Capability duplicated, covered, overlapping, or conflicting? |
| G | Approval and runtime | Is the approved definition the released and running definition? |

Technical governance remains mandatory in parallel. It cannot substitute for these layers.

### 7.1 Maturity levels

```text
L0 unregistered
L1 registered but generated, incomplete, or unconfirmed
L2 explicit purpose and rule draft
L3 enforcement mapping and rule-specific evidence
L4 machine reviewed and relationship candidates dispositioned
L5 human approved and release-gate verified
L6 runtime effectiveness verified and periodically reviewed
```

New or materially changed Capabilities must reach L5. L6 requires real runtime evidence and is not fabricated during migration.

### 7.2 Finding aggregation

Root-cause keys use:

```text
reason_code + Capability@major + rule_id (when applicable)
```

Reports separately count evidence rows, root-cause groups, affected Capabilities, and shared remediation families. A cross-domain conflict is one root-cause group listing every involved Capability.

### 7.3 Test evidence

A business-rule test proves the authoritative Capability or Provider behavior, covers a valid case, applicable boundaries, rejection, stable error code, and failure atomicity. State rules cover allowed and forbidden transitions.

A generic Gateway smoke test proves the technical path only and never counts as rule-specific evidence.

## 8. Gate Semantics

The Release Gate emits separate results:

```text
machine_passed
human_approved
runtime_verified
legacy_pending_review_count
```

It applies the following policy:

| Subject | Required decision |
|---|---|
| New Capability | machine passed and current human approval |
| Materially changed Capability | machine passed and renewed human approval |
| Unchanged legacy Capability | may remain testable as `legacy_pending_review` |
| Deterministic blocker | blocked regardless of legacy status |

Deterministic blockers include ambiguous public entry binding, provably incompatible rules for the same conditions, bypass of an approved critical-field write path, missing claimed evidence, and mismatch among Descriptor, Catalog, approval hash, Provider artifact, source revision, or production artifact.

The signed release report remains the final release decision. Static audit, human approval, runtime evidence, and source/artifact bindings are distinct signed inputs.

## 9. Runtime Effectiveness

Runtime effectiveness is added after the L5 control loop is operational. It records aggregate, privacy-safe evidence such as rule rejection count, unexpected provider failures, approved exception use, and repeated false-positive review feedback.

Effectiveness signals trigger review; they do not silently rewrite rules or approvals. Any semantic rule change returns through the normal proposal and approval path.

## 10. Implementation Boundaries

The implementation should extend the smallest existing surfaces:

- `backend/capability_v2/contracts.py`: additive Descriptor fields and semantic hash projection;
- `backend/capability_v2/catalog.py` and `catalog_audit.py`: authoritative purpose/rule projection and validation;
- `backend/capability_governance_test/models.py`, `store.py`, `scanner.py`, and `provider.py`: persistent projections, fingerprints, relations, review views, and query output;
- `backend/capability_governance_test/ai_advisory.py`: advisory-only relationship explanations;
- existing Base approval service: `super_admin` decision workflow primitive;
- `backend/capability_v2/release_gate.py` and governance release gate: independent machine/human/runtime results and legacy policy;
- governance center Web UI: review queue, evidence view, relation comparison, and decisions;
- audit scripts and tests: seven-layer baseline and exact root-cause aggregation.

No new external dependency is required. No production database is modified by scans or audits. Schema changes use the existing versioned migration mechanism.

## 11. Error and Safety Rules

- Scanner parsing or configuration failures become structured blocking findings rather than process crashes.
- Missing, stale, or mismatched approval evidence fails closed for new and materially changed Capabilities.
- AI timeout or failure removes the advisory explanation but does not suppress deterministic findings or prevent a human from reviewing the hard evidence.
- Review decisions are append-only; correction creates a superseding decision.
- Audit and migration jobs are read-only except for governance projections, findings, reviews, and evidence owned by the Governance Center.
- A false-positive disposition must include a rationale and remains bound to the analyzed versions.

## 12. Verification Strategy

1. Contract tests for additive fields, exclusivity, and semantic hash stability.
2. Scanner tests proving authoritative purpose ingestion and rejection of generated templates.
3. Analyzer tests for duplicate, containment, formal conflict, overlap, candidate narrowing, and AI advisory separation.
4. Review tests for `super_admin` authorization, append-only decisions, exact-hash approval, expiry, and non-mutation of Catalog authority.
5. Gate tests for new, material-change, unchanged-legacy, deterministic-blocker, stale approval, and current approval cases.
6. Audit tests for seven layers, L0-L6 grading, exact root-cause keys, cross-domain grouping, and separate evidence/root-cause counts.
7. One controlled end-to-end path from Descriptor to snapshot, analysis, human approval, signed release report, artifact verification, and readback.
8. Regression execution of the current offline strict acceptance and Web governance scans to prove legacy testing remains available.

## 13. Delivery Sequence

1. Add compatible contracts, statuses, semantic hashes, migrations, and unit tests without tightening the legacy gate.
2. Correct scanner projections and generate the first seven-layer baseline.
3. Add deterministic fingerprints and relationship analyzers; keep AI advisory-only.
4. Add Governance Center review queries and the `super_admin` review workflow.
5. Add the review UI and exact-hash decisions.
6. Enforce V2.5 for new and materially changed Capabilities while reporting legacy backlog separately.
7. Review and repair the highest-risk legacy write families, then remaining writes and reads.
8. Add runtime-effectiveness evidence and periodic review triggers.

Each step leaves a runnable test and a reversible gate mode. The first usable milestone is step 6; completion of all legacy reviews is not a prerequisite for entering product testing.

## 14. Completion Criteria

V2.5 infrastructure is complete when:

- new and materially changed Capabilities cannot become stable without a current exact-hash `super_admin` approval;
- legacy Capabilities remain testable and are visibly tracked by risk and maturity;
- every audit report includes the seven layers, L0-L6 level, exact root-cause groups, relation candidates, and separate machine/human/runtime states;
- deterministic duplicate, coverage, conflict, and bypass evidence is reproducible;
- AI output is visibly advisory and cannot change gate results by itself;
- the signed release decision binds current Catalog, Descriptor, Provider, approval, source, tests, and artifact identities; and
- the Governance Center can produce an actionable review queue for the existing Catalog without treating every finding row as an independent repair task.
