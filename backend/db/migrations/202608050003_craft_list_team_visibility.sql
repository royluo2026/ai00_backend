-- Complete the Craft list visibility contract used by the web client.
ALTER TABLE workmanship_work_lists
    ADD COLUMN IF NOT EXISTS shared_team_gid CHAR(36) NULL;

CREATE INDEX IF NOT EXISTS idx_lists_shared_team
    ON workmanship_work_lists (shared_team_gid);