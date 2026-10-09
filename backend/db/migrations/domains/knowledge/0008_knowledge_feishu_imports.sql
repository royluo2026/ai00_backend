-- Accepted Feishu conversion and local Markdown head are separate identities.
CREATE TABLE IF NOT EXISTS workmanship_know_feishu_baselines (
  source_gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  snapshot_gid VARCHAR(128) NOT NULL,
  accepted_revision_gid VARCHAR(128) NOT NULL,
  updated_by VARCHAR(128) NOT NULL,
  updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS workmanship_know_feishu_imports (
  gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  source_gid VARCHAR(128) NOT NULL,
  snapshot_gid VARCHAR(128) NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  request_sha256 CHAR(64) NOT NULL,
  document_gid VARCHAR(128) NOT NULL,
  revision_gid VARCHAR(128) NOT NULL,
  revision_no BIGINT NOT NULL,
  changed BOOLEAN NOT NULL,
  created_by VARCHAR(128) NOT NULL,
  created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_know_feishu_import_request (tenant_gid,idempotency_key),
  KEY idx_know_feishu_import_source (tenant_gid,source_gid,created_at)
);
