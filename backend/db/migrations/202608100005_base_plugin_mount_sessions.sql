ALTER TABLE workmanship_plugin_installations
  ADD COLUMN IF NOT EXISTS installation_id VARCHAR(64) NULL;

ALTER TABLE workmanship_plugin_installations
  ADD COLUMN IF NOT EXISTS mount_revocation_version INT UNSIGNED NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS workmanship_plugin_mount_sessions (
  mount_session_id VARCHAR(64) NOT NULL,
  asset_token_hash CHAR(64) NOT NULL,
  user_id VARCHAR(256) NOT NULL,
  tenant_id VARCHAR(256) NOT NULL,
  installation_id VARCHAR(64) NOT NULL,
  plugin_id VARCHAR(255) NOT NULL,
  plugin_version VARCHAR(128) NOT NULL,
  artifact_sha256 CHAR(64) NOT NULL,
  catalog_release VARCHAR(64) NOT NULL,
  capability_grants_json JSON NOT NULL,
  resource_scopes_json JSON NOT NULL,
  data_scopes_json JSON NOT NULL,
  revocation_version INT UNSIGNED NOT NULL,
  status VARCHAR(32) NOT NULL,
  authenticated_at DATETIME(6) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  revoked_at DATETIME(6) NULL,
  PRIMARY KEY (mount_session_id),
  UNIQUE KEY uq_plugin_mount_asset_token_hash (asset_token_hash),
  KEY ix_plugin_mount_installation (installation_id, status, expires_at),
  KEY ix_plugin_mount_user (tenant_id, user_id, status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
