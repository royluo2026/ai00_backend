# Capability Business Governance V2.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Capability governance stack so new and materially changed Capabilities require reproducible business-purpose/rule evidence and an exact-hash `super_admin` approval, while unchanged legacy Capabilities remain testable in a visible review backlog.

**Architecture:** Keep business-rule execution in domain Providers, cross-cutting controls in the Gateway, and review/evidence projections in the existing Governance Center. Add compatible Descriptor fields, a generated semantic definition hash, deterministic seven-layer analysis and relationship candidates, advisory-only AI explanations, an immutable review decision, and separate machine/human/runtime release results.

**Tech Stack:** Python 3, Pydantic v2, dataclasses, OceanBase/MySQL-compatible SQL, pytest, vanilla JavaScript, Node test runner, existing Capability Gateway and Governance Center.

**Spec:** `docs/superpowers/specs/2026-09-01-capability-business-governance-v25-design.md`

## Global Constraints

- Phase 1 human approval is restricted to `super_admin`.
- AI output is advisory and can never approve, reject, merge, retire, waive, or assign blocking severity.
- `business_effect` remains a string; existing public contracts are extended additively.
- Business-rule execution remains in the owning domain Provider or policy; do not create a central rule engine.
- Descriptor owns purpose and invariant declarations; Catalog owns the generated definition hash; Governance Center owns approval state and review references.
- Existing stable Capabilities default to `legacy_pending_review` and remain testable unless a deterministic blocker exists.
- New and materially changed Capabilities must be machine-passed and human-approved before stable release.
- Scans and audits never modify domain data, production Catalog authority, or permissions.
- No new third-party dependency.
- Use immutable versioned migrations; never modify an applied migration.
- Finding evidence rows, root-cause groups, affected Capabilities, and shared remediation families are reported separately.

---

## File Map

### Backend repository

- `backend/capability_v2/contracts.py`: author-controlled business-governance contract fields.
- `backend/capability_v2/business_definition.py`: canonical business projection, template detection, and semantic hash.
- `backend/capability_v2/catalog.py`: generated Catalog projection.
- `backend/capability_v2/catalog_audit.py`: V2.5 structural/static checks without blocking unchanged legacy entries.
- `backend/capability_governance_test/business_models.py`: immutable purpose, rule, fingerprint, relation, maturity, and review projections.
- `backend/capability_governance_test/business_relations.py`: deterministic candidate narrowing and relationship analyzers.
- `backend/capability_governance_test/models.py`: snapshot integration fields only.
- `backend/capability_governance_test/scanner.py`: authoritative extraction and business fingerprints.
- `backend/capability_governance_test/store.py`: persistence port and SQL/in-memory projections.
- `backend/capability_governance_test/workflow.py`: exact-hash `super_admin` review decision.
- `backend/capability_governance_test/service.py`: analysis, review queue, and decision orchestration.
- `backend/capability_governance_test/contracts.py`: closed Gateway request/response contracts.
- `backend/capability_governance_test/provider.py`: governed read/write dispatch.
- `backend/capability_governance_test/ai_advisory.py`: advisory explanation for deterministic relation candidates.
- `backend/capability_governance_test/release_gate.py`: Governance Center release decision.
- `backend/capability_v2/release_gate.py`: static release inputs and legacy/new policy.
- `backend/db/migrations/test_governance/0005_business_governance.sql`: governance-only normalized persistence.
- `backend/scripts/audit_capability_business_rules.py`: seven-layer audit and migration baseline.
- `backend/scripts/check_capability_v2_release_gate.py`: separate machine/human/runtime reporting.
- `docs/governance/capability-business-governance-legacy-baseline.json`: immutable cutover keys and V2.5 definition hashes for the existing Catalog.
- `docs/governance/atomic-capability-spec-v2.md`: V2.5 normative text.

### Web repository (`E:/Projects/ai00/workmanship-web`, branch `test`)

- `web/admin/capability_governance/governance_api.js`: review queue, evidence detail, and decision calls.
- `web/admin/capability_governance/governance_controller_next.js`: maturity filters, comparison drawer, and review actions.
- `web/admin/capability_governance/governance.css`: review and relation presentation.
- existing adjacent `*.test.js`: API and rendering tests.

---

### Task 1: Add Authoritative Business Contracts and Semantic Hash

**Files:**
- Create: `backend/capability_v2/business_definition.py`
- Modify: `backend/capability_v2/contracts.py:309-367`
- Test: `backend/tests/test_capability_business_definition.py`

**Interfaces:**
- Produces: `BusinessInvariantContract`, `business_definition_projection(descriptor) -> dict[str, object]`, `business_definition_hash(descriptor) -> str`, `is_generated_business_effect(value, description) -> bool`.
- Consumes: existing `CapabilityDescriptorV2`, `FrozenModel`, and canonical JSON hash conventions.

- [ ] **Step 1: Write failing contract and hash tests**

```python
def test_business_invariant_and_no_rule_reason_are_exclusive(descriptor_factory):
    with pytest.raises(ValueError, match="business_rule_declaration_conflict"):
        descriptor_factory(
            business_invariants=({"rule_id": "person.height.range", "version": 1,
                "statement": "Height is 0.3m to 2.5m", "applies_when": "height changes",
                "enforcement_ref": "person.provider:validate_height",
                "error_code": "invalid_person_height", "test_refs": ("tests/test_height.py::test_range",)},),
            no_business_invariant_reason="No rules",
        )

def test_semantic_hash_ignores_description_formatting(descriptor_factory):
    left = descriptor_factory(description="First description")
    right = descriptor_factory(description="Second description")
    assert business_definition_hash(left) == business_definition_hash(right)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_business_definition.py -q`

