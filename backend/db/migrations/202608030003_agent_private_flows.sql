ALTER TABLE workmanship_app_flows
    ADD COLUMN IF NOT EXISTS owner_user_gid VARCHAR(191) NOT NULL DEFAULT '' AFTER gid;

CREATE INDEX IF NOT EXISTS idx_agent_flows_owner_updated
    ON workmanship_app_flows (owner_user_gid, updated_at);
