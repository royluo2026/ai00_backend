# Versioned database migrations

File names must use `YYYYMMDDNNNN_domain_description.sql`, for example
`202608030001_agent_private_sessions.sql`. The domain is one of `base`, `craft`,
`simulation`, `agent`, `device`, or `knowledge`.

Rules:

- A migration may only reference tables owned by its filename domain.
- Applied files are immutable; changing a checksum is a deployment error.
- Only the deployment migration job may run these files, using `AI00_DDL_DB_URL`.
- Application startup, routers, Agent tools and plugins must never execute DDL.
- Cross-domain foreign keys and SQL are forbidden.

OceanBase compatibility contract:

- Production baseline is OceanBase 4.3.5+ in MySQL mode with strict SQL mode.
- OceanBase DDL implicitly commits, so every statement must be independently replay-safe.
- Only `CREATE TABLE IF NOT EXISTS`, `CREATE [UNIQUE] INDEX IF NOT EXISTS`, and
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` are accepted by the migration validator.
- TEXT/BLOB columns must not declare `DEFAULT`. Legacy JSON expression defaults are stripped by the runner because OceanBase 4.3.5 rejects them; new migrations should omit them.
- Run `python backend/scripts/oceanbase_compatibility_audit.py` before packaging and
  add `--connect` in the deployment environment.
- A failed migration may be corrected and retried; an applied migration is immutable.

See `docs/oceanbase-mysql-compatibility.md` for the complete policy.