# Capability Governance Evidence Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five remaining Capability V2 evidence gaps so every governed entry resolves to a stable owned Capability, every Web `/api/` use is classified, consumer and orchestration evidence is reviewable, and the release is bound to reproducible static and trusted runtime evidence.

**Architecture:** Introduce one shared versioned Catalog target index, then make each inventory and registry consume it instead of duplicating lifecycle rules. Generate Web and consumer evidence from source plus small reviewed disposition files, generate the audit from immutable inputs, and run/sign runtime attestation only after all source-derived artifacts are committed.

**Tech Stack:** Python 3, FastAPI route metadata, Pydantic/dataclasses already used by Capability V2, JSON/JSON Schema, pytest, Node/npm frontend checks, Git, Ed25519 release signing through the existing governance service.

**Spec:** `docs/superpowers/specs/2026-08-26-capability-governance-evidence-closure-design.md`

## Global Constraints

- Backend baseline is branch `test`; frontend baseline is branch `test` in `E:\Projects\ai00\workmanship-web`.
- Do not mutate a production database during Tasks 1-7. Task 8 may write only to the explicitly configured controlled governance store through the official Capability Gateway.
- A governed target is valid only when `(capability_id, major_version)` exists, lifecycle is exactly `stable`, ownership matches, and no active atomicity replacement invalidates it.
- Scan all literal `/api/` occurrences under frontend `web/` and `packages/`; prefix lists may classify but may not limit discovery.
- A stable descriptor must have verified `consumer_refs` or a structured reviewed no-consumer disposition containing owner, category, review reference, and expiry.
- Do not promote deprecated umbrella Capabilities or create replacement `operation + arguments` umbrellas.
- Runtime evidence must use an authoritative persistent store and a trusted configured release signer; development/unit signers and caller-supplied pass values are forbidden.
- Runtime signing is the final mutation. Any later source, Catalog, Provider, evidence, waiver, approval, or test change invalidates the signed report.
- Preserve unrelated untracked files, never use force push, and stage only the files listed by the current task.
- Reports and command output must not contain passwords, tokens, private keys, confirmation tokens, or authenticated remote URLs.

## File Map

| Responsibility | Files |
|---|---|
| Shared stable target resolution | `backend/capability_v2/catalog_targets.py`, route/function/orchestration auditors |
| Five-family legacy route repair | `docs/governance/legacy-route-target-mappings.json`, its schema, repair/check script |
| Complete Web API classification | `backend/capability_v2/consumer_routes.py`, operations exclusion registry, generated Web inventory |
| Consumer evidence | `backend/capability_v2/consumer_evidence.py`, evidence schema/artifact, Catalog builder/auditor |
| Business/Task Tool/BFF ledgers | three existing registry files and schemas, orchestration auditor |
| Reproducible audit | `backend/capability_v2/audit_report.py`, generator/verifier script, audit Markdown |
| Controlled runtime attestation | `backend/scripts/run_capability_governance_controlled_release.py`, completion and artifact validation |

---

### Task 1: Shared Stable Catalog Target Resolver

**Files:**
- Create: `backend/capability_v2/catalog_targets.py`
- Create: `backend/tests/test_capability_v2_catalog_targets.py`
- Modify: `backend/capability_v2/route_inventory.py`
- Modify: `backend/capability_v2/orchestration_audit.py`
- Modify: `backend/scripts/build_user_function_registry.py`
- Modify: `backend/capability_v2/completion.py`
- Test: `backend/tests/test_capability_v2_route_inventory.py`
- Test: `backend/tests/test_capability_v2_orchestration_audit.py`
- Test: `backend/tests/test_user_function_registry.py`

**Interfaces:**
- Produces: `CatalogTargetIndex.from_catalog(payload) -> CatalogTargetIndex` and `resolve_stable(capability_id, major_version, expected_owner) -> TargetResolution`.
- Produces: stable reason codes `target_missing`, `target_not_stable`, `target_owner_mismatch`, and `target_replaced`.
- Consumes: the current Catalog JSON shape and atomicity dispositions already loaded by completion checks.

- [ ] **Step 1: Add failing resolver tests**

```python
def test_resolve_stable_rejects_deprecated_and_cross_domain():
    index = CatalogTargetIndex.from_catalog({"capabilities": [
        {"id": "craft.old.read", "major_version": 1, "lifecycle": "deprecated", "owner": "craft"},
        {"id": "project.scope.read", "major_version": 1, "lifecycle": "stable", "owner": "project"},
    ]})
    assert index.resolve_stable("craft.old.read", 1, "craft").reason_code == "target_not_stable"
    assert index.resolve_stable("project.scope.read", 1, "craft").reason_code == "target_owner_mismatch"

def test_resolve_stable_accepts_exact_version_and_owner():
    index = CatalogTargetIndex.from_catalog({"capabilities": [
        {"id": "craft.bop.read", "major_version": 1, "lifecycle": "stable", "owner": "craft"},
    ]})
    assert index.resolve_stable("craft.bop.read", 1, "craft").ok is True
```

- [ ] **Step 2: Verify the new tests fail for the missing module**

Run: `python -m pytest backend/tests/test_capability_v2_catalog_targets.py -q`

Expected: FAIL because `backend.capability_v2.catalog_targets` does not exist.

- [ ] **Step 3: Implement the focused resolver**

```python
@dataclass(frozen=True)
class TargetResolution:
    ok: bool
    capability_id: str
    major_version: int
    reason_code: str | None = None
    actual_owner: str | None = None
    lifecycle: str | None = None

class CatalogTargetIndex:
    @classmethod
    def from_catalog(cls, payload: Mapping[str, object], *, replacements: Mapping[tuple[str, int], str] | None = None) -> "CatalogTargetIndex": ...

    def resolve_stable(self, capability_id: str, major_version: int, expected_owner: str) -> TargetResolution: ...
```

Normalize owner from the Catalog's authoritative owner field, reject duplicate `(id, major)` keys during construction, and check existence → lifecycle → owner → replacement in that order.

- [ ] **Step 4: Make all target-bearing audits use the resolver**

Add `migration_target_major_version: int = 1` to `RouteInventoryEntry`. Change `audit_route_inventory`, `audit_orchestration_registry`, and `registry_errors` to accept the same `CatalogTargetIndex`; emit the resolver reason code plus the exact route/function/ledger entry. Update `_route_inventory_failures()` to load the index once and pass it through.

- [ ] **Step 5: Add integration regression cases**

```python
def test_route_inventory_blocks_deprecated_target(catalog_index):
    failures = audit_route_inventory([deprecated_entry], catalog_index=catalog_index)
    assert failures[0].reason_code == "target_not_stable"

def test_user_function_strict_mode_blocks_non_stable_target(tmp_path):
    errors = registry_errors(existing, discovered, catalog_index=index)
    assert any(error["reason_code"] == "target_not_stable" for error in errors)
```

- [ ] **Step 6: Run the focused suite**

Run: `python -m pytest backend/tests/test_capability_v2_catalog_targets.py backend/tests/test_capability_v2_route_inventory.py backend/tests/test_capability_v2_orchestration_audit.py backend/tests/test_user_function_registry.py -q`

Expected: PASS, including explicit deprecated and owner-mismatch failures.

- [ ] **Step 7: Commit the lifecycle gate**

```powershell
git add -- backend/capability_v2/catalog_targets.py backend/capability_v2/route_inventory.py backend/capability_v2/orchestration_audit.py backend/capability_v2/completion.py backend/scripts/build_user_function_registry.py backend/tests/test_capability_v2_catalog_targets.py backend/tests/test_capability_v2_route_inventory.py backend/tests/test_capability_v2_orchestration_audit.py backend/tests/test_user_function_registry.py
git commit -m "feat: enforce stable capability targets"
```

### Task 2: Batch-Repair the 81 Deprecated Legacy Route Targets

**Files:**
- Create: `docs/governance/legacy-route-target-mappings.schema.json`
- Create: `docs/governance/legacy-route-target-mappings.json`
- Create: `backend/scripts/repair_legacy_route_targets.py`
- Create: `backend/tests/test_repair_legacy_route_targets.py`
- Modify: `docs/governance/legacy_route_inventory.json`
- Modify: generated route review artifacts reported by `git status` after the repair command

**Interfaces:**
- Consumes: `CatalogTargetIndex.resolve_stable(...)` from Task 1.
- Produces: `load_mapping_families(path) -> tuple[RouteTargetFamily, ...]` and `repair_inventory(inventory, families, catalog_index) -> RepairResult`.
- Produces: exactly five reviewed mapping families keyed by method plus normalized route-resource pattern.

- [ ] **Step 1: Encode schema and failing family tests**

