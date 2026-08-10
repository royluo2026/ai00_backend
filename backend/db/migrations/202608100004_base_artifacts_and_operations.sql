CREATE TABLE IF NOT EXISTS workmanship_base_artifact_upload_sessions (
  upload_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(256) NOT NULL,
  actor_id VARCHAR(256) NOT NULL,
  object_key VARCHAR(1024) NOT NULL,
  media_type VARCHAR(255) NOT NULL,
  expected_sha256 CHAR(64) NOT NULL,
  expected_byte_size BIGINT UNSIGNED NOT NULL,
  resource_refs_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL,
  uploaded_sha256 CHAR(64) NULL,
  uploaded_byte_size BIGINT UNSIGNED NULL,
  artifact_id VARCHAR(64) NULL,
  created_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  PRIMARY KEY (upload_id),
  UNIQUE KEY uq_base_artifact_upload_object (object_key),
  KEY ix_base_artifact_upload_expiry (status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_artifacts (
  artifact_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(256) NOT NULL,
  actor_id VARCHAR(256) NOT NULL,
  object_key VARCHAR(1024) NOT NULL,
  media_type VARCHAR(255) NOT NULL,
  sha256 CHAR(64) NOT NULL,
  byte_size BIGINT UNSIGNED NOT NULL,
  artifact_version INT UNSIGNED NOT NULL,
  resource_refs_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (artifact_id),
  UNIQUE KEY uq_base_artifact_object (object_key),
  KEY ix_base_artifact_tenant_digest (tenant_id, sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_capability_operations (
  operation_id VARCHAR(64) NOT NULL,
  kind VARCHAR(128) NOT NULL,
  tenant_id VARCHAR(256) NOT NULL,
  actor_id VARCHAR(256) NOT NULL,
  consumer_id VARCHAR(256) NOT NULL,
  resource_refs_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL,
  operation_version INT UNSIGNED NOT NULL,
  error_code VARCHAR(128) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  PRIMARY KEY (operation_id),
  KEY ix_base_capability_operation_tenant (tenant_id, created_at),
  KEY ix_base_capability_operation_status (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
