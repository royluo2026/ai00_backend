-- Document maturity is independent of immutable revision numbering.
ALTER TABLE workmanship_know_documents
  ADD COLUMN maturity VARCHAR(2) NOT NULL DEFAULT 'V1';

CREATE TABLE IF NOT EXISTS workmanship_know_document_maturity_events (
  gid VARCHAR(128) PRIMARY KEY,
  tenant_gid VARCHAR(128) NOT NULL,
  document_gid VARCHAR(128) NOT NULL,
  from_maturity VARCHAR(2) NOT NULL,
  to_maturity VARCHAR(2) NOT NULL,
  changed_by VARCHAR(128) NOT NULL,
  changed_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_know_maturity_document (document_gid, changed_at)
);

-- Drafts are private working copies; they do not consume revision numbers.
CREATE TABLE IF NOT EXISTS workmanship_know_document_drafts (
  document_gid VARCHAR(128) NOT NULL,
  user_gid VARCHAR(128) NOT NULL,
  tenant_gid VARCHAR(128) NOT NULL,
  base_revision_gid VARCHAR(128) NOT NULL,
  markdown LONGTEXT NOT NULL,
  updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (document_gid, user_gid)
);

-- Historical team-wide grants cannot confer editor rights. User grants remain intact.
DELETE FROM workmanship_know_document_acl
WHERE subject_type='team' AND permission IN ('edit','admin');
