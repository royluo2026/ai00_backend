# Domain Table Prefix Coverage

## Classification

Implementation fix. The test runtime already declares `TABLE_PREFIX=test_`, but plugin-owned database pools bypass the existing cursor wrapper and can execute SQL against unprefixed tables.

## Design

Add one connection-level helper beside the existing `PrefixedCursor`. The helper wraps a connection's `cursor()` method exactly once and delegates SQL rewriting to the existing `rewrite_sql()` implementation.

Every plugin-owned database connection boundary must call this helper immediately after acquiring a connection. This keeps database credentials, pool ownership, transactions, and repository SQL unchanged while making `TABLE_PREFIX` behavior consistent across Base and all plugin domains.

## Safety

- Empty `TABLE_PREFIX` preserves current production SQL.
- `TABLE_PREFIX=test_` rewrites `workmanship_*` to `test_workmanship_*`.
- Double wrapping must be idempotent.
- No schema creation, migration, or database write is part of this change.

## Verification

Add a focused test that proves connection wrapping is idempotent and rewrites SQL. Add a repository-level coverage assertion listing every plugin connection boundary so a future unwrapped pool fails CI. Run the focused tests, then restart the test backend with `backend/.env` and verify representative Project and Workbench reads no longer target unprefixed tables.

