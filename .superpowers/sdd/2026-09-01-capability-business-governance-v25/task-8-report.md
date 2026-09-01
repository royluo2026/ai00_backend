# Task 8 Report — Seven-layer Capability Business Audit

## Result

Implemented the read-only seven-layer baseline at commit `842933d8140d00c8c5994c28011dc504236e225a`. The audit consumes the Task 4 scanner snapshot and maturity records, Task 5 deterministic/advisory relation records, and Task 7 canonical business release result. It does not add another scanner, approval model, or maturity scale, and it performs no database, Catalog, permission, domain, or review mutation.

`BusinessAuditReport` now carries the exact snapshot GID; exact backend, Web, and snapshot-source revisions; A-G evidence; L0-L6 counts and capability evidence; separately counted evidence rows and root-cause groups; affected capabilities/domains; shared remediation families; relation candidates; concrete unbound public entries; the risk-ordered legacy review queue; and independent machine/human/runtime states. Root keys are exactly `reason_code:capability_id@major[:rule_id]`. A deterministic cross-domain conflict is one canonical group with all affected capability keys and domains, while its evidence rows remain individually countable.

## TDD evidence

- Initial RED: the required focused command produced `8 failed` because `business_audit` and the new CLI contract did not exist.
- Exact service projection RED: `1 failed`; the service had no exact-snapshot audit projection and registry search read the latest snapshot.
- Deterministic conflict RED: `1 failed`; collected relation evidence was not yet emitted as one cross-domain root group.
- Offline Integration bootstrap RED: `1 failed`; the clean authoritative registry correctly refused to load without `AI00_INTEGRATION_ADAPTER_FACTORY`.
- GREEN: `python -m pytest backend/tests/test_audit_capability_business_rules.py backend/tests/test_capability_business_audit.py -q -p no:cacheprovider --basetemp=E:/Projects/ai00_v3/.runtime/task8-clean-focused-842933d8-2` — `10 passed in 0.91s`.

Pagination tests force 205 registry rows and 205 Finding rows. Both APIs are called with `limit=200` and offsets `0, 200`, and collection stops only after `offset >= total`. The same test proves exact snapshot/source binding, full relation redaction, and concrete REST route, Provider, worker, MCP, Agent Tool, and file-location output.

## Read-only baseline

Generated from the exact clean detached materialization at `842933d8`:

`python backend/scripts/audit_capability_business_rules.py --format json --output E:/Projects/ai00_v3/.runtime/task8-capability-business-audit-clean.json`

The command exited 0. The 844,101-byte JSON binds snapshot GID `991`, backend/source revision `842933d8140d00c8c5994c28011dc504236e225a`, and Web revision `b48b630b8ade831f2f8bd31275d7629aeb5af434`. It reports 495 evidence findings, 495 root-cause groups, 495 affected Capabilities across 11 domains, 2 shared remediation families, 1 relation, 27 concrete unbound entries (9 Providers and 18 workers), and 495 review-queue entries. Maturity is L1=495 with all other levels zero; layer counts are A=495, B=495, F=495, and C/D/E/G=0. Machine passed is true, human approved is false, runtime verified is false, and legacy pending review is 495.

The shared dirty worktree run failed closed before scanning because unrelated dirty Integration Provider sources do not match the frozen provider artifact hash. No trust check was bypassed. In the clean tree, the CLI temporarily supplies the repository's established offline Integration acceptance factory only for authoritative registry construction and restores the caller environment afterward.

## Regression and clean-materialization verification

- Clean Task 4-7/service/provider/Task 8 group: `98 passed, 2 failed in 13.57s`.
- The two failures are the known stale release-evidence assertions carried from Tasks 6/7: one provider fixture still expects the old three blockers and omits `business_governance_missing`/`missing_required_data`; one authoritative-evidence fixture omits the newly required static/business evidence and therefore fails closed before its old `required_test_not_passed` assertion.
- The same shared dirty group produced `99 passed, 1 failed`; preserved uncommitted static-gate evidence changes hide the second clean stale assertion. Task 8 did not absorb either fixture rewrite.
- `python -m compileall -q` for the audit module, service, and CLI passed.
- `git diff --check 1f1b7064 842933d8` passed; the clean detached materialization remained clean after verification.