The schema must require `family_id`, `source_capability_id`, `source_major_version`, `route_method`, `route_pattern`, `target_capability_id`, `target_major_version`, `owner`, and `review_reference`. Add tests asserting duplicate route keys, a deprecated replacement, and a cross-owner replacement are rejected.

```python
def test_mapping_file_contains_five_complete_families():
    families = load_mapping_families(MAPPING_PATH)
    assert {f.source_capability_id for f in families} == {
        "craft.manufacturing_resource.change.apply",
        "craft.manufacturing_resource.read",
        "craft.gbop.change.apply",
        "craft.gbop.read",
        "project.craft_scope.read",
    }
```

- [ ] **Step 2: Verify repair tests fail**

Run: `python -m pytest backend/tests/test_repair_legacy_route_targets.py -q`

Expected: FAIL because the mapping loader and repair script do not exist.

- [ ] **Step 3: Implement deterministic check/write modes**

```python
@dataclass(frozen=True)
class RepairResult:
    updated: int
    unchanged: int
    unmatched: tuple[str, ...]
    counts_by_source: Mapping[str, int]

def repair_inventory(inventory, families, catalog_index) -> RepairResult:
    # Match method and normalized path once, resolve target as stable, then persist id+major.
    ...
```

CLI behavior: default `--check` exits non-zero when the checked-in inventory differs; `--write` updates atomically. Both modes print the five source-group counts and fail when total matched is not 81.

- [ ] **Step 4: Populate reviewed mappings and perform one batch rewrite**

For each of the five source families, inspect the exact methods/resources and atomicity dispositions, map to an existing stable atomic outcome, and record the review reference. Do not map a route merely because names are similar. If no stable outcome exists, remove/retire the legacy exposure or add the reviewed operations exclusion required by Task 3.

Run: `python backend/scripts/repair_legacy_route_targets.py --write`

Expected: `updated=81`, source counts `37, 11, 24, 8, 1`, `unmatched=0`.

- [ ] **Step 5: Prove zero non-stable route targets**

Run: `python backend/scripts/repair_legacy_route_targets.py --check`

Run: `python backend/scripts/check_capability_v2_completion.py --static-only`

Expected: repair check PASS and lifecycle finding count is 0. If the completion CLI has no `--static-only`, add that flag as a read-only alias for the existing static evaluation path and test it in `backend/tests/test_capability_v2_completion.py`.

- [ ] **Step 6: Commit the five-family repair**

Stage the mapping schema/data, script/tests, inventory, and only regenerated route review artifacts shown as consequences of this command.

```powershell
git commit -m "fix: migrate deprecated legacy route targets"
```

### Task 3: Discover and Classify Every Frontend `/api/` Route

**Files:**
- Create: `docs/governance/web-api-operations-exclusions.schema.json`
- Create: `docs/governance/web-api-operations-exclusions.json`
- Modify: `backend/capability_v2/consumer_routes.py`
- Modify: `backend/scripts/check_web_capability_routes.py`
- Modify: `backend/capability_v2/completion.py`
- Modify: `docs/governance/capability-coverage-review/generated/web_route_inventory.json`
- Test: `backend/tests/test_capability_v2_consumer_routes.py`
- Test: `backend/tests/test_capability_v2_completion.py`

**Interfaces:**
- Produces: `scan_web_api_routes(roots, legacy_index, bff_index, exclusions, frontend_revision) -> RouteScanReport`.
- Produces dispositions `capability`, `legacy_registered`, `bff_registered`, `operations_excluded`, `unresolved`.
- Produces report fields `frontend_revision`, `content_hash`, `scan_roots`, `excluded_roots`, `counts`, and normalized occurrence identities.

- [ ] **Step 1: Add failing all-route discovery tests**

```python
def test_scanner_discovers_api_outside_configured_prefixes(tmp_path):
    source = tmp_path / "web" / "agent.js"
    source.parent.mkdir()
    source.write_text("fetch('/api/agents/' + agentId)", encoding="utf-8")
    report = scan_web_api_routes([tmp_path / "web"], empty_indexes, [], "abc123")
    assert report.routes[0].normalized_route == "/api/agents/{dynamic}"
    assert report.routes[0].disposition == "unresolved"

def test_ambiguous_method_is_unresolved():
    assert occurrence_for("client.request('/api/tasks')").disposition == "unresolved"
```

- [ ] **Step 2: Verify the focused scanner tests fail**

Run: `python -m pytest backend/tests/test_capability_v2_consumer_routes.py -q`

Expected: FAIL because discovery is still prefix-limited or the new report fields are absent.

