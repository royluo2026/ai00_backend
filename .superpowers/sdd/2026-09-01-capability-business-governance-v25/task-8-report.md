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
