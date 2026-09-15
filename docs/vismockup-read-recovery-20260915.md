# Test runtime read recovery — 2026-09-15

## Change classification
Implementation recovery fix; user confirmed that timed-out read-only work may fail without blocking reconnection. No new Capability, model write, schema migration, or production release.

## Authoritative context inspected
Simulation Connector repository, v2 runtime/reconciliation contracts and SQL tests, official simulation Provider manifest. App-owned ConnectorHost is the consumer; runtime plan/device/audit tables remain owned by simulation and test deployment uses the test_ prefix.

## Reuse and boundary
Extend existing restart-safe read retirement to manual_review_required only when every persisted step is read-only and the lease expired (or authenticated process restart fences the previous host). Empty, write, mixed, and still-leased plans are not waived. Existing signed outcome evidence is preserved; retirement appends plan_failed_without_effect audit. No direct database recovery script or installed standalone Connector.

## Verification
Regression reproduced runtime_plans_unresolved for expired manual-review reads before the fix. SQL tests cover read recovery, active-lease refusal, write refusal and preservation of original reconciliation evidence. See execution output for final counts; MySQL fixture tests without a configured dedicated fixture are skipped, not passed.

Final regression: 112 passed, 99 skipped (SQL runtime + reconciliation suites). Test App restarted successfully with App-owned ConnectorHost PID 393880. At 2026-09-15 06:49:06 UTC, normal registration retired the timed-out tree plan and two never-leased queued reads with appended audit, then installed a replacement runtime session. A new heartbeat was persisted at 06:49:07 UTC. Existing VisMockup processes remained running. No direct DB mutation was used.

## Governance status and risks
AI advisory. User approved the recovery rule, not a signed Capability release. Formal human_approved/release readiness remains unverified. Runtime restoration and full model-tree extraction are separate acceptance checks; restoring registration alone does not prove complete tree extraction.