Expected: collection fails because `backend.capability_v2.business_definition` and `BusinessInvariantContract` do not exist.

- [ ] **Step 3: Add the minimal additive contracts and canonical projection**

```python
class BusinessInvariantContract(FrozenModel):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    version: int = Field(ge=1)
    statement: str = Field(min_length=1, max_length=4000)
    applies_when: str = Field(min_length=1, max_length=4000)
    enforcement_ref: str = Field(min_length=1, max_length=1000)
    error_code: str = Field(min_length=1, max_length=255)
    test_refs: tuple[str, ...] = Field(min_length=1)

# CapabilityDescriptorV2 additions
business_acceptance_criteria: tuple[str, ...] = ()
business_invariants: tuple[BusinessInvariantContract, ...] = ()
no_business_invariant_reason: str | None = Field(default=None, min_length=1, max_length=4000)
```

```python
def business_definition_projection(descriptor: CapabilityDescriptorV2) -> dict[str, object]:
    return {
        "capability_id": descriptor.id,
        "major_version": descriptor.major_version,
        "business_effect": (descriptor.business_effect or "").strip(),
        "business_acceptance_criteria": list(descriptor.business_acceptance_criteria),
        "business_invariants": [item.model_dump(mode="json") for item in descriptor.business_invariants],
        "no_business_invariant_reason": descriptor.no_business_invariant_reason,
        "input_schema": descriptor.input_schema,
        "output_schema": descriptor.output_schema,
        "provider_ref": descriptor.provider_ref,
        "side_effects": descriptor.side_effects,
    }

def business_definition_hash(descriptor: CapabilityDescriptorV2) -> str:
    raw = json.dumps(business_definition_projection(descriptor), ensure_ascii=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"
```

- [ ] **Step 4: Run focused and existing contract tests**

Run: `python -m pytest backend/tests/test_capability_business_definition.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/test_capability_catalog_release.py -q`

Expected: PASS; existing descriptors without new fields still construct successfully.

- [ ] **Step 5: Commit the contract slice**

```bash
git add backend/capability_v2/contracts.py backend/capability_v2/business_definition.py backend/tests/test_capability_business_definition.py
git commit -m "feat: add capability business definition contracts"
```

### Task 2: Generate and Audit Compatible Catalog Projections

**Files:**
- Modify: `backend/capability_v2/catalog.py:80-125`
- Modify: `backend/capability_v2/catalog_audit.py:20-190`
- Modify: `backend/scripts/build_capability_catalog.py`
- Test: `backend/tests/test_capability_catalog_release.py`
- Test: `backend/tests/test_capability_v2_catalog_audit.py`

**Interfaces:**
- Consumes: `business_definition_hash()` and `is_generated_business_effect()` from Task 1.
- Produces: Catalog keys `business_acceptance_criteria`, `business_invariants`, `no_business_invariant_reason`, `business_definition_hash`, and audit counters `generated_business_effect_count`, `missing_business_rule_declaration_count`.

- [ ] **Step 1: Add failing projection and audit tests**

```python
def test_catalog_projects_business_definition_hash(stable_descriptor):
    entry = build_catalog_entry(stable_descriptor)
    assert entry["business_definition_hash"].startswith("sha256:")
    assert entry["business_invariants"][0]["rule_id"] == "person.height.range"

def test_generated_business_effect_is_reported_not_silently_accepted(catalog_entry):
    catalog_entry["business_effect"] = f"Business outcome: {catalog_entry['description']}"
    report = audit_catalog_entries([catalog_entry])
    assert report.generated_business_effect_count == 1
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_catalog_release.py backend/tests/test_capability_v2_catalog_audit.py -q`

Expected: FAIL because the generated hash and V2.5 counters are absent.

- [ ] **Step 3: Replace silent business-effect synthesis with explicit projection**

```python
business_effect = (item.business_effect or "").strip()
business_governance_fields = {
    "business_effect": business_effect,
    "business_acceptance_criteria": list(item.business_acceptance_criteria),
    "business_invariants": [rule.model_dump(mode="json") for rule in item.business_invariants],
    "no_business_invariant_reason": item.no_business_invariant_reason,
    "business_definition_hash": business_definition_hash(item),
}
entry.update(business_governance_fields)
return entry
```

The audit records generated/missing business data. It does not globally block unchanged legacy entries; the release policy in Task 7 decides whether the entry is new, materially changed, or legacy.

- [ ] **Step 4: Verify generator determinism and audit behavior**

Run: `python backend/scripts/build_capability_catalog.py --check`

Run: `python -m pytest backend/tests/test_capability_catalog_release.py backend/tests/test_capability_v2_catalog_audit.py -q`

Expected: both commands PASS and two consecutive generated Catalogs have identical hashes.

- [ ] **Step 5: Commit the Catalog slice**

```bash
git add backend/capability_v2/catalog.py backend/capability_v2/catalog_audit.py backend/scripts/build_capability_catalog.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_v2_catalog_audit.py
git commit -m "feat: project capability business governance metadata"
```

