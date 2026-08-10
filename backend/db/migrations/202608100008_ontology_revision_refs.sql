ALTER TABLE workmanship_base_ontology_releases
  ADD COLUMN IF NOT EXISTS revision_commit_id VARCHAR(64) NULL;

CREATE INDEX IF NOT EXISTS ix_ontology_release_revision_commit
  ON workmanship_base_ontology_releases (revision_commit_id);
