ALTER TABLE workmanship_base_capability_approvals
  ADD COLUMN IF NOT EXISTS catalog_release VARCHAR(64) NULL AFTER major_version;

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_capability_approvals
SET catalog_release = 'legacy:unbound'
WHERE catalog_release IS NULL;

ALTER TABLE workmanship_base_capability_approvals
  MODIFY COLUMN catalog_release VARCHAR(64) NOT NULL;
