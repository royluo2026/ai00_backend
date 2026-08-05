-- Align the BOP version table with the fields used by the Craft runtime.
ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS version_type VARCHAR(32) NOT NULL DEFAULT 'working';
ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS visibility VARCHAR(32) NOT NULL DEFAULT 'team';
ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS shared_team_gid CHAR(36) NULL;
ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS shared_project_gid CHAR(36) NULL;
ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS data_stage VARCHAR(64) NULL;
ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS snapshot_data JSON NULL;