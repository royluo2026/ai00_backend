-- Persist the tenant boundary used by bounded Agent canvas queries.
-- Existing NULL rows deliberately remain unavailable until explicitly re-owned.
ALTER TABLE workmanship_app_flows
  ADD COLUMN IF NOT EXISTS team_gid VARCHAR(191) NULL AFTER owner_user_gid;

ALTER TABLE workmanship_app_skills
  ADD COLUMN IF NOT EXISTS team_gid VARCHAR(191) NULL AFTER owner_gid;

CREATE INDEX IF NOT EXISTS idx_agent_flows_team_owner_updated
  ON workmanship_app_flows (team_gid, owner_user_gid, updated_at);

CREATE INDEX IF NOT EXISTS idx_agent_skills_team_owner_scope
  ON workmanship_app_skills (team_gid, owner_gid, scope, status);