- [ ] **Step 3: Implement full discovery and exact disposition joins**

Change prefix configuration from a discovery predicate to optional classification metadata. Scan source files under `web/` and `packages/`, excluding only dependency folders, tests, generated bundles, and build output. Normalize templates conservatively; ambiguous method/path becomes `unresolved`. Join by `(method, normalized_route)` against Capability Gateway routes, legacy inventory, BFF registry, and active operations exclusions; require exactly one disposition.

- [ ] **Step 4: Add reviewed operations exclusions**

The exclusion schema requires `route_method`, `normalized_route`, `owner`, `reason`, `approval_reference`, and ISO `expires_at`. Reject expired, duplicate, wildcard, ownerless, or empty-approval records. Populate it only for health/admin/auth/file-transfer endpoints that are demonstrably non-business operations; business routes must use a governed inventory.

- [ ] **Step 5: Regenerate the authoritative inventory from frontend `test`**

```powershell
python backend/scripts/check_web_capability_routes.py --web-root 'E:\Projects\ai00\workmanship-web' --write
python backend/scripts/check_web_capability_routes.py --web-root 'E:\Projects\ai00\workmanship-web' --check --fail-on-unresolved
```

Expected: all `/api/` occurrences are present, `unresolved=0`, and `frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9` unless a reviewed frontend commit was created during remediation.

- [ ] **Step 6: Make completion fail on drift, omission, or unresolved entries**

Add regression tests that delete one stored occurrence, alter the frontend revision, and leave one unresolved occurrence; each must produce a distinct blocking reason code. Ensure a fresh scan equals the stored artifact byte-for-byte after canonical JSON serialization.

- [ ] **Step 7: Run and commit Web coverage**

Run: `python -m pytest backend/tests/test_capability_v2_consumer_routes.py backend/tests/test_capability_v2_completion.py -q`

Run: `python backend/scripts/check_web_capability_routes.py --web-root 'E:\Projects\ai00\workmanship-web' --check --fail-on-unresolved`

Expected: PASS and unresolved count 0.

```powershell
git commit -m "feat: govern complete web api route coverage"
```

### Task 4: Generate Verified Consumer Evidence and Enforce It in Catalog

**Files:**
- Create: `backend/capability_v2/consumer_evidence.py`
- Create: `backend/scripts/build_capability_consumer_evidence.py`
- Create: `backend/tests/test_capability_consumer_evidence.py`
- Create: `docs/governance/capability-consumer-evidence.schema.json`
- Create: `docs/governance/capability-consumer-evidence.json`
- Create: `docs/governance/capability-no-consumer-dispositions.schema.json`
- Create: `docs/governance/capability-no-consumer-dispositions.json`
- Modify: `backend/scripts/build_capability_catalog.py`
- Modify: `backend/capability_v2/catalog.py`
- Modify: `backend/capability_v2/catalog_audit.py`
- Test: `backend/tests/test_capability_v2_catalog_audit.py`
- Test: `backend/tests/test_capability_catalog_release.py`

**Interfaces:**
- Produces: `build_consumer_evidence(inputs: EvidenceInputs) -> ConsumerEvidenceReport`.
- Produces records keyed by `(capability_id, major_version, consumer_id, source_path)` with `consumer_type`, `version_constraint`, and `source_hash`.
- Consumes: Task 3 Web report, Python boundary discovery, plugin/Agent/MCP/worker manifests, and orchestration registries.

- [ ] **Step 1: Add evidence canonicalization and stale-source tests**

```python
def test_evidence_record_hashes_the_referenced_source(tmp_path):
    path = tmp_path / "consumer.js"
    path.write_text("invoke('craft.bop.read@1')", encoding="utf-8")
    record = evidence_for(path, "craft.bop.read", 1, "web")
    assert record.source_hash.startswith("sha256:")

def test_catalog_audit_rejects_empty_refs_without_structured_disposition():
    findings = audit_catalog(stable_descriptor(consumer_refs=[], no_consumer_reason=None))
    assert "consumer_evidence_missing" in {f.reason_code for f in findings}
```

- [ ] **Step 2: Verify evidence tests fail**

Run: `python -m pytest backend/tests/test_capability_consumer_evidence.py backend/tests/test_capability_v2_catalog_audit.py -q`

Expected: FAIL because evidence generation and structured exception validation are absent.

- [ ] **Step 3: Implement deterministic evidence collection**

