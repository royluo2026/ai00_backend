-- Feishu Bitable is the authoritative membership index. No upstream writes.
CREATE TABLE IF NOT EXISTS workmanship_know_feishu_catalog_config (
  tenant_gid VARCHAR(128) PRIMARY KEY,
  source_url VARCHAR(2048) NOT NULL,
  app_token VARCHAR(128) NOT NULL,
  table_id VARCHAR(128) NOT NULL,
  updated_by VARCHAR(128) NOT NULL,
  updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS workmanship_know_feishu_sources (
  gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  catalog_record_gid VARCHAR(128) NOT NULL,
  document_url VARCHAR(2048) NOT NULL,
  document_token VARCHAR(128) NOT NULL,
  linked_document_gid VARCHAR(128) NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_know_feishu_source_record (tenant_gid, catalog_record_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_know_feishu_catalog_records (
  gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  record_id VARCHAR(128) NOT NULL,
  title VARCHAR(512) NOT NULL,
  document_url VARCHAR(2048) NULL,
  document_token VARCHAR(128) NULL,
  source_gid VARCHAR(128) NULL,
  error_code VARCHAR(128) NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_know_feishu_catalog_record (tenant_gid, record_id),
  KEY idx_know_feishu_catalog_status (tenant_gid, active, updated_at)
);