### Task 3: Persist Business Governance Projections

**Files:**
- Create: `backend/capability_governance_test/business_models.py`
- Create: `backend/db/migrations/test_governance/0005_business_governance.sql`
- Modify: `backend/capability_governance_test/models.py:41-75,121-143`
- Modify: `backend/capability_governance_test/store.py:13-68`
- Test: `backend/tests/test_capability_governance_business_store.py`
- Test: `backend/tests/test_versioned_migration_files.py`

**Interfaces:**
- Produces immutable `BusinessPurposeRecord`, `BusinessRuleRecord`, `CapabilityFingerprint`, `CapabilityRelationCandidate`, `CapabilityMaturity`, and `CapabilityBusinessReview`.
- Produces store methods `save_business_projection(projection: CapabilityBusinessProjection) -> None`, `list_relation_candidates(snapshot_gid: int) -> tuple[CapabilityRelationCandidate, ...]`, `save_business_review(review: CapabilityBusinessReview) -> None`, `current_business_review(capability_version_gid: int, definition_hash: str) -> CapabilityBusinessReview | None`, `save_rule_effectiveness(record: RuleEffectivenessRecord) -> None`, and `list_rule_effectiveness(capability_version_gid: int, definition_hash: str) -> tuple[RuleEffectivenessRecord, ...]`.

- [ ] **Step 1: Write failing model, immutability, migration, and round-trip tests**

```python
def test_business_review_is_bound_to_exact_definition_hash(store):
    review = CapabilityBusinessReview(
        review_gid=101, capability_version_gid=202, definition_hash="sha256:" + "1" * 64,
        decision="approved", decision_reason="Evidence is sufficient",
        reviewer_gid="9001", reviewer_role="super_admin", decided_at=NOW,
    )
    store.save_business_review(review)
    assert store.current_business_review(202, review.definition_hash) == review
    assert store.current_business_review(202, "sha256:" + "2" * 64) is None

def test_rule_effectiveness_is_append_only(store):
    record = effectiveness_record(metric_name="rule_rejection_count", metric_value=7)
    store.save_rule_effectiveness(record)
    assert store.list_rule_effectiveness(record.capability_version_gid, record.definition_hash) == (record,)
```

```python
def test_business_governance_migration_is_discoverable():
    ids = {item.migration_id for item in discover_migrations(TEST_GOVERNANCE_DIR)}
    assert "0005" in ids
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_governance_business_store.py backend/tests/test_versioned_migration_files.py -q`

Expected: FAIL because the models, migration, and store methods are missing.

- [ ] **Step 3: Add immutable records and four normalized tables**

```python
@dataclass(frozen=True)
class CapabilityBusinessReview:
    review_gid: int
    capability_version_gid: int
    definition_hash: str
    decision: Literal["approved", "rejected", "changes_requested"]
    decision_reason: str
    reviewer_gid: str
    reviewer_role: str
    decided_at: datetime

@dataclass(frozen=True)
class RuleEffectivenessRecord:
    effectiveness_gid: int
    capability_version_gid: int
    definition_hash: str
    metric_name: str
    metric_value: int
    evidence: Mapping[str, object]
    measured_from: datetime
    measured_to: datetime
```

```sql
CREATE TABLE IF NOT EXISTS workmanship_base_capability_business_purposes (
  purpose_gid BIGINT NOT NULL PRIMARY KEY,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  business_effect VARCHAR(4000) NOT NULL,
  acceptance_criteria_json LONGTEXT NOT NULL,
  evidence_snapshot_gid BIGINT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_capability_business_purpose (capability_version_gid, definition_hash)
);
CREATE TABLE IF NOT EXISTS workmanship_base_capability_business_rules (
  business_rule_gid BIGINT NOT NULL PRIMARY KEY,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  rule_id VARCHAR(128) NOT NULL,
  rule_version BIGINT NOT NULL,
  statement VARCHAR(4000) NOT NULL,
  applies_when VARCHAR(4000) NOT NULL,
  enforcement_ref VARCHAR(1000) NOT NULL,
  error_code VARCHAR(255) NOT NULL,
  test_refs_json LONGTEXT NOT NULL,
  evidence_snapshot_gid BIGINT NOT NULL,
  UNIQUE KEY uq_capability_business_rule (capability_version_gid, definition_hash, rule_id, rule_version)
);
CREATE TABLE IF NOT EXISTS workmanship_base_capability_relation_candidates (
  relation_candidate_gid BIGINT NOT NULL PRIMARY KEY,
  snapshot_gid BIGINT NOT NULL,
  candidate_hash VARCHAR(71) NOT NULL,
  relation_type VARCHAR(32) NOT NULL,
  source VARCHAR(32) NOT NULL,
  capability_keys_json LONGTEXT NOT NULL,
  evidence_json LONGTEXT NOT NULL,
  status VARCHAR(32) NOT NULL,
  UNIQUE KEY uq_capability_relation_candidate (snapshot_gid, candidate_hash)
);
CREATE TABLE IF NOT EXISTS workmanship_base_capability_business_reviews (
  business_review_gid BIGINT NOT NULL PRIMARY KEY,
  proposal_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  decision VARCHAR(32) NOT NULL,
  decision_reason VARCHAR(2000) NOT NULL,
  reviewer_gid BIGINT NOT NULL,
  reviewer_role VARCHAR(64) NOT NULL,
  evidence_snapshot_gid BIGINT NOT NULL,
  decided_at DATETIME(6) NOT NULL,
  KEY ix_capability_business_review_subject (capability_version_gid, definition_hash, decided_at)
);
CREATE TABLE IF NOT EXISTS workmanship_base_capability_rule_effectiveness (
  effectiveness_gid BIGINT NOT NULL PRIMARY KEY,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  metric_name VARCHAR(128) NOT NULL,
  metric_value BIGINT NOT NULL,
  evidence_json LONGTEXT NOT NULL,
  measured_from DATETIME(6) NOT NULL,
  measured_to DATETIME(6) NOT NULL,
  KEY ix_capability_rule_effectiveness_subject (capability_version_gid, definition_hash, measured_to)
);
```