## Final-review observation

The Task 6 process-local `business_review_gid` restart-collision observation remains deferred exactly as ruled. Task 8 neither expands nor relies on that allocator; the review queue is derived read-only from immutable snapshot, relation, and release-policy records.

## Fix round 1 — evidence-integrity review

Commit `6e19b63d932261a97d192a7c3cd4b0ee79c89bc3` closes all five review findings as one evidence-integrity change. Audit release states are now accepted only after Task 7's canonical `parse_business_governance_result` rederives them and the collector proves an exact match among Catalog release/content/projection, snapshot Catalog release, and the complete `(capability_key, capability_version_gid, major_version, business_definition_hash)` set. Empty, omitted, extra, stale-Catalog, wrong-hash, and wrong-GID results fail closed. The scanner snapshot now retains the canonical business-definition hash using the shared business-definition projection rather than a second hash model.

Registry projections retain immutable business-rule records. Exact enforcement and test references attach their canonical `rule_id`, repeated rows for the same rule share one `reason_code:capability@major:rule_id` group, different rules remain separate, and capability-level evidence keeps the unsuffixed root. Nested relation evidence, layer evidence, rules, and mappings are recursively frozen while explicit serialization still produces ordinary JSON values.

The CLI rejects relevant tracked dirt before recording a Git revision. Backend scanning requires clean `backend`, `plugins`, and `docs/governance` paths; Web provenance independently requires a clean Web tree. Ignored and untracked runtime output is not treated as source dirt. The replacement baseline was therefore generated only from detached clean backend and Web worktrees. Scanner-projected `public_entry` and `source_line` metadata now distinguish externally callable routes/exports from private helpers; the audit consumes that projection and emits exact `file:line` locations. `_worker_error`, `_worker_envelope_bytes`, `_UnavailableProviderRegistry`, other underscore helpers, and task-classifier implementation details are absent unless an explicit public route registration makes them callable.

Fix-round TDD evidence: focused RED was `6 failed, 9 passed`, directly covering gate binding, rule grouping, public filtering/location, recursive freezing, and dirty provenance. Focused GREEN at the final commit is `20 passed in 3.11s`. The pagination proof remains offsets `0, 200` for both 205-row inputs with `limit=200`.

The reconciled read-only JSON is `E:/Projects/ai00_v3/.runtime/task8-capability-business-audit-fix1.json`. It binds snapshot GID `991`, backend/source revision `6e19b63d932261a97d192a7c3cd4b0ee79c89bc3`, and independent Web revision `b48b630b8ade831f2f8bd31275d7629aeb5af434`. Counts are 495 findings, 495 root groups, 495 affected Capabilities, 11 domains, 2 remediation families, 1 relation, **17** public unbound entries (8 Providers and 9 workers), and 495 review items. Maturity is L1=495; layers A/B/F/G each cover 495 Capabilities and C/D/E are zero. Machine passes; human approval and runtime verification remain false; legacy pending review is 495. The former count of 27 is intentionally not preserved because it included private and non-public implementation helpers.

Final clean regression evidence is `145 passed, 4 failed in 51.30s`. Two failures are the already recorded Task 7 release-fixture assertions that omit required static/business evidence. The other two are pre-existing scanner assertions: the offline runner lacks the test-only Integration adapter in that command path, and one stale assertion expects `product_catalog_string_list_invalid` although canonical rule validation returns the more precise `product_catalog_business_rule_scalar_invalid`. Task 8 does not weaken those fail-closed paths or rewrite unrelated assertions. The Task 6 process-local `business_review_gid` collision observation remains deferred and unchanged.

## Fix round 2 — race-free source provenance

Commit `839f830c52ffecbdc18566fc6c5cf7e048daa3a8` closes the remaining provenance root cause. `GovernanceScanner` now exposes the same declared-root discovery, `.py`/`.sql` candidate rule, symlink boundary, and size limit used by the actual scan. The CLI fingerprints the exact discovered scanner inputs plus the Catalog, extension Catalog, official domain manifest, acceptance manifest, and legacy baseline. Every discovered input must be Git-tracked. Tracked staged/unstaged changes and deletions fail closed; untracked or ignored source that the scanner could read fails closed; irrelevant untracked runtime/cache/output files remain outside the provenance set.

Backend and Web provenance are captured independently before the scan and again after it. Each capture includes the resolved 40-character commit, ordered input-path set, and SHA-256 input fingerprint, with a clean relevant status as a precondition. The one canonical Task 4 scan receives the captured backend revision. Any backend or Web revision, relevant status, input membership, or byte-fingerprint change aborts with `business_audit_inputs_changed_during_scan` before report construction. Web is guarded against every tracked-tree change and fingerprinted across its complete tracked materialization.

Fix-round RED was `3 failed, 6 passed`: untracked eligible Python was accepted and the pre/post provenance contract did not exist. Final provenance unit GREEN is `10 passed in 6.09s`; the combined Task 8 focused suite is `22 passed in 6.65s`. Clean audit/scanner verification is `64 passed, 2 failed in 10.76s`, with only the same pre-existing offline Integration binding and stale scalar-error wording assertions recorded above.

The final baseline was regenerated only from detached clean backend and Web materializations at `E:/Projects/ai00_v3/.runtime/task8-capability-business-audit-fix2.json`. It binds snapshot `991`, backend/source `839f830c52ffecbdc18566fc6c5cf7e048daa3a8`, and Web `b48b630b8ade831f2f8bd31275d7629aeb5af434`. Counts remain reconciled at 495 findings, 495 root groups, 17 public unbound entries, and 495 review items; machine passes, human/runtime remain false, and legacy pending review remains 495. The detached backend worktree contained an unrelated untracked `.runtime/promotion-retirement-scan.json`; it was correctly excluded because neither scanner discovery nor the fixed policy inputs can consume it.

## Fix round 3 — acceptance-source provenance

Commit `989911f258a6ca84b699677dd8913db8e9ae60dc` closes the final indirect-input gap. The scanner-owned discovery API now includes the acceptance manifest and resolves every manifest test node through the same parser, repository-boundary check, symlink/size/source eligibility rules, and normalized path used by `_bind_acceptance_tests`. Missing, outside-root, symlink-escaping, duplicate node, and malformed references fail closed before a report can be built. `_bind_acceptance_tests` consumes the shared parsed records, so discovery and the source bytes actually hashed into test-case nodes cannot diverge. The production manifest currently reveals one indirect source, `backend/tests/acceptance/test_mandatory_cases.py`; no other manifest/config-referenced files are consumed by this scanner path.

Fix-round RED was `5 failed, 10 passed`: the manifest and its referenced source were absent from canonical discovery, so staged, unstaged, untracked, and during-scan acceptance-source changes were not provenance failures. Final focused GREEN is `27 passed in 16.36s` from the detached clean materialization. The tests also prove that the scanner creates the declared test node and hashes the exact referenced source bytes, rather than merely listing the path. Clean scanner regression is `42 passed, 2 failed in 5.05s`; the only failures remain the previously recorded offline Integration adapter and stale scalar-error wording assertions.

The regenerated read-only baseline is `E:/Projects/ai00_v3/.runtime/task8-capability-business-audit-fix3.json`. It binds snapshot `991`, backend/source `989911f258a6ca84b699677dd8913db8e9ae60dc`, and Web `b48b630b8ade831f2f8bd31275d7629aeb5af434`. Counts remain 495 findings, 495 root groups, 495 affected Capabilities in 11 domains, 2 remediation families, 1 relation, 17 public unbound entries, and 495 review items. Layer counts are A/B/F/G=495 and C/D/E=0; maturity remains L1=495. Machine passes, human/runtime remain false, and legacy pending review remains 495. Compile and scoped diff checks passed; the unrelated detached `.runtime` output remains excluded because scanner discovery cannot consume it.
