-- Immutable attribution for human, Agent and plugin-authored Knowledge revisions.
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS channel VARCHAR(32) NOT NULL DEFAULT 'web';
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS delegated_user_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS agent_run_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS plugin_id VARCHAR(128) NULL;
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS plugin_version VARCHAR(128) NULL;
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS request_id VARCHAR(128) NULL;
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS before_sha256 CHAR(64) NULL;
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS after_sha256 CHAR(64) NULL;
ALTER TABLE workmanship_know_revisions ADD COLUMN IF NOT EXISTS change_summary VARCHAR(2048) NULL;