Use append-only review rows. Store rule/test/evidence arrays as canonical JSON. Add in-memory and SQL implementations behind the existing governance persistence boundary. Add foreign keys to the existing Capability version, snapshot, and proposal tables where the current test-governance migration style permits them.

- [ ] **Step 4: Verify in-memory/SQL-shape parity and immutable migrations**

Run: `python -m pytest backend/tests/test_capability_governance_business_store.py backend/tests/test_versioned_migration_files.py backend/tests/test_capability_governance_service_workflow.py -q`

Expected: PASS; an approval lookup succeeds only for the exact hash.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add backend/capability_governance_test/business_models.py backend/capability_governance_test/models.py backend/capability_governance_test/store.py backend/db/migrations/test_governance/0005_business_governance.sql backend/tests/test_capability_governance_business_store.py backend/tests/test_versioned_migration_files.py
git commit -m "feat: persist capability business governance projections"
```

### Task 4: Correct the Scanner and Produce Seven-layer Evidence

**Files:**
- Modify: `backend/capability_governance_test/scanner.py:208-560`
- Modify: `backend/capability_governance_test/models.py:41-75`
- Modify: `backend/capability_governance_test/service.py:380-440`
- Test: `backend/tests/test_capability_governance_business_scanner.py`
- Test: `backend/tests/test_capability_governance_provider.py`

**Interfaces:**
- Consumes: Catalog V2.5 fields and business models from Tasks 1-3.
- Produces: authoritative `ScannedCapability.business_effect`, rules, fingerprint, per-layer evidence, and maturity `L0`-`L6` candidate.

- [ ] **Step 1: Write failing scanner tests for authoritative fields and structured failures**

```python
def test_scanner_uses_business_effect_not_description(scanner, catalog):
    catalog["entries"][0].update(business_effect="Approved outcome", description="Technical text")
    item = scanner.scan("abc123").capabilities[0]
    assert item.business_effect == "Approved outcome"

def test_scanner_marks_generated_effect_as_l1(scanner, catalog):
    entry = catalog["entries"][0]
    entry["business_effect"] = f"Business outcome: {entry['description']}"
    item = scanner.scan("abc123").capabilities[0]
    assert item.business_maturity.level == "L1"
    assert "generated_business_effect" in item.business_maturity.reason_codes
```

- [ ] **Step 2: Run scanner tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_governance_business_scanner.py -q`

Expected: FAIL because scanner line 535 still substitutes `description/title` and no maturity evidence exists.

- [ ] **Step 3: Extract authoritative data and compute a deterministic fingerprint**

```python
business_effect = str(descriptor.get("business_effect") or "").strip()
fingerprint = CapabilityFingerprint(
    owner_domain=owner,
    business_object=_business_object(descriptor),
    action=_business_action(capability_id, descriptor),
    business_effect=business_effect,
    input_schema_hash=input_hash,
    output_schema_hash=output_hash,
    provider_ref=str(descriptor.get("provider_ref") or ""),
    read_scope=tuple(sorted(read_scope)),
    write_scope=tuple(sorted(write_scope)),
    rule_ids=tuple(sorted(rule.rule_id for rule in rules)),
)
```

Catch parser/configuration exceptions at the scan boundary and return a structured blocking scan finding with the source path and error category; do not let the release command crash without a report.

- [ ] **Step 4: Verify authoritative extraction and current scan regression**

Run: `python -m pytest backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_provider.py -q`

Run: `python backend/scripts/run_capability_governance_scan.py --help`

Expected: tests PASS; the CLI remains callable and generated business effects are visible as evidence, not silently approved.

- [ ] **Step 5: Commit the scanner slice**

```bash
git add backend/capability_governance_test/scanner.py backend/capability_governance_test/models.py backend/capability_governance_test/service.py backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_provider.py
git commit -m "feat: scan authoritative capability business evidence"
```

### Task 5: Add Deterministic Relationship Analysis and Advisory AI

**Files:**
- Create: `backend/capability_governance_test/business_relations.py`
- Modify: `backend/capability_governance_test/ai_advisory.py`
- Modify: `backend/capability_governance_test/service.py:778-820`
- Test: `backend/tests/test_capability_business_relations.py`
- Test: `backend/tests/test_capability_governance_ai_advisory.py`

**Interfaces:**
- Produces: `analyze_relationships(capabilities) -> tuple[CapabilityRelationCandidate, ...]`.
- Produces: `explain_relation(candidate, evidence) -> AdvisoryFinding` with `authority="advisory"`.
- Consumes: fingerprints and rule projections from Task 4.

- [ ] **Step 1: Write failing duplicate, coverage, conflict, overlap, and AI-boundary tests**