```python
@dataclass(frozen=True)
class ConsumerEvidenceRecord:
    capability_id: str
    major_version: int
    consumer_id: str
    consumer_type: Literal["web", "backend", "plugin", "agent", "mcp", "worker", "task_tool", "bff", "business"]
    version_constraint: str
    source_path: str
    source_hash: str
```

Reject missing source files, mismatched hashes, unknown Capability versions, exposure-only metadata, and duplicate keys. Sort canonically and compute one artifact content hash over the records and all input hashes.

- [ ] **Step 4: Replace hard-coded Catalog consumer refs**

Remove `_verified_consumer_refs()` from `build_capability_catalog.py`. Load the generated evidence artifact and join by exact `(id, major)`. Change `complete_governance_metadata` so it never invents the generic sentence “No verified consumer is registered”; it must receive either verified records or a checked structured disposition.

- [ ] **Step 5: Review the current 394 empty descriptors as a batch**

Run the generator once to attach all discoverable real consumers. For the remainder, create finite reviewed dispositions with schema:

```json
{
  "capability_id": "example.capability",
  "major_version": 1,
  "owner": "example-domain",
  "category": "provider_internal|planned|compatibility_only|retirement_candidate",
  "review_reference": "review:2026-08-26/...",
  "expires_at": "2026-11-26"
}
```

Do not invent consumer IDs to make the count zero. The target is zero unaccounted descriptors, not 440 populated refs.

- [ ] **Step 6: Regenerate Catalog-derived artifacts and prove closure**

```powershell
python backend/scripts/build_capability_consumer_evidence.py --write --web-root 'E:\Projects\ai00\workmanship-web'
python backend/scripts/build_capability_consumer_evidence.py --check --web-root 'E:\Projects\ai00\workmanship-web'
python backend/scripts/build_capability_catalog.py
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
```

Expected: every stable descriptor has at least one verified record or one active structured disposition; all generated artifacts are current.

- [ ] **Step 7: Run tests and commit consumer evidence**

Run: `python -m pytest backend/tests/test_capability_consumer_evidence.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/test_capability_catalog_release.py -q`

Expected: PASS.

```powershell
git commit -m "feat: generate verified capability consumer evidence"
```

### Task 5: Govern Business, Task Tool, and BFF Orchestration Registries

**Files:**
- Modify: `docs/governance/business-capability-ledger.schema.json`
- Modify: `docs/governance/task-tool-registry.schema.json`
- Modify: `docs/governance/bff-capability-registry.schema.json`
- Modify: `docs/governance/business_capability_ledger.json`
- Modify: `docs/governance/task_tool_registry.json`
- Modify: `docs/governance/bff_capability_registry.json`
- Modify: `backend/capability_v2/orchestration_audit.py`
- Test: `backend/tests/test_capability_v2_orchestration_audit.py`

**Interfaces:**
- Consumes: `CatalogTargetIndex` from Task 1 and consumer evidence records from Task 4.
- Produces: exact versioned orchestration edges with owner, bounded input/output contract, source evidence, and stable audit results.

- [ ] **Step 1: Add failing schema/audit cases**

```python
def test_task_tool_requires_versioned_stable_targets(catalog_index):
    findings = audit_orchestration_registry({"capabilities": [{"capability_id": "craft.old.read"}]}, catalog_index)
    assert {f.reason_code for f in findings} >= {"target_version_missing"}

def test_cross_domain_orchestration_edge_requires_reviewed_boundary(catalog_index):
    findings = audit_orchestration_registry(cross_domain_entry_without_boundary, catalog_index)
    assert findings[0].reason_code == "cross_domain_boundary_missing"
```

- [ ] **Step 2: Verify orchestration tests fail**

Run: `python -m pytest backend/tests/test_capability_v2_orchestration_audit.py -q`

Expected: FAIL on missing version/source/boundary validation.

- [ ] **Step 3: Extend all three schemas and audit rules**

Require `capability_id`, `major_version`, `owner`, `source_path`, and `source_hash` for every atomic edge. Business entries additionally require a user outcome; Task Tools require bounded input/output schemas; BFF entries require an aggregation rationale and constituent versioned targets. Validate lifecycle, owner, duplicates, source hashes, and reviewed cross-domain boundaries.

- [ ] **Step 4: Discover real orchestration entry points and update ledgers**

Use source search results from Task 4 to add only real business workflows, callable Agent/Task Tool operations, and reviewed BFF aggregations. Do not create one ledger row per atomic Capability. Record an explicit reviewed coverage disposition for each discovered orchestration entry point that is intentionally not a ledger node.

- [ ] **Step 5: Regenerate consumer evidence after ledger changes**

Run: `python backend/scripts/build_capability_consumer_evidence.py --write --web-root 'E:\Projects\ai00\workmanship-web'`

Run: `python backend/scripts/build_capability_catalog.py`

Expected: orchestration consumers flow into exact descriptor `consumer_refs`; no hard-coded counts are used.

- [ ] **Step 6: Run audits and commit**

Run: `python -m pytest backend/tests/test_capability_v2_orchestration_audit.py backend/tests/test_capability_consumer_evidence.py -q`

Run: `python backend/scripts/check_capability_v2_completion.py --static-only`

Expected: invalid/non-stable orchestration references 0 and no unreviewed discovered entry points.

```powershell
git commit -m "feat: govern capability orchestration ledgers"
```

### Task 6: Generate and Verify a Reproducible Static Audit Report

**Files:**
- Create: `backend/capability_v2/audit_report.py`
- Create: `backend/scripts/generate_capability_governance_audit.py`
- Create: `backend/tests/test_capability_governance_audit_report.py`
- Modify: `docs/audits/2026-08-26-atomic-capability-code-audit.md`

**Interfaces:**
- Produces: `collect_audit_inputs(backend_root, frontend_root) -> AuditInputManifest`.
- Produces: `render_static_audit(manifest, results) -> str` and `verify_audit(report_path, current_manifest) -> AuditVerification`.
- Consumes: clean Git SHAs, Catalog release/hash, Provider hashes, route/Web/consumer/orchestration artifacts, validation command results, and static gate result.

- [ ] **Step 1: Add clean-state, exact-SHA, and stale-report tests**

```python
def test_report_binds_full_backend_and_frontend_sha(fake_repos):
    manifest = collect_audit_inputs(*fake_repos)
    report = render_static_audit(manifest, passing_results())
    assert manifest.backend_sha in report
    assert manifest.frontend_sha in report

def test_verifier_marks_changed_evidence_stale(report, changed_manifest):
    assert verify_audit(report, changed_manifest).status == "stale"
```

- [ ] **Step 2: Verify audit report tests fail**

Run: `python -m pytest backend/tests/test_capability_governance_audit_report.py -q`

Expected: FAIL because the generator module is absent.

- [ ] **Step 3: Implement immutable manifest collection**

```python
@dataclass(frozen=True)
class AuditInputManifest:
    backend_sha: str
    frontend_sha: str
    catalog_release_id: str
    catalog_hash: str
    provider_hashes: Mapping[str, str]
    evidence_hashes: Mapping[str, str]
    generated_at: str
    input_manifest_hash: str
```

Formal generation refuses dirty backend or frontend worktrees. The report must derive all counts from parsed artifacts, capture every validation command and exit status, and show runtime attestation as `pending` until Task 8 supplies matching evidence.

- [ ] **Step 4: Add `--write` and `--verify` CLI modes**

`--write` runs the documented static commands, exits on the first failure, then writes canonical Markdown. `--verify` recomputes the manifest and returns non-zero for dirty, stale, missing, or mismatched inputs. Neither mode reads prose constants from the old report.

- [ ] **Step 5: Commit source/artifacts before generating the formal report**

Run: `git status --short`

Expected: only intended Task 6 source/test changes are present. Commit those first so the report can bind to a real backend SHA:

```powershell
git commit -m "feat: add reproducible capability audit reporting"
```

- [ ] **Step 6: Generate and verify the report against exact commits**

```powershell
python backend/scripts/generate_capability_governance_audit.py --backend-root . --frontend-root 'E:\Projects\ai00\workmanship-web' --write docs/audits/2026-08-26-atomic-capability-code-audit.md
python backend/scripts/generate_capability_governance_audit.py --backend-root . --frontend-root 'E:\Projects\ai00\workmanship-web' --verify docs/audits/2026-08-26-atomic-capability-code-audit.md
```

Expected: report names full current SHAs, verification `current`, static result `pass`, runtime result `pending`.

- [ ] **Step 7: Commit the generated report, then regenerate once**

Commit the report, rerun `--write` so its backend SHA becomes the report commit, and amend only the report. Verify again; this two-pass rule prevents a report that points to its parent commit.

