-- Immutable source candidates remain separate from accepted OIS document revisions.
CREATE TABLE IF NOT EXISTS workmanship_know_feishu_snapshots (
  gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  source_gid VARCHAR(128) NOT NULL,
  document_token VARCHAR(128) NOT NULL,
  object_key VARCHAR(1024) NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  byte_size BIGINT NOT NULL,
  anchors_json JSON NOT NULL,
  diagnostics_json JSON NOT NULL,
  complete BOOLEAN NOT NULL,
  created_by VARCHAR(128) NOT NULL,
  created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_know_source_snapshot (tenant_gid,source_gid,created_at)
);

CREATE TABLE IF NOT EXISTS workmanship_know_feishu_assets (
  gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  snapshot_gid VARCHAR(128) NOT NULL,
  source_gid VARCHAR(128) NOT NULL,
  feishu_token VARCHAR(128) NOT NULL,
  object_key VARCHAR(1024) NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  byte_size BIGINT NOT NULL,
  media_type VARCHAR(128) NOT NULL,
  created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_know_feishu_asset_snapshot (tenant_gid,snapshot_gid),
  UNIQUE KEY uq_know_feishu_asset_identity (tenant_gid,source_gid,feishu_token,content_sha256)
);