```python
def test_formal_rule_conflict_lists_both_capabilities():
    result = analyze_relationships((height_rule(maximum=2.5), height_rule(maximum=2.2)))
    conflict = next(item for item in result if item.relation_type == "conflict")
    assert conflict.capability_keys == ("ergonomics.height.validate@1", "person.height.write@1")
    assert conflict.source == "deterministic"

def test_ai_advisory_cannot_raise_blocking_severity(candidate):
    advisory = explain_relation(candidate, evidence={"summary": "possibly similar"})
    assert advisory.authority == "advisory"
    assert advisory.severity != "blocking"
```

- [ ] **Step 2: Run relation tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_business_relations.py backend/tests/test_capability_governance_ai_advisory.py -q`

Expected: FAIL because the analyzers and advisory authority marker do not exist.

- [ ] **Step 3: Implement narrowed deterministic analyzers**

```python
def candidate_pairs(items: Iterable[ScannedCapability]) -> Iterator[tuple[ScannedCapability, ScannedCapability]]:
    buckets: dict[tuple[str, str], list[ScannedCapability]] = defaultdict(list)
    for item in items:
        buckets[(item.fingerprint.business_object, item.fingerprint.action)].append(item)
    for bucket in buckets.values():
        yield from combinations(sorted(bucket, key=lambda item: (item.capability_id, item.major_version)), 2)

def analyze_relationships(items: Iterable[ScannedCapability]) -> tuple[CapabilityRelationCandidate, ...]:
    return tuple(sorted(_analyze_pair(left, right) for left, right in candidate_pairs(items)
                        if _analyze_pair(left, right) is not None))
```

Deterministic blocking is limited to provable same-condition rule contradiction, ambiguous public binding, approved critical-write bypass, and identity/hash mismatch. Semantic similarity remains a review candidate.

- [ ] **Step 4: Verify determinism and bounded AI behavior**

Run: `python -m pytest backend/tests/test_capability_business_relations.py backend/tests/test_capability_governance_ai_advisory.py backend/tests/test_capability_governance_service_workflow.py -q`

Expected: PASS; shuffling input produces identical candidate IDs and evidence hashes.

- [ ] **Step 5: Commit the relation slice**

```bash
git add backend/capability_governance_test/business_relations.py backend/capability_governance_test/ai_advisory.py backend/capability_governance_test/service.py backend/tests/test_capability_business_relations.py backend/tests/test_capability_governance_ai_advisory.py
git commit -m "feat: analyze capability business relationships"
```

### Task 6: Add the Exact-hash Super-admin Review Workflow

**Files:**
- Modify: `backend/capability_governance_test/workflow.py:56-219`
- Modify: `backend/capability_governance_test/service.py:836-890`
- Modify: `backend/capability_governance_test/contracts.py:139-157,214-235`
- Modify: `backend/capability_governance_test/provider.py:127-208`
- Test: `backend/tests/test_capability_business_review.py`
- Test: `backend/tests/test_capability_governance_service_workflow.py`

**Interfaces:**
- Consumes: `CapabilityBusinessReview` persistence from Task 3 and semantic hash from Task 1.
- Produces governed operations through existing `base.capability_review.decide` and proposal search; no new parallel approval API.
- Review request fields: `proposal_gid`, `definition_hash`, `decision`, `decision_reason`, `row_version`.

- [ ] **Step 1: Write failing authorization, hash, append-only, and expiry tests**

```python
def test_only_super_admin_can_approve_business_definition(service, context_factory, pending_proposal):
    with pytest.raises(CapabilityBusinessError, match="reviewer_not_authorized"):
        service.base_capability_review_decide(review_payload(pending_proposal), context_factory(roles=("admin",)))

def test_changed_hash_has_no_current_approval(review_store, approved_review):
    review_store.save_business_review(approved_review)
    assert review_store.current_business_review(approved_review.capability_version_gid,
                                                "sha256:" + "9" * 64) is None
```

- [ ] **Step 2: Run workflow tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_business_review.py backend/tests/test_capability_governance_service_workflow.py -q`

Expected: FAIL because the existing stage rules require `base_owner`/`platform_release` and do not bind a business definition hash or reason.

- [ ] **Step 3: Add a business-review path to the existing proposal workflow**

```python
def decide_business_definition(
    self,
    proposal_gid: int,
    *,
    reviewer_context: ReviewerContext,
    definition_hash: str,
    decision: str,
    decision_reason: str,
    expected_row_version: int,
    idempotency_key: str,
    decided_at: datetime | None = None,
) -> Proposal:
    if "super_admin" not in reviewer_context.roles:
        raise WorkflowError("reviewer_not_authorized")
    if decision not in {"approved", "rejected", "changes_requested"}:
        raise WorkflowError("review_decision_invalid")
    if definition_hash != proposal.proposed_descriptor_hash:
        raise WorkflowError("review_subject_hash_mismatch")
    # append review; never mutate a prior decision
```

Keep AI identities forbidden. Return relation evidence, business purpose, rules, maturity, and exact hash in the proposal/review projection. Require a non-empty decision reason for all decisions.

- [ ] **Step 4: Verify Gateway contracts and workflow behavior**

Run: `python -m pytest backend/tests/test_capability_business_review.py backend/tests/test_capability_governance_service_workflow.py backend/tests/test_capability_governance_provider.py -q`

Expected: PASS; `super_admin` approves exact hash, stale hash is rejected, all decisions are append-only and auditable.

- [ ] **Step 5: Commit the review slice**

```bash
git add backend/capability_governance_test/workflow.py backend/capability_governance_test/service.py backend/capability_governance_test/contracts.py backend/capability_governance_test/provider.py backend/tests/test_capability_business_review.py backend/tests/test_capability_governance_service_workflow.py backend/tests/test_capability_governance_provider.py
git commit -m "feat: add super-admin capability business review"
```

### Task 7: Enforce New/Changed Approval Without Blocking Legacy Testing

**Files:**
- Modify: `backend/capability_v2/release_gate.py:1-95`
- Modify: `backend/capability_governance_test/release_gate.py`
- Modify: `backend/scripts/check_capability_v2_release_gate.py`
- Create: `docs/governance/capability-business-governance-legacy-baseline.json`
- Test: `backend/tests/test_capability_v2_business_release_gate.py`
- Test: `backend/tests/test_capability_governance_release_gate.py`

**Interfaces:**
- Consumes: current Catalog definition hash, previous released hash, deterministic blockers, and current review lookup.
- Produces: `machine_passed`, `human_approved`, `runtime_verified`, `legacy_pending_review_count`, and per-Capability `governance_status`.

- [ ] **Step 1: Write the gate policy matrix as failing tests**

```python
@pytest.mark.parametrize((kind, approved, expected), [
    ("new", False, "blocked"),
    ("material_change", False, "blocked"),
    ("unchanged_legacy", False, "passed_with_legacy_backlog"),
    ("new", True, "passed"),
])
def test_business_governance_gate_policy(kind, approved, expected, gate_case):
    assert evaluate_business_governance_gate(gate_case(kind=kind, approved=approved)).status == expected

def test_deterministic_blocker_always_blocks(gate_case):
    result = evaluate_business_governance_gate(gate_case(kind="unchanged_legacy", deterministic_blockers=("route_conflict",)))
    assert result.status == "blocked"

def test_cutover_capability_is_legacy_only_while_hash_is_unchanged(gate_case):
    baseline = {"person.height.write@1": "sha256:" + "1" * 64}
    assert gate_case(definition_hash="sha256:" + "1" * 64, legacy_baseline=baseline).change_kind == "unchanged_legacy"
    assert gate_case(definition_hash="sha256:" + "2" * 64, legacy_baseline=baseline).change_kind == "material_change"
```

- [ ] **Step 2: Run gate tests and verify RED**

Run: `python -m pytest backend/tests/test_capability_v2_business_release_gate.py backend/tests/test_capability_governance_release_gate.py -q`

Expected: FAIL because current gates do not distinguish legacy/new/material change or machine/human/runtime states.

- [ ] **Step 3: Implement the explicit policy result**

```python
@dataclass(frozen=True)
class BusinessGateResult:
    status: str
    machine_passed: bool
    human_approved: bool
    runtime_verified: bool
    legacy_pending_review_count: int
    blockers: tuple[str, ...]

def classify_change(
    capability_key: str,
    current_hash: str,
    previous_hash: str | None,
    legacy_baseline: Mapping[str, str],
) -> str:
    reference = previous_hash or legacy_baseline.get(capability_key)
    if reference is None:
        return "new"
    return "unchanged_legacy" if current_hash == reference else "material_change"
```

Generate the cutover baseline once from the exact pre-enforcement Catalog and bind it to the source revision and Catalog release ID. Subsequent commands only verify it; they never rewrite it implicitly. The signed Governance Center report consumes this structured result. A static green report cannot imply human approval or runtime verification.

- [ ] **Step 4: Run release-gate regression and offline acceptance**

Run: `python -m pytest backend/tests/test_capability_v2_business_release_gate.py backend/tests/test_capability_v2_release_gate.py backend/tests/test_capability_governance_release_gate.py -q`

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`

Expected: tests PASS; offline acceptance remains runnable and reports legacy backlog separately rather than failing all unchanged stable entries.

- [ ] **Step 5: Commit the gate slice**

```bash
git add backend/capability_v2/release_gate.py backend/capability_governance_test/release_gate.py backend/scripts/check_capability_v2_release_gate.py docs/governance/capability-business-governance-legacy-baseline.json backend/tests/test_capability_v2_business_release_gate.py backend/tests/test_capability_governance_release_gate.py
git commit -m "feat: gate new capability business definitions"
```

### Task 8: Replace Binary Audit With the Seven-layer Baseline

**Files:**
- Modify: `backend/scripts/audit_capability_business_rules.py`
- Create: `backend/capability_governance_test/business_audit.py`
- Modify: `backend/capability_governance_test/service.py:740-820`
- Test: `backend/tests/test_audit_capability_business_rules.py`
- Test: `backend/tests/test_capability_business_audit.py`

**Interfaces:**
- Produces: `BusinessAuditReport` with `snapshot_gid`, exact source revisions, L0-L6 counts, evidence findings, root-cause groups, affected domains, shared remediation families, relations, unbound entries, review queue, and machine/human/runtime states.
- Root-cause key: `reason_code:Capability@major[:rule_id]`.

- [ ] **Step 1: Write failing aggregation and maturity tests**

```python
def test_evidence_rows_and_root_causes_are_counted_separately():
    report = audit((missing_rule_evidence(line=10), missing_rule_evidence(line=20)))
    assert report.finding_count == 2
    assert report.root_cause_group_count == 1

def test_cross_domain_conflict_is_one_group_with_all_capabilities():
    group = audit((person_height_conflict(), ergonomics_height_conflict())).root_causes[0]
    assert group.capability_keys == ("ergonomics.height.validate@1", "person.height.write@1")
```

- [ ] **Step 2: Run audit tests and verify RED**

Run: `python -m pytest backend/tests/test_audit_capability_business_rules.py backend/tests/test_capability_business_audit.py -q`

Expected: FAIL because the current audit lacks complete seven-layer results and exact grouped output.

- [ ] **Step 3: Add explicit report records and stable aggregation**

```python
def root_cause_key(reason_code: str, capability_id: str, major: int, rule_id: str | None) -> str:
    suffix = f":{rule_id}" if rule_id else ""
    return f"{reason_code}:{capability_id}@{major}{suffix}"

@dataclass(frozen=True)
class BusinessAuditReport:
    snapshot_gid: str
    finding_count: int
    root_cause_group_count: int
    affected_capability_count: int
    shared_remediation_family_count: int
    maturity_counts: Mapping[str, int]
    machine_passed: bool
    human_approved: bool
    runtime_verified: bool
```

Paginate registry and finding inputs with `limit <= 200` until `offset >= total`. Include every unbound REST route, Provider, worker, MCP/Agent Tool, and file location.

- [ ] **Step 4: Run unit tests and generate a read-only local baseline**

Run: `python -m pytest backend/tests/test_audit_capability_business_rules.py backend/tests/test_capability_business_audit.py -q`

Run: `python backend/scripts/audit_capability_business_rules.py --format json`

Expected: PASS and valid JSON containing `snapshot_gid`, seven layers, exact grouped counts, relationship candidates, and legacy review queue; no domain table is written.

- [ ] **Step 5: Commit the audit slice**

```bash
git add backend/capability_governance_test/business_audit.py backend/capability_governance_test/service.py backend/scripts/audit_capability_business_rules.py backend/tests/test_audit_capability_business_rules.py backend/tests/test_capability_business_audit.py
git commit -m "feat: add seven-layer capability business audit"
```

### Task 9: Add the Governance Center Review Workbench

**Repository:** `E:/Projects/ai00/workmanship-web` on branch `test`

**Files:**
- Modify: `web/admin/capability_governance/governance_api.js`
- Modify: `web/admin/capability_governance/governance_controller_next.js`
- Modify: `web/admin/capability_governance/governance.css`
- Test: `web/admin/capability_governance/governance_api.test.js`
- Test: `web/admin/capability_governance/governance_controller.test.js`

**Interfaces:**
- Consumes: existing governed `base.capability_analysis.get`, `base.capability_proposal.search`, and `base.capability_review.decide` projections extended by Tasks 5-8.
- Produces UI actions `loadBusinessReviewQueue`, `loadBusinessReviewDetail`, and `decideBusinessReview`.

- [ ] **Step 1: Write failing API and rendering tests**

```javascript
test('approval sends exact definition hash and reason', async () => {
  await api.decideBusinessReview({ proposalGid: '101', rowVersion: '3',
    definitionHash: `sha256:${'1'.repeat(64)}`, decision: 'approved',
    decisionReason: '目的、规则和证据一致' })
  assert.equal(calls[0].capabilityId, 'base.capability_review.decide')
  assert.equal(calls[0].payload.definition_hash, `sha256:${'1'.repeat(64)}`)
})

test('review drawer separates deterministic evidence from AI advice', () => {
  const html = controller.renderBusinessReviewDetail(reviewFixture())
  assert.match(html, /机器证据/)
  assert.match(html, /AI 辅助建议（不参与自动批准）/)
})
```

- [ ] **Step 2: Run Web tests and verify RED**

Run from Web repository: `node --test web/admin/capability_governance/governance_api.test.js web/admin/capability_governance/governance_controller.test.js`

Expected: FAIL because the business review methods and views do not exist.

- [ ] **Step 3: Add the minimal review queue and detail drawer**

```javascript
const decideBusinessReview = ({ proposalGid, rowVersion, definitionHash, decision, decisionReason }, options) =>
  write('base.capability_review.decide', {
    proposal_gid: gid(proposalGid), row_version: String(rowVersion),
    definition_hash: definitionHash, decision, decision_reason: decisionReason
  }, Object.assign({}, options, { expectedResourceVersion: String(rowVersion) }))
