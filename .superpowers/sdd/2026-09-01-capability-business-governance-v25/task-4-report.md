# Task 4 Report: Scan Authoritative Capability Business Evidence

## Status

Complete. The scanner now reads only the approved `business_effect`, normalizes business rules/scopes into a deterministic `CapabilityFingerprint`, emits A-G layer evidence and an L0-L6-compatible maturity candidate, and converts parser/configuration failures into immutable blocking scan findings. Registry reads project this evidence through the existing closed `contract` envelope.

## Commit

- `4c610f8e` — `feat: scan authoritative capability business evidence`

## RED Evidence

Command:

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py -q
```

Result before production changes: exit 1; 6 failed in 0.91s. Failures proved that the scanner substituted `description`, lacked business maturity/fingerprint/layer evidence, omitted structured syntax findings, and raised `official_domain_manifests_required` instead of returning a report.

The provider projection test was also run before its service change:

```text
python -m pytest backend/tests/test_capability_governance_provider.py -q -k scanned_business_evidence
```

Result: exit 1; 1 failed, 19 deselected in 0.94s because the closed registry item had no `contract` business evidence.

## GREEN Evidence

Required focused command, post-commit:

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_provider.py -q
```

Result: exit 0; 27 passed in 3.41s.

Compatibility command:

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_test_profile.py backend/tests/test_capability_identity_projection.py backend/tests/test_capability_governance_business_store.py -q
```

Result: exit 0; 50 passed in 4.78s.

CLI command:

```text
python backend/scripts/run_capability_governance_scan.py --help
```

Result: exit 0; argparse displayed the offline scan usage and required output option.

Syntax and staged-diff commands:

```text
python -m compileall -q backend/capability_governance_test/models.py backend/capability_governance_test/scanner.py backend/capability_governance_test/service.py backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_provider.py
git diff --cached --check
```

Result: both exited 0 with no output.

## Implementation Notes

- `business_effect` is stripped from the authoritative Catalog field; `description` and `title` are never fallbacks.
- Empty and generated/template purposes remain registered at L1 with `missing_business_effect` or `generated_business_effect` evidence.
- Rule IDs, scopes, enforcement references, and test references are sorted before fingerprint/evidence construction. No AI, dependency, or central rule engine participates.
- Every scanned Capability contains A-G evidence keys. Scanner-observable completeness can advance through L3; later review, release, and runtime tasks own L4-L6 evidence.
- Syntax failures become `scan_parser_error` findings with the repository-relative source path. Invalid manifests/catalog inputs become blocking configuration findings and an otherwise valid, hashable empty `SnapshotDocument`.
- Business rules, fingerprints, layer evidence, maturity, and scan findings are immutable and included in snapshot serialization/hashing.
- Registry search joins persisted entries to the pinned snapshot document and transports the business evidence under the existing bounded `contract` object.

## Files

- `backend/capability_governance_test/models.py`
- `backend/capability_governance_test/scanner.py`
- `backend/capability_governance_test/service.py` (only Task 4 hunks committed)
- `backend/tests/test_capability_governance_business_scanner.py` (new)
- `backend/tests/test_capability_governance_provider.py` (only the Task 4 test committed)

## Concerns

- The scanner intentionally cannot award L4-L6: relationship disposition, exact-hash human approval/release verification, and real runtime effectiveness are owned by later tasks.
- `service.py` and `test_capability_governance_provider.py` still contain unrelated pre-existing static-gate working-tree edits. They were preserved and remain unstaged after `4c610f8e`.
- No live database migration or network operation was performed.

## Fix Round 1 (2026-09-01)

### Status and Commit

Complete. Commit `ed35fafa` (`fix: preserve blocking governance scan evidence`) addresses all five Important review findings without modifying the existing immutable test-governance migrations or any production table. The existing `workmanship_base_capability_scan_runs` and `workmanship_base_capability_findings` test-governance tables provide the required additive persistence boundary.

### RED Evidence

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py -q --tb=short
```

Result before fix implementation: exit 1; `8 failed, 3 passed in 0.95s`. Failures covered non-total snapshot ordering, unresolved references incorrectly yielding L3, missing blocked status, invalid string elements and duplicate rule identities not becoming structured configuration evidence, and the broken legacy positional descriptor contract.

