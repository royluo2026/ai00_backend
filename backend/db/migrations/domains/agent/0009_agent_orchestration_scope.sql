ALTER TABLE workmanship_agent_orch_panoramas
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL AFTER tenant_gid;

CREATE INDEX IF NOT EXISTS idx_agent_orch_panorama_scope
  ON workmanship_agent_orch_panoramas (tenant_gid, project_gid, updated_at);