```

Render maturity, business purpose, accepted/rejected examples, rules, enforcement/test evidence, relationship comparison, deterministic evidence, AI advice, exact hash, and decision reason. Show approval buttons only when `super_admin` is present in trusted permissions/roles.

- [ ] **Step 4: Run tests and the test-governance build**

Run: `node --test web/admin/capability_governance/governance_api.test.js web/admin/capability_governance/governance_controller.test.js`

Run: `npm run build:test-governance`

Expected: PASS; production build continues to exclude the test-only Governance Center.

- [ ] **Step 5: Commit the Web slice in the Web repository**

```bash
git add web/admin/capability_governance/governance_api.js web/admin/capability_governance/governance_controller_next.js web/admin/capability_governance/governance.css web/admin/capability_governance/governance_api.test.js web/admin/capability_governance/governance_controller.test.js
git commit -m "feat: add capability business review workbench"
```

### Task 10: Prove the End-to-end Control Loop and Publish V2.5

**Files:**
- Create: `backend/tests/integration/test_capability_business_governance_e2e.py`
- Modify: `backend/tests/test_capability_v2_rc_runtime.py`
- Modify: `backend/scripts/run_capability_governance_release_acceptance.py`
- Modify: `docs/governance/atomic-capability-spec-v2.md`
- Create: `docs/audits/2026-09-01-capability-business-governance-v25-baseline.md`
- Create: `docs/audits/2026-09-01-capability-business-governance-v25-baseline.json`

**Interfaces:**
- Consumes: every preceding task.
- Produces: one controlled Descriptor-to-signed-report proof, the first migration baseline, and normative V2.5 documentation.

- [ ] **Step 1: Write the failing controlled end-to-end test**

```python
def test_new_capability_requires_exact_hash_super_admin_approval(governance_runtime):
    snapshot = governance_runtime.scan(new_height_capability())
    analysis = governance_runtime.analyze(snapshot.snapshot_gid)
    assert analysis.machine_passed
    assert governance_runtime.release(snapshot).conclusion == "blocked"
    review = governance_runtime.approve(
        snapshot=snapshot, reviewer_role="super_admin",
        definition_hash=analysis.business_definition_hash,
        decision_reason="Purpose, invariant, implementation and tests agree",
    )
    report = governance_runtime.release(snapshot)
    assert review.definition_hash == analysis.business_definition_hash
    assert report.conclusion == "passed"
    assert governance_runtime.verify_signature(report)
    governance_runtime.record_effectiveness(
        capability_version_gid=analysis.capability_version_gid,
        definition_hash=analysis.business_definition_hash,
        metric_name="rule_rejection_count", metric_value=1,
    )
    verified = governance_runtime.release(snapshot)
    assert verified.runtime_verified
```

- [ ] **Step 2: Run the end-to-end test and verify RED**

Run: `python -m pytest backend/tests/integration/test_capability_business_governance_e2e.py -q`

Expected: FAIL at the first missing integration between scan, analysis, review, and signed release report.

- [ ] **Step 3: Wire the existing controlled acceptance path and update the normative spec**

```python
result = {
    "snapshot_gid": str(snapshot.snapshot_gid),
    "machine_passed": analysis.machine_passed,
    "human_approved": gate.human_approved,
    "runtime_verified": gate.runtime_verified,
    "legacy_pending_review_count": gate.legacy_pending_review_count,
    "release_report_gid": str(report.release_report_gid),
}
```

Update the local specification heading to V2.5 and add the approved super-admin review, advisory AI boundary, joined storage authority, seven-layer audit, exact-hash approval, separate result states, and legacy migration rules. Generate the Markdown and JSON baseline from the same report object; do not hand-edit counts.

- [ ] **Step 4: Run the complete acceptance matrix**

Run: `python -m pytest backend/tests/test_capability_business_definition.py backend/tests/test_capability_governance_business_store.py backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_business_relations.py backend/tests/test_capability_business_review.py backend/tests/test_capability_v2_business_release_gate.py backend/tests/test_capability_business_audit.py backend/tests/integration/test_capability_business_governance_e2e.py -q`

Run: `python backend/scripts/build_capability_catalog.py --check`

Run: `python backend/scripts/generate_capability_docs.py --check`

Run: `python backend/scripts/build_capability_acceptance_manifest.py --check`

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`

Run in Web repository: `node --test web/admin/capability_governance/governance_api.test.js web/admin/capability_governance/governance_controller.test.js`

Run in Web repository: `npm run build:test-governance`

Expected: all commands PASS. The baseline reports current evidence honestly; it may contain legacy pending reviews, but it contains no hidden or collapsed failure categories.

- [ ] **Step 5: Commit backend completion artifacts, then update Feishu from the verified local spec**

```bash
git add backend/tests/integration/test_capability_business_governance_e2e.py backend/tests/test_capability_v2_rc_runtime.py backend/scripts/run_capability_governance_release_acceptance.py docs/governance/atomic-capability-spec-v2.md docs/audits/2026-09-01-capability-business-governance-v25-baseline.md docs/audits/2026-09-01-capability-business-governance-v25-baseline.json
git commit -m "feat: complete capability business governance v2.5"
```

After the commit and readback, replace the Feishu normative document from the verified local V2.5 specification and retain the audit-model document as the human-readable audit reference.

---

## Final Review Gate

- [ ] Confirm every new/changed Capability path fails without current exact-hash `super_admin` approval.
- [ ] Confirm unchanged legacy Capabilities remain testable and appear in `legacy_pending_review` counts.
- [ ] Confirm deterministic blockers cannot be downgraded by AI or legacy status.
- [ ] Confirm AI output is visibly advisory in API, UI, persistence, and tests.
- [ ] Confirm relationship candidates contain all involved Capability keys and concrete evidence.
- [ ] Confirm audit pagination reads every registry and Finding page with `limit <= 200`.
- [ ] Confirm evidence-row and root-cause-group counts are distinct.
- [ ] Confirm signed report binds Catalog, Descriptor, Provider, approval, source, tests, and artifact identities.
- [ ] Confirm no scan, audit, or review path writes domain or production data.
- [ ] Confirm backend and Web commits are both on their `test` branches and recorded in the final audit.
