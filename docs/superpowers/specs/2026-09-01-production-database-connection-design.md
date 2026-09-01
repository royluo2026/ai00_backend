# Production Database Connection Design

## Goal

Make the database settings flow safe and useful for production readiness without weakening Capability V2 domain database isolation or allowing browser-managed production cutover.

## Scope

- Keep `base.runtime.database_connection.test@1` as a read-only MySQL/OceanBase connectivity check.
- Remove hard-coded test-environment values from the web settings form.
- Reject incomplete connection tests before opening a database connection.
- Return stable, sanitized diagnostic categories without exposing credentials or raw server errors.
- When `ENV_FILE` is explicitly configured, reject browser attempts to persist database configuration because deployment configuration is authoritative.
- Explain in the UI that production cutover uses `USERS_DB_URL` and domain-owned `AI00_*_DB_URL` values followed by a backend restart.

## Non-goals

- No production credentials are stored in the browser.
- No domain runtime connection pool is changed while the service is running.
- No schema creation, migration, grant, DDL, or business-data write is performed by the connection test.
- No web-based multi-domain secret-management subsystem is introduced.

## Backend behavior

`base.runtime.database_connection.test@1` validates `host`, `port`, `user`, `password`, and `collab_db`. A blank password may reuse a password already stored in desktop mode; otherwise it is rejected before connecting.

The provider performs one connection and `SELECT 1`, then closes the connection. Failures return one of these safe codes:

- `authentication_failed`
- `database_not_found`
- `network_unreachable`
- `tls_or_server_config_failed`
- `connection_failed`

Raw exception text, usernames, passwords, database URLs, and SQL are never returned to the client.

`base.runtime.database_config.change.apply@1` remains available only for desktop-style startup without an explicit `ENV_FILE`. Under deployment-managed startup it rejects the operation with `deployment_managed_config`; it never claims that a saved value changed the running connection pools.

## Frontend behavior

The database form starts empty unless the backend returns an existing saved desktop configuration. It never inserts the former `sam-bdmsdb01-test.chj.cloud` test values.

The connection-test action validates required fields locally, invokes the governed Capability, and maps safe error codes to actionable Chinese messages. The screen labels the operation as a read-only connectivity test and states that production database activation requires deployment configuration and restart.

The save action displays the deployment-managed rejection clearly. It does not imply that Craft, Knowledge, Project, or other domain pools were switched.

## Capability governance

All browser operations continue through the existing Capability Gateway. The change does not add a direct REST or database bypass. Runtime credentials remain domain-owned (`AI00_CRAFT_DB_URL`, `AI00_KNOWLEDGE_DB_URL`, and peers), while Base continues to use its declared runtime URL. DDL credentials remain separate and are outside this UI.

## Verification

- Backend tests prove missing passwords are rejected without calling PyMySQL.
- Backend tests prove representative PyMySQL failures map to sanitized codes and never leak raw messages.
- Backend tests prove explicit `ENV_FILE` blocks saved configuration changes.
- Frontend tests prove no test host/user/database defaults remain and safe codes render actionable messages.
- Existing Capability contract and acceptance tests remain green.
- A manual local check confirms that the currently reachable test host is not contacted until complete user-supplied values are present.
