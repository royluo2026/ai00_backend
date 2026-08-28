-- Preserve historical rows under the empty legacy tenant while new lifecycle
-- writes bind the trusted tenant and canonical command digest.
ALTER TABLE workmanship_base_plugin_lifecycle_idempotency
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NOT NULL DEFAULT '' FIRST;
ALTER TABLE workmanship_base_plugin_lifecycle_idempotency
  ADD COLUMN IF NOT EXISTS command_sha256 CHAR(64) NOT NULL DEFAULT '' AFTER idempotency_key;

ALTER TABLE workmanship_base_plugin_lifecycle_idempotency
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_gid, actor_gid, operation, idempotency_key);