```powershell
git add -- docs/audits/2026-08-26-atomic-capability-code-audit.md
git commit -m "docs: publish current capability code audit"
python backend/scripts/generate_capability_governance_audit.py --backend-root . --frontend-root 'E:\Projects\ai00\workmanship-web' --write docs/audits/2026-08-26-atomic-capability-code-audit.md
git add -- docs/audits/2026-08-26-atomic-capability-code-audit.md
git commit --amend --no-edit
```

The generator must define its bound backend revision as the tree/content revision excluding the report's self-referential bytes, or equivalently record the commit and report blob in a detached manifest. Test this explicitly so amend does not create an endless SHA loop.

### Task 7: Build the Controlled Runtime Attestation Command

**Files:**
- Create: `backend/scripts/run_capability_governance_controlled_release.py`
- Create: `backend/tests/test_capability_governance_controlled_release.py`
- Modify: `backend/scripts/check_capability_v2_completion.py`
- Modify: `backend/scripts/build_capability_v2_production_artifact.py`
- Modify only if required by failing tests: `backend/capability_governance_test/service.py`
- Test: `backend/tests/test_capability_governance_execution_ports.py`
- Test: `backend/tests/test_capability_governance_release_gate.py`
- Test: `backend/tests/test_capability_v2_production_artifact.py`

**Interfaces:**
- Produces CLI inputs `--gateway-url`, `--authority-store`, `--release-key-id`, `--trusted-keyring`, `--input-manifest`, and `--output-report`.
- Consumes official Gateway capabilities `base.capability_scan.run`, `base.capability_test.run`, and `base.capability_release_gate.evaluate`.
- Produces a persisted, read-back, signature-verified release report bound to the Task 6 input manifest.

- [ ] **Step 1: Add failure-first controlled-release tests**

```python
@pytest.mark.parametrize("store_kind", ["memory", "unit-test"])
def test_controlled_release_rejects_non_authoritative_store(store_kind): ...

def test_controlled_release_rejects_skipped_component(fake_gateway):
    fake_gateway.test_result.components[0].status = "skipped"
    assert run_controlled_release(fake_gateway, config).reason_code == "runtime_component_not_executed"

def test_controlled_release_reads_back_and_verifies_signature(fake_gateway): ...
```

- [ ] **Step 2: Verify controlled release tests fail**

Run: `python -m pytest backend/tests/test_capability_governance_controlled_release.py -q`

Expected: FAIL because the orchestrator does not exist.

- [ ] **Step 3: Implement the fail-closed orchestration sequence**

```python
def run_controlled_release(gateway: CapabilityGatewayClient, config: ControlledReleaseConfig) -> ControlledReleaseResult:
    pinned = verify_clean_and_pin_inputs(config)
    snapshot = gateway.invoke("base.capability_scan.run", {"input_manifest_hash": pinned.hash})
    test_run = gateway.invoke("base.capability_test.run", {"snapshot_gid": snapshot.gid})
    require_all_components_executed(test_run, snapshot, pinned)
    report = gateway.invoke("base.capability_release_gate.evaluate", {"test_run_gid": test_run.gid, "input_manifest_hash": pinned.hash})
    persisted = gateway.read_release_report(report.gid)
    verify_report_hash_signature_and_inputs(persisted, config.trusted_keyring, pinned)
    return ControlledReleaseResult(snapshot.gid, test_run.gid, persisted.gid, persisted.report_hash)
```

Reject dirty repos, missing trusted key IDs, development/unit signer IDs, memory stores, caller-supplied conclusions, missing persisted rows, required `not_run`/`skipped`, stale timestamps/hashes, and any manifest mismatch.

- [ ] **Step 4: Harden completion and production artifact validation**

Require live mode, the exact required section set, trusted signature, report hash, snapshot/test/report GIDs, zero skipped required components, and exact Task 6 manifest match. Add one regression test per rejection reason and ensure error output includes identities but no secrets.

- [ ] **Step 5: Run the runtime unit/integration contract suite**

Run: `python -m pytest backend/tests/test_capability_governance_controlled_release.py backend/tests/test_capability_governance_execution_ports.py backend/tests/test_capability_governance_release_gate.py backend/tests/test_capability_v2_production_artifact.py -q`

Expected: PASS using fakes/test fixtures only; no production or controlled store is mutated by this test command.

- [ ] **Step 6: Commit the controlled runner**

```powershell
git commit -m "feat: add controlled capability release attestation"
```

### Task 8: Final Static Verification, Controlled Attestation, and Release Artifact

**Files:**
- Modify: `docs/audits/2026-08-26-atomic-capability-code-audit.md`
- Create in an ignored secure output directory: signed runtime report and production artifact generated by existing scripts
- Do not commit: private keys, credentials, authenticated URLs, local database files, or unredacted service logs

**Interfaces:**
- Consumes: all Tasks 1-7 plus controlled-environment connection/signing configuration supplied outside the repository.
- Produces: exact `snapshot_gid`, `test_run_gid`, `release_report_gid`, report hash/signature verification, and production artifact hash.

- [ ] **Step 1: Run the complete backend static suite**

```powershell
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/build_user_function_registry.py --strict
python backend/scripts/check_domain_dependencies.py
python backend/scripts/check_web_capability_routes.py --web-root 'E:\Projects\ai00\workmanship-web' --check --fail-on-unresolved
python backend/scripts/build_capability_consumer_evidence.py --check --web-root 'E:\Projects\ai00\workmanship-web'
python backend/scripts/check_capability_v2_completion.py --static-only
python -m pytest backend/tests/test_capability_v2_catalog_targets.py backend/tests/test_capability_v2_route_inventory.py backend/tests/test_capability_v2_consumer_routes.py backend/tests/test_capability_consumer_evidence.py backend/tests/test_capability_v2_orchestration_audit.py backend/tests/test_capability_governance_audit_report.py backend/tests/test_capability_governance_controlled_release.py -q
```

Expected: every command exits 0; non-stable targets 0, unresolved Web routes 0, unaccounted stable consumers 0, invalid orchestration references 0.

- [ ] **Step 2: Run frontend checks at the pinned frontend commit**

```powershell
npm ci
npm run build:web
```

Run from: `E:\Projects\ai00\workmanship-web`

Expected: dependency install and production Web build PASS. Run any repository-defined unit/lint command listed in `package.json` that is part of the existing `test` gate and record its exact exit status in the audit.

- [ ] **Step 3: Commit final generated static evidence and require clean repos**

Regenerate consumer/Catalog/Web/audit artifacts after the last source change, commit them normally, then run:

```powershell
git status --short
git rev-parse HEAD
git -C 'E:\Projects\ai00\workmanship-web' status --short
git -C 'E:\Projects\ai00\workmanship-web' rev-parse HEAD
```

Expected: both status outputs empty and both full SHAs match the audit input manifest.

- [ ] **Step 4: Run authoritative scan, test, and release gate in the controlled environment**

```powershell
python backend/scripts/run_capability_governance_controlled_release.py --gateway-url $env:AI00_GOVERNANCE_GATEWAY_URL --authority-store $env:AI00_GOVERNANCE_STORE --release-key-id $env:AI00_RELEASE_KEY_ID --trusted-keyring $env:AI00_RELEASE_TRUSTED_KEYRING --input-manifest .runtime/capability-audit-input-manifest.json --output-report .runtime/capability-release-report.json
```

Expected: one line containing non-empty `snapshot_gid`, `test_run_gid`, `release_report_gid`, `report_hash`, `conclusion=pass`, and `signature=verified`. Stop without weakening the gate if controlled store or signing authority is unavailable.

- [ ] **Step 5: Verify completion and build the bound production artifact**

```powershell
python backend/scripts/check_capability_v2_completion.py --release-report .runtime/capability-release-report.json --trusted-keyring $env:AI00_RELEASE_TRUSTED_KEYRING
python backend/scripts/build_capability_v2_production_artifact.py --release-report .runtime/capability-release-report.json --trusted-keyring $env:AI00_RELEASE_TRUSTED_KEYRING
```

Expected: completion PASS and artifact manifest contains the same report hash, input manifest hash, backend SHA, frontend SHA, Catalog hash, Provider hashes, and consumer evidence hash.

- [ ] **Step 6: Attach runtime identifiers to the audit without invalidating inputs**

Generate the runtime section from the verified report; do not hand-edit conclusions or IDs. Re-run audit verification and production artifact verification. The runtime attachment must be outside the source tree hash or represented by the detached manifest scheme tested in Task 6.

- [ ] **Step 7: Final review and integration handoff**

Run: `git log --oneline --decorate -10`

Run: `git diff --check HEAD~8..HEAD`

Expected: one reviewable commit per work package, no whitespace errors, no secrets, and no unrelated files. Present the exact SHAs, four zero-count gate metrics, runtime GIDs, report hash, signature key ID, and artifact hash before any push/merge request.