```text
python -m pytest backend/tests/test_capability_governance_store.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_scanner.py::test_offline_cli_emits_blocked_report_and_exits_nonzero backend/tests/test_capability_governance_acceptance.py::test_release_acceptance_legacy_positional_capabilities_keep_descriptors -q --tb=short
```

Result before fix implementation: exit 1; `5 failed, 30 passed in 3.87s`. Failures covered absent blocked status/persistence, lost SQL scan findings/business evidence, provider read reachability, and the CLI returning zero for a blocked report.

### GREEN Evidence

Fresh final focused verification:

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_scanner.py::test_offline_cli_emits_blocked_report_and_exits_nonzero backend/tests/test_capability_governance_acceptance.py::test_release_acceptance_legacy_positional_capabilities_keep_descriptors backend/tests/test_capability_governance_migrations.py -q --tb=short --basetemp=E:/Projects/ai00_v3/.runtime/task4-final
```

Result: exit 0; `52 passed in 7.39s`.

Post-commit repetition with `--basetemp=E:/Projects/ai00_v3/.runtime/task4-postcommit`: exit 0; `52 passed in 7.40s`. `git show --check --oneline --stat HEAD` also exited 0 for `ed35fafa`.

```text
python -m compileall -q backend/capability_governance_test backend/scripts/run_capability_governance_scan.py
python backend/scripts/run_capability_governance_scan.py --help
git diff --cached --check
```

Result: all exited 0. Compile and staged-diff checks produced no errors; CLI help displayed the bounded offline scan usage and required output option.

### Fix Notes

- Restored `descriptor` as the original thirteenth positional `ScannedCapability` argument; new additive business fields follow it. SQL rehydration now uses keyword construction and restores every business evidence field.
- L3 requires every declared enforcement reference to resolve to a scanned provider/port/repository/handler symbol and every rule test reference to resolve to an executable scanned or accepted test node. Unresolved references stay L2 with explicit reason codes.
- Scan findings and blocked run status survive both memory and SQL persistence, and finding search merges persisted scanner findings with deterministic analysis findings.
- Blocked status is serialized and hashed in `SnapshotDocument`, persisted on scan runs, exposed through the closed service/provider response contract, and makes the CLI return 1 only after emitting its structured report.
- Rule identities are unique and deterministically ordered. Duplicate identities and non-string string-list elements produce deterministic blocking configuration findings instead of input-order-sensitive hashes or `str()` coercion.

### Concerns

- The broad offline scanner and full release-acceptance suites are currently blocked by unrelated concurrent Catalog artifact/model drift: the checked-in Catalog contains `business_definition_hash`, while the working `CatalogRelease` model rejects it as an extra field (495 validation errors). Baseline full acceptance result was `2 failed, 4 passed in 4.73s`; the non-offline scanner selection was `1 failed, 15 passed` for the same cause. The focused positional release-acceptance and all Task 4 tests pass.
- Unrelated static-gate and pinned descriptor-count edits in `service.py`, `run_capability_governance_scan.py`, and `test_capability_governance_provider.py` remain in the working tree and were deliberately excluded from `ed35fafa`.

## Fix Round 2 (2026-09-01)

### Status and Commit

Complete. Commit `5aac4906` (`fix: fail closed across governance scan preflight`) addresses the three second-review Important findings.

### RED Evidence

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_store.py::test_sql_store_persists_blocked_run_and_scan_finding backend/tests/test_capability_governance_provider.py::test_blocked_scan_is_persisted_and_reachable_through_finding_provider backend/tests/test_capability_governance_provider.py::test_scan_finding_pagination_deduplicates_analysis_without_merging_evidence backend/tests/test_capability_governance_scanner.py::test_offline_cli_persists_real_catalog_validation_failure_before_exit -q --tb=short --basetemp=E:/Projects/ai00_v3/.runtime/task4-fix2-red
```

Result before production changes: exit 1; `11 failed, 11 passed in 1.37s`. The failures proved that six rule scalar fields accepted type coercion, boolean rule versions were treated as integers, invalid-rule order did not produce a blocked identity, SQL/memory finding fingerprints differed from analysis, finding totals doubled from 1 to 2 and 2 to 4, and a real Catalog validation exception escaped without a report.

### GREEN Evidence

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_scanner.py backend/tests/test_capability_governance_acceptance.py::test_release_acceptance_legacy_positional_capabilities_keep_descriptors backend/tests/test_capability_governance_migrations.py -q --tb=short -k "not offline_runner_attaches_authoritative_registry_bindings" --basetemp=E:/Projects/ai00_v3/.runtime/task4-fix2-final
```

Result: exit 0; `78 passed, 1 deselected in 7.73s`.

Post-commit repetition with `--basetemp=E:/Projects/ai00_v3/.runtime/task4-fix2-postcommit`: exit 0; `78 passed, 1 deselected in 7.86s`. `git show --check --oneline --stat HEAD` also exited 0 for `5aac4906`.

```text
python -m compileall -q backend/capability_governance_test/scanner.py backend/capability_governance_test/store.py backend/scripts/run_capability_governance_scan.py
python backend/scripts/run_capability_governance_scan.py --help
git diff --cached --check
```

Result: all exited 0; compile and staged-diff checks had no errors, and CLI help displayed the required bounded offline invocation.

Real checked-in Catalog preflight command:

```text
python backend/scripts/run_capability_governance_scan.py --offline --output .runtime/task4-fix2-real-cli.json
```

Result: exit 1 after writing the report. The emitted summary reported `scan_status=blocked` and snapshot hash `sha256:18fe6b61492289f0928da43f44133531697de4da5b02d495b325bbe0589cc0c3`; the persisted finding was `scan_configuration_error`, source `product_catalog`, reason `product_catalog_validation_error`.

### Fix Notes

- All Catalog, extension, official-domain manifest, acceptance-manifest, count/set, and registry preflight failures now enter one deterministic blocked `SnapshotDocument` writer. Third-party exception text is not hashed or exposed as finding identity.
- Business-rule identity fields require raw strings and a non-boolean integer version. Optional rule statement/condition/enforcement/error scalars, when supplied, must be raw strings. Invalid instances produce the constant `product_catalog_business_rule_scalar_invalid` finding before sorting or normalization.
- Memory and SQL persistence now use the same `finding_fingerprint` payload as analysis (`code`, severity, remediation boundary, and evidence path). Finding search therefore deduplicates scanner persistence and deterministic analysis before paging; distinct evidence paths remain distinct.

### Concerns

- Running the same focused collection without the deselection produced `1 failed, 78 passed in 8.41s`. The sole failure, `test_offline_runner_attaches_authoritative_registry_bindings`, requires a healthy Catalog; the current checked-in Catalog still has 495 `business_definition_hash` fields rejected by the concurrent `CatalogRelease` model. The command now correctly writes a blocked report rather than crashing, so an empty blocked snapshot intentionally has no `implemented_by` binding.
- The unrelated pinned descriptor-count and static-gate working-tree hunks remain excluded from `5aac4906`.

## Fix Round 3 (2026-09-01)

### Status and Commit

Complete. Commit `6104811d` (`fix: honor catalog business rule versions`) corrects the remaining author-contract boundary.

### RED Evidence

```text
python -m pytest backend/tests/test_capability_governance_business_scanner.py -q --tb=short --basetemp=E:/Projects/ai00_v3/.runtime/task4-fix3-red
```

Result before the scanner change: exit 1; `6 failed, 13 passed in 0.94s`. Real author `version` inputs produced empty blocked snapshots, invalid test-ref and duplicate tests were intercepted by the wrong missing-version error, while a descriptor containing only the undeclared persistence alias `rule_version` incorrectly scanned as completed.

### GREEN Evidence

```text
python -m pytest backend/tests/test_capability_business_definition.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_scanner.py backend/tests/test_capability_governance_acceptance.py::test_release_acceptance_legacy_positional_capabilities_keep_descriptors -q --tb=short -k "not offline_runner_attaches_authoritative_registry_bindings" --basetemp=E:/Projects/ai00_v3/.runtime/task4-fix3-final
```

Result: exit 0; `118 passed, 1 deselected in 8.99s`.

Post-commit repetition with `--basetemp=E:/Projects/ai00_v3/.runtime/task4-fix3-postcommit`: exit 0; `118 passed, 1 deselected in 8.90s`. `git show --check --oneline --stat HEAD` also exited 0 for `6104811d`.

Additional Task 1 contract probe:

```text
python -m pytest backend/tests/test_capability_v2_contracts.py backend/tests/test_capability_business_definition.py -q --tb=short --basetemp=E:/Projects/ai00_v3/.runtime/task4-fix3-contracts
```

Result: exit 0; `21 passed in 0.84s`.

```text
python -m compileall -q backend/capability_governance_test/scanner.py backend/tests/test_capability_governance_business_scanner.py
git diff --cached --check
```

Result: both exited 0 with no errors.

### Fix Notes

- Scanner validation, ordering, duplicate identity, and deterministic descriptor/snapshot hashing now consume only the author-contract `version` field.
- `version` must be an integer of at least 1 and explicitly rejects booleans. The undeclared persistence alias `rule_version` is rejected even when present alongside other valid author fields.
- Scanned author evidence retains `version` unchanged. No reverse dependency on the later `BusinessRuleRecord.rule_version` persistence field was introduced.
- Task 4 fixtures now use the actual `BusinessInvariantContract` shape. Probes cover valid author `version`, alias-only rejection, boolean rejection, duplicate identity, and input-shuffle hash stability.

### Concerns

- The known Catalog `business_definition_hash` drift and stable-count pin mismatch were deliberately not changed. The one healthy-Catalog binding test remains deselected for the same separately owned integration issue described in fix round 2.
- Unrelated dirty working-tree hunks remain excluded from `6104811d`.

## Fix Round 4 (2026-09-01)

### Status and Commit

Complete. Commit `3935bcc2` (`fix: require strict business rule versions`) closes the real author-model coercion boundary.

### RED Evidence

```text
python -m pytest backend/tests/test_capability_business_definition.py backend/tests/test_capability_governance_business_scanner.py -q --tb=short --basetemp=.runtime/task4-fix4-red
```

Result before the contract change: exit 1; `2 failed, 25 passed in 1.26s`. Both failures showed `CatalogRelease.model_validate_json` accepting `true` and `"1"` for `BusinessInvariantContract.version` instead of raising `ValidationError`.

### GREEN Evidence

```text
python -m pytest backend/tests/test_capability_v2_contracts.py backend/tests/test_capability_business_definition.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_scanner.py -q --tb=short -k "not offline_runner_attaches_authoritative_registry_bindings" --basetemp=.runtime/task4-fix4-final
```

Result: exit 0; `140 passed, 1 deselected in 9.13s`.

Post-commit repetition with `--basetemp=.runtime/task4-fix4-postcommit`: exit 0; `140 passed, 1 deselected in 9.05s`. `git show --check --oneline --stat HEAD` also exited 0 for `3935bcc2`.

```text
python -m compileall -q backend/capability_v2/contracts.py backend/tests/test_capability_business_definition.py backend/tests/test_capability_governance_business_scanner.py
git diff --cached --check
```

Result: both exited 0 with no errors.

### Fix Notes

- `BusinessInvariantContract.version` is now `Field(ge=1, strict=True)`, so JSON booleans and numeric strings are rejected before scanner construction while literal integer 1 remains valid.
- End-to-end probes create a real immutable release, serialize it, pass it through `CatalogRelease.model_validate_json`, and only then scan it. They cover `true`, `"1"`, integer 1, the undeclared `rule_version` alias, version-sensitive business/descriptor hashes, and shuffle-stable scanner descriptor hashes.
- The author JSON Schema remains `type: integer` with `minimum: 1`; existing business-definition hash, catalog construction, catalog audit, store, provider, and CLI compatibility tests remain green.

### Concerns

- The known 495-field Catalog hash drift and 317/479 stable pin integration issues were not changed. The one healthy-Catalog binding test remains intentionally deselected.
- Unrelated dirty working-tree hunks remain excluded from `3935bcc2`.

## Catalog Integration Closure (2026-09-01)

### RED Evidence

```text
python -m pytest backend/tests/test_capability_catalog_release.py -q --tb=short -k "shared_catalog_loader" --basetemp=.runtime/task4-catalog-red
```

Result: exit 2 during collection because `load_catalog_release` did not exist.

```text
python -m pytest backend/tests/test_capability_governance_scanner.py::test_offline_runner_attaches_authoritative_registry_bindings -q --tb=short --basetemp=.runtime/task4-offline-red
```

Result: exit 1; the offline scan emitted a blocked empty snapshot and the expected `implemented_by` binding was absent. The structured report identified `extension_catalog_validation_error`; the checked-in extension artifact had a stale `catalog_hash` relative to its authoritative descriptors.

### GREEN Evidence

```text
python -m pytest backend/tests/test_capability_business_definition.py backend/tests/test_capability_v2_catalog_audit.py backend/tests/test_capability_catalog_release.py backend/tests/test_capability_governance_business_scanner.py backend/tests/test_capability_governance_store.py backend/tests/test_capability_governance_provider.py backend/tests/test_capability_governance_scanner.py backend/tests/test_capability_governance_acceptance.py -q --tb=short --basetemp=.runtime/task4-catalog-full-final
```

Result: exit 0; `134 passed in 155.34s` with no deselection.

```text
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/build_capability_governance_catalog.py --check
python backend/scripts/run_capability_governance_scan.py --offline --output .runtime/task4-catalog-integration-scan-green.json
```

Result: all exit 0. The product release check reported 495 descriptors; the regenerated test extension reported 18. The real scanner returned `scan_status=completed`, `product_descriptor_count=495`, `stable_product_descriptor_count=479`, `extension_descriptor_count=18`, and snapshot `sha256:89125f6a09891bd6eff0d58a9163c6ae8904926bf054a93ed995acccf2e90f16`.

### Fix Notes

- `load_catalog_release` is the one hash-aware Catalog reader. It deep-copies caller mappings, removes only the generated `business_definition_hash`, validates the unchanged closed Descriptor model, and verifies every supplied hash. Hashless legacy/test-extension documents remain valid.
- Generated-Catalog readers in catalog builders, documentation generation, offline scan and acceptance paths, bootstrap, gateway, and plugin marketplace use the loader.
- The stable descriptor pin is the explicit audited value `479`, independently counted from the checked-in product Catalog; it is not derived at runtime.
- The test-extension Catalog was regenerated from the current authoritative registry so its immutable release hash matches its descriptors.

### Concerns

- `python backend/scripts/generate_capability_docs.py --check` and `backend/tests/test_capability_docs_generation.py::test_checked_in_manual_has_no_generation_drift` still report broad documentation drift across pre-existing modified generated docs. Catalog parsing succeeds; those generated-document changes are outside this closure and remain uncommitted.

### Final Commit Verification

Commit `21864a2d` (`fix: close catalog integration`) contains the integration closure. The final pre-commit regression repetition used the same complete suite and exited 0 with `136 passed in 153.83s`; it includes the malformed-derived-hash cases added after the earlier 134-test run. No push or merge was performed.

## Catalog Integration Closure — Clean Materialization Repair (2026-09-01)

### RED Evidence

- Fresh detached materialization of `21864a2d` failed `python backend/scripts/build_capability_catalog.py --check` with `ModuleNotFoundError: backend.capability_v2.acceptance_contract`.
- The committed test-extension artifact was produced from a dirty working tree: its provider hash was `sha256:0aadb0ddcc02056b0c27a97dc81a87fb9e3e4e0867364a7b4b9ca146c0231c2d`, not the hash of the clean tracked governance-provider tree. The old extension builder also loaded the complete official registry, so unrelated dirty `release_gate.py` and `service.py` could change that artifact.
- Direct `CatalogRelease.model_validate_json` readers in integration production composition, agent e2e, and integration target tests rejected the generated `business_definition_hash` field. Before migration, those focused agent/integration suites had `9 failed, 2 passed`.

### GREEN Evidence

- The extension builder now creates a private `CapabilityRegistry` and invokes only `register_governance_capabilities`. The focused isolation test replaces the old official-registry entry point with a failure and proves the release still has exactly the 18 IDs in `ALL_IDS`.
- A fresh clean candidate materialization regenerated exactly the checked-in extension bytes: catalog hash `sha256:842a83882703680257177d9f0ecbc4007593f23609499ef169909a93dde83d93`, release `rel_842a83882703680257177d9f0ecbc400`, provider artifact `sha256:c61f1b375e84024901c1d625a124bb12dca3be3041baa68e9308e8b8fee60846`, and 18 descriptors. This deliberately excludes the uncommitted `release_gate.py`/`service.py` changes.
- `acceptance_contract.py` is committed as the audited 42-line minimal deterministic identity helper. It is not a new closure dependency: `3935bcc2` already imported it from the tracked product catalog builder; `21864a2d` changed the reader path but did not introduce that import.
- Product manifest hashes are regenerated from the candidate's tracked Base and Integration provider trees, and the product release/lineage are regenerated. Clean check: `rel_3f5ef8265738dc99f4803579111af53d`, 495 total / 479 stable.
- Clean candidate commands (with the required explicit Integration factory `AI00_INTEGRATION_ADAPTER_FACTORY=integration_backend.infrastructure.production_adapters:build`) passed:
  - `python backend/scripts/build_capability_catalog.py --check`
  - `python backend/scripts/build_capability_governance_catalog.py --check`
  - `python backend/scripts/run_capability_governance_scan.py --offline --output .task4-clean-offline-scan.json` → `completed`, 495 / 479 / 18
  - `python -m pytest backend/tests/test_capability_governance_catalog.py plugins/integration/tests/test_integration_target_catalog.py plugins/agent/tests/test_catalog_tool_e2e.py -q` → `21 passed`

### Reader Audit

- Generated release readers use `load_catalog_release`, including integration production adapters, agent e2e, integration target tests, user-function registry, bootstrap, gateway, scanners, and CLI builders.
- `build_user_function_registry.py` retains `json.loads` only for the human projection `docs/capabilities/catalog.v2.json`; it validates the immutable product release first, and validates release documents through the shared loader before deriving descriptor IDs.
- Remaining direct `CatalogRelease.model_validate_json` uses in `test_capability_governance_business_scanner.py` construct or mutate author/test fixture objects, not generated release artifacts. They intentionally exercise closed-model validation and are not Catalog file readers.

### Concerns

- The full `backend/tests/test_user_function_registry.py` has one pre-existing clean-worktree failure (`dynamic_fetch` line identity absent from `dist/web/core/auth_state.js`); it is unrelated to the loader/registry logic. The other focused reader tests pass.
- The official Integration provider intentionally requires the explicit factory environment variable; without it, full official-registry tests fail closed at configuration, not at Catalog validation.

### Final Commit Verification

- The final `fix: regenerate clean capability catalogs` commit was materialized in a fresh detached worktree and verified without using the shared dirty Provider tree.
- Fresh-clean results: product `--check` passed at `rel_3f5ef8265738dc99f4803579111af53d` (495 total / 479 stable); extension `--check` passed at `rel_842a83882703680257177d9f0ecbc400` (18); offline scan completed with `495 / 479 / 18`; the authoritative offline binding test passed; agent e2e passed `4`; extension/integration target focused tests passed `17`; and `git diff --check 21864a2d..HEAD` passed.
- `build_user_function_registry.py --strict` reaches the shared loader successfully but exits 1 on existing reviewed-disposition drift (replacement/non-stable Craft and Project targets plus missing review rows). This is governance-data drift outside the loader migration and is retained as a concern rather than rewritten by this closure.

## Catalog Integration Closure — Projection and Acceptance Binding Repair (2026-09-02)

### RED Evidence

- The committed human `docs/capabilities/catalog.v2.json` and acceptance case manifest still represented `rel_b79...`; the immutable product release is `rel_3f5ef8265738dc99f4803579111af53d`. The old manifest did not have `catalog_hash`.
- `test_catalog_projection_rejects_tampered_release_hash` initially failed because the registry builder exposed no verified projection loader. `test_case_manifest_is_bound_to_verified_catalog_hash` failed with the stale release mismatch. `test_validate_manifest_rejects_rebound_case_node` failed because a valid-looking node for another capability was accepted.
- `test_catalog_document_is_verified_before_domain_coverage_reads_it` failed because the coverage reader accepted `{ "descriptors": [] }` through `json.loads`.

### GREEN Evidence

```text
python backend/scripts/generate_capability_docs.py --write
python backend/scripts/build_capability_acceptance_manifest.py --write
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
```

All exited 0 from the exact detached `39123d77` candidate. The regenerated machine/human projection has product release `rel_3f5ef8265738dc99f4803579111af53d`, catalog hash `sha256:3f5ef8265738dc99f4803579111af53dfc0e0e019bbca1190b0946e28ccc84dc`, 495 descriptors, and 479 stable descriptors. The schema-v2 acceptance manifest has the same release/hash and 3,353 mandatory case nodes (479 × 7).

```text
python -m pytest backend/tests/acceptance/test_acceptance_runner.py::test_validate_manifest_rejects_catalog_hash_mismatch backend/tests/acceptance/test_acceptance_runner.py::test_validate_manifest_rejects_rebound_case_node backend/tests/acceptance/test_catalog_release.py backend/tests/acceptance/test_mandatory_cases.py -q
```

Result: exit 0; `3358 passed`.

```text
python -m pytest backend/tests/test_user_function_registry.py::test_catalog_projection_rejects_tampered_release_hash backend/tests/test_domain_capability_coverage.py::test_catalog_document_is_verified_before_domain_coverage_reads_it backend/tests/test_plugin_acceptance_tooling.py::PluginAcceptanceToolingTests::test_sdk_example_and_template_only_request_current_plugin_capabilities -q
```

Result: exit 0; `3 passed`.

### Fix Notes

- `validate_machine_catalog` compares a human/machine projection against the same verified immutable release, including release/hash and every generated descriptor/governance field. User Function Registry now loads that verified pair once before deriving its target index; it no longer validates one document and trusts another.
- The existing documentation generator remains the only projection generator. Its exact clean output replaces all 502 changed `docs/capabilities` files plus the acceptance case manifest; no shared dirty documentation or Provider input was used.
- Mandatory test support and manifest generation derive stable descriptor identities from the immutable release. Manifest validation now verifies release, hash, exact stable set, all case kinds, and the canonical per-capability pytest node identifier.
- Domain coverage and plugin tooling tests now consume generated releases via `load_catalog_release`. Remaining `CatalogRelease.model_validate_json` calls are fixture/author-contract tests in `test_capability_governance_business_scanner.py`; they do not read generated release files.

### Registry Drift Baseline

- On an independent clean `39123d77` materialization after its own docs regeneration, `build_user_function_registry.py --strict` exited 1 with 313 business/review drift lines, SHA-256 `bcf200cf6528edfff2473e10af3e07c10dce0847cb4b5fa6504a4dde55e27cc3`.
- The closure candidate has the same exit, 313 lines, and digest, with zero release/projection-integrity lines. These replacements, non-stable targets, and missing/evidence review rows are retained governance data drift.

### Concerns

- The full document tree must be committed together because the existing `generate_capability_docs.py --check` compares the complete generated tree; the clean semantic change is rebinding its release/hash and descriptors to the immutable product release.
- The final commit still requires fresh detached-materialization checks, including the explicit Integration adapter factory and the offline scanner; no result above uses the shared dirty worktree.

### Final Clean Materialization Verification

The single closure commit was materialized in a new detached worktree and verified with `AI00_INTEGRATION_ADAPTER_FACTORY=integration_backend.infrastructure.production_adapters:build`:

```text
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/build_capability_governance_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/run_capability_governance_scan.py --offline --output .task4-r2-offline-scan.json
```

All exited 0: product `rel_3f5ef8265738dc99f4803579111af53d` (495/479), extension `rel_842a83882703680257177d9f0ecbc400` (18), and the real scan completed with `495 / 479 / 18` and snapshot `sha256:99eaaf68ab23f5a78bc3c3ada122b3485fc2dc32d022a8d07f925dfb7de042d5`.

The full mandatory/binding and migrated-reader selection exited 0 with `3361 passed`; `git diff --check 39123d77..HEAD` exited 0. Registry strict still exits 1 only for the verified identical 313 governance-data drift rows, with no release/projection-integrity row.

## Catalog Integration Closure — Canonical Mandatory-Test Revision Repair (2026-09-02)

### RED Evidence

- The product builder hashed `test_mandatory_cases.py` with raw `read_bytes()`.  The initial contract test demonstrated that the generated `code_revision` did not equal the canonical LF/CRLF-equivalent digest.
- A changed mandatory-test `code_revision` was accepted by both acceptance-manifest validation and catalog audit because each path only checked that the field existed.

### GREEN Evidence

- `backend.capability_v2.acceptance_contract.canonical_test_source_hash` defines the shared controlled hash: it decodes UTF-8 strictly, normalizes only CRLF to LF, rejects an isolated CR, and returns a `sha256:` digest of the re-encoded canonical UTF-8 bytes.  Thus LF and CRLF checkouts bind identically, while a content change does not.  Invalid UTF-8 and bare CR are fail-closed rather than silently rewritten.
- `build_capability_catalog.py` obtains every mandatory `code_revision` through that helper.  Acceptance validation now requires exactly the seven canonical mandatory node IDs and paths per stable capability and rejects a source-hash mismatch.  Catalog audit receives the repository source root in both production callers and rejects a mismatched mandatory source revision.
- The controlled cross-EOL byte probe produced identical LF/CRLF hash `sha256:98752ee28d5484bdc2814fb70adb6a0b2fb31f6a9b8ee7ae81fd2fc9cf300b3b`; changing `x=1` to `x=2` produced `sha256:7b519d327803fabd4c74e1b993360e8d48b414771a12d0a868d6edf7cfec50bb`.
- Exact clean-candidate regeneration with `AI00_INTEGRATION_ADAPTER_FACTORY=integration_backend.infrastructure.production_adapters:build` produced product `rel_0b584b19349bc98727900583bb19f687`, catalog hash `sha256:0b584b19349bc98727900583bb19f687a093b3ce91431fb384795034d690ab60`, 495 descriptors / 479 stable, and mandatory test source hash `sha256:578d5843eb4b4bf06d74b3954220f41a6073171c414b0ad52f88dfda7436a802`.  The extension has no mandatory-test dependency and remains `rel_842a83882703680257177d9f0ecbc400` with 18 descriptors.  Product release/lineage, all generated docs/agent/MCP tools, and the 479-stable case manifest were regenerated from that candidate only.

### Test Commands

```text
python -m pytest backend/tests/acceptance/test_catalog_release.py backend/tests/acceptance/test_mandatory_cases.py backend/tests/acceptance/test_acceptance_runner.py::test_current_manifest_is_release_complete backend/tests/acceptance/test_acceptance_runner.py::test_validate_manifest_rejects_tampered_mandatory_test_source_hash backend/tests/acceptance/test_acceptance_runner.py::test_validate_manifest_rejects_missing_mandatory_test_refs backend/tests/test_capability_catalog_release.py::test_generated_catalog_declares_exact_acceptance_cases_without_self_attested_results backend/tests/test_capability_catalog_release.py::test_mandatory_test_source_hash_is_eol_stable_and_content_sensitive backend/tests/test_capability_v2_catalog_audit.py::test_audit_catalog_rejects_tampered_mandatory_test_source_hash backend/tests/test_plugin_acceptance_tooling.py::PluginAcceptanceToolingTests::test_sdk_example_and_template_only_request_current_plugin_capabilities -q -p no:cacheprovider
```

Result: exit 0; `3363 passed`.

```text
python -m pytest backend/tests/test_user_function_registry.py::test_catalog_projection_rejects_tampered_release_hash backend/tests/test_domain_capability_coverage.py::test_catalog_document_is_verified_before_domain_coverage_reads_it -q -p no:cacheprovider
```

Result: exit 0; `2 passed` on the clean candidate.  A later aggregate rerun reached 3,363 passing tests before two `tmp_path` setup errors caused by an inaccessible/reused Windows pytest base directory; those errors occur before either test body and are not a Catalog assertion failure.

### Concerns

- This round uses an equivalent controlled LF/CRLF byte probe, rather than an OS-specific checkout, so the evidence is independent of Git EOL configuration and exercises the exact bytes accepted by the shared helper.
- The known User Function Registry `--strict` 313-row governance-data drift remains out of scope; this repair removes no business drift and introduces no release/projection-integrity drift.

### Final Clean Materialization Verification

The final commit was materialized in a fresh detached worktree, with the explicit Integration factory, and the following commands exited 0:

```text
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/build_capability_governance_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/run_capability_governance_scan.py --offline --output .task4-r3-final-offline-scan.json
git diff --check ca18325e..HEAD
```

They verified product `rel_0b584b19349bc98727900583bb19f687` (495 total / 479 stable), extension `rel_842a83882703680257177d9f0ecbc400` (18), and an offline scan status of `completed` with snapshot `sha256:0508f47cf78faf95c30b63d5ee5ed3bdbd0ce5049add523e373ccf696b5c4742`.  The clean checkout uses Windows checkout bytes, while the controlled LF/CRLF probe proves its stored Catalog source revision is invariant under the alternate line ending.

The mandatory/binding/reader command above reached `3363 passed`; its two remaining errors occurred during `tmp_path` setup because the host denied enumeration of `C:\\Users\\luoyi8\\AppData\\Local\\Temp\\pytest-of-luoyi8`, before those test bodies.  Their same focused command passed earlier on the clean candidate (`2 passed`).  `build_user_function_registry.py --strict` still exits 1 for the same 313 drift records (314 output lines including its heading) and no release/projection integrity error.
