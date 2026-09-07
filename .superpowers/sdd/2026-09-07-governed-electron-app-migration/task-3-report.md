# Task 3 report — DONE_WITH_CONCERNS

Implementation commit: `3bd31a9b4` (`feat: persist governed Connector runtime v2 state`).

## 1. Change classification

Compatible additive Simulation persistence for the already committed protocol v2. No wire-contract, Capability definition/version, provider registration, generated Catalog, approval, or route change. The AI00 skill's literal basename scope gate excludes this worktree (`orchestration-merge-backend-20260905`); its ownership/evidence reporting structure is nevertheless useful here. TDD and Ponytail were applied; completion claims use fresh test output.

## 2. Authoritative context inspected

Read the exact Task 3 brief, Task 2 protocol models and fixtures, migration design and plan sections for pairing/runtime fencing, the existing Simulation repository/connection adapter, migrations 0005 and 0007, migration preparation/validation, ownership/inventory documents, existing pairing/data/ownership tests, and the opt-in MySQL projection integration fixture. The resolved worktree had no AGENTS.md. Existing protocol v2 models were reused without modification.

## 3. Reuse, atomicity, and ownership result

Migration 0008 adds five Simulation tables: `workmanship_sim_connector_runtime_devices`, `workmanship_sim_connector_runtime_plans`, `workmanship_sim_connector_app_pairings`, `workmanship_sim_connector_runtime_recovery_sessions`, and `workmanship_sim_connector_runtime_audit`. Explicit non-null protocol columns, checks, binary ASCII identity columns up to 256 characters, uniqueness constraints and lookup indexes preserve v2 identities. Legacy bindings/plans/pairings/bootstrap rows receive a v1 protocol default; no row is copied or reinterpreted as v2.

Separate v2 tables prevent legacy completion/lease code from touching v2 rows. Legacy leasing additionally locks/checks the new runtime-device row and returns no work for a device present in v2 storage. V2 registration and takeover check unresolved legacy plans as well as v2 plans. This closes the coexistence race for existing runtime-device rows; Task 4 activation must maintain the same device-first serialization and caller authentication boundaries.

All v2 writers acquire the device row lock first. Normal sessions bind device, generation, current execution instance and SHA-256 token hash. Registration cannot replace an unexpired session, and either registration or takeover rejects leased, executing, unknown and manual-review work. Takeover requires the caller's exact old instance/hash snapshot and precisely the next generation, then audits actor and reason. Session replacement, outcomes and reconciliation use compare-and-set predicates under the transaction. Only random session tokens are returned; their plaintext is absent from storage and dataclass repr. Session TTL is bounded to 300 seconds.

Queueing binds the plan to the authenticated session. Leasing is single-flight per device, clips the lease to session/plan expiry, marks expired leases unknown instead of retrying, and excludes stale instance/session plans. Completion checks device, generation, instance, token, protocol, lease, tenant and plan hash. Normal outcome retries are idempotent; conflicting outcomes fail. Explicit reconciliation is required to change an uncertain result. Signed original and reconciliation outcome payloads/hashes remain in append-only audit entries, while the plan row holds the current result.

The parent authorized a reconciliation-only recovery interface after discovery of the expired-session deadlock. It leaves original runtime/plan pins untouched, requires an expired normal session and a named unknown/manual-review plan, permits only one unexpired recovery session per device, and uses a separate token/hash and explicit `plan_reconciliation` scope. Recovery credentials cannot satisfy normal authentication, lease or completion. Reconciliation audit records both execution and recovery instances plus both session hashes. Terminal success/failed-without-effect consumes recovery atomically; ordinary registration can then succeed if every uncertain plan is resolved. A consumed recovery token fails closed on subsequent submissions; callers should read authoritative plan state after an uncertain response rather than replay with a consumed token.

## 4. Implementation boundary and Task 4 interfaces

Files changed:

- `backend/db/migrations/domains/simulation/0008_connector_app_runtime_v2.sql`
- `plugins/simulation/simulation_backend/data/connector_repository.py`
- `backend/governance/domain_table_ownership.json`
- `backend/governance/table_inventory.json`
- `backend/tests/test_simulation_connector_runtime_v2_sql.py`

The existing pairing SQL tests were exercised unchanged. Inventory changes are limited to the five new tables and the previously unregistered 0007 bootstrap table that 0008 alters; exact ownership metadata and its count match these additions. The pre-existing unrelated inventory gap remains reported below.

Public storage interfaces:

```python
register_runtime_session(device_id, runtime_generation, runtime_instance_id, now, expires_at) -> RuntimeSession
force_takeover(device_id, expected_generation, new_generation, runtime_instance_id, now, expires_at,
               *, expected_runtime_instance_id, expected_session_token_hash, actor_id, reason) -> RuntimeSession
insert_v2_plan(plan: ConnectorExecutionPlanV2, session_token: str, now: datetime) -> None
lease_v2_plan(device_id, runtime_generation, runtime_instance_id, session_token, now, lease_seconds=60)
complete_v2_plan(device_id, runtime_generation, runtime_instance_id, session_token, outcome, now) -> None
mark_reconciled(device_id, runtime_generation, runtime_instance_id, session_token, outcome, now) -> None
register_reconciliation_session(device_id, generation, recovery_instance_id, plan_id,
                                token_hash, expires_at, *, now=None) -> dict
```

