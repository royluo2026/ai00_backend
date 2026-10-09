-- Reviewable semantic card suggestions belong to Knowledge until a domain owner accepts them.
CREATE TABLE IF NOT EXISTS workmanship_know_extraction_candidates (
  gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  document_gid VARCHAR(128) NOT NULL,
  revision_gid VARCHAR(128) NOT NULL,
  card_type VARCHAR(16) NOT NULL,
  title VARCHAR(255) NOT NULL,
  body TEXT NOT NULL,
  evidence_text TEXT NOT NULL,
  evidence_from INT NOT NULL,
  evidence_to INT NOT NULL,
  evidence_sha256 CHAR(64) NOT NULL,
  target_gid VARCHAR(128) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'draft',
  created_by VARCHAR(128) NOT NULL,
  updated_by VARCHAR(128) NOT NULL,
  created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY idx_know_extraction_document (tenant_gid,document_gid,created_at),
  KEY idx_know_extraction_status (tenant_gid,status,card_type)
);