`RuntimeSession` returns device/generation/instance/expiry and the one-time plaintext `session_token`. Leasing returns lease_id, lease_until and the persisted v2 plan. Recovery registration returns only device/generation/recovery instance/plan/scope/expiry. For recovery reconciliation, pass the recovery instance and recovery secret to `mark_reconciled`; the signed Outcome v2 still carries the original execution instance, plan hash and lease. This preserves Task 2 wire rules.

Task 4 must authenticate the device credential and device-signing proof before either registration interface and authenticate the user/takeover authority before takeover. The recovery caller generates a high-entropy secret and supplies only its SHA-256 hash to storage. Task 4/5 must restrict any recovery probe service to the named plan, distinguish its token scope from wake-up/normal execution/renewal, authenticate signatures and probe evidence, and supply trusted server UTC time. Normal session renewal, activation transactions and service/Capability exposure are intentionally not implemented here. No general wake/renew authentication surface was added that could accidentally accept recovery tokens.

## 5. Verification evidence

TDD observations:

1. Initial new SQL suite failed with the explicitly missing migration (17 setup failures); existing pairing tests passed (10).
2. After additive schema creation, the same suite produced 17 failures for missing `register_runtime_session`, proving the real repository behavior was absent.
3. Initial implementation: 17 passed, 17 optional MySQL cases skipped.
4. Additional red tests exposed absent legacy protocol columns, unresolved-v1 gating, ownership entries and legacy leasing fencing; these were implemented and rerun.
5. The parent-requested recovery tests failed on the missing recovery interface, then passed after implementation, including two-worker registration races, plan scope, expiry, stale generation, terminal consumption, identity preservation and subsequent normal registration.
6. An audit-preservation test failed on missing original outcome payload storage, then passed with outcome JSON persisted in audit.

Final required focused command:

```powershell
python -m pytest backend/tests/test_simulation_connector_runtime_v2_sql.py backend/tests/test_simulation_connector_pairing_sql.py backend/tests/test_simulation_connector_data_migration.py backend/tests/test_simulation_connector_capability_ownership.py -q --tb=short
```

Result: **52 passed, 29 skipped**. Skips are exclusively the opt-in native MySQL cases because `AI00_SIMULATION_TEST_DB_URL` is absent.

Final broader passing command added `test_simulation_connector_outcome_capabilities.py`, `test_simulation_connector_projection_worker.py`, `test_connector_runtime_control_plane.py`, `test_versioned_migration_files.py`, and `integration/test_simulation_connector_projection_mysql.py` to the four modules above: **93 passed, 31 skipped**. The additional two skips are the existing real MySQL projection tests requiring the same missing URL. `git diff --check` and staged diff checks passed.

The new suite runs real repository SQL against a temporary SQLite database with dialect-only translation and real transaction rollback; SQLite serializes writers. Its optional MySQL parameter uses native PyMySQL transactions and row locks and applies migrations through the production MySQL/OceanBase preparation adapter. SQLite results establish repository behavior, not native MySQL concurrency/runtime verification. No native MySQL server execution occurred.

Broader checks with known baseline failures:

- `test_versioned_migration_files.py`, `test_versioned_migrations.py`, `test_domain_table_ownership.py`: **18 passed, 2 failed**. Remaining failures: the historical 0004 byte comparison sees checkout CRLF versus Git LF; ownership/inventory set equality sees nine pre-existing missing inventory entries. Before Task 3, ownership had 293 entries and inventory 284; after additive Task 3 metadata, 299 and 290. No historical migration was edited.
- A broader run including `test_simulation_connector_http_api.py`: **95 passed, 29 skipped, 1 failed**. The unchanged route set assertion omits the already-present `/api/v1/simulation/connectors/plans/wake` and `/api/v1/simulation/connectors/plans/{plan_id}/artifacts/{artifact_id}/content` routes. No route file changed.

## 6. Governance status

- Focused storage/migration behavior: passed.
- Repository-wide `machine_passed`: not claimed; broader baseline failures remain.
- `human_approved`: not claimed.
- `runtime_verified`: false/unverified; native MySQL and deployed services were not exercised.
- Knowledge capabilities, route-proof debt, approvals and generated Catalog remain untouched. No push, merge, publication, or subagent dispatch occurred.

## 7. Self-review and unresolved concerns

Self-reviewed the staged diff, SQL lock order, compare-and-set predicates, token handling, legacy isolation, outcome conflict behavior and recovery scope. Tests execute actual transactions; a forced duplicate audit primary key proves plan-state rollback after an audit insert fails. Migration validation recognizes the additive schema and exact Simulation ownership. New v2 identity fields accommodate the existing 256-character wire IDs.

Outstanding native MySQL execution is the material verification gap. The broader baseline inventory/checksum/route-test failures above are not fixed or hidden. Service authentication, signing/possession verification, normal renewal and recovery-probe authorization remain Task 4/5 work. Registering an execution session is not itself credential validation; callers must enforce that documented boundary. Deployment must apply migration 0008 before the updated repository, including legacy leasing's new device-row guard. Release readiness and approval remain blocked by their separately owned concerns.
