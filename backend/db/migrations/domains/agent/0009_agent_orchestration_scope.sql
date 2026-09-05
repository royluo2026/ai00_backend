ALTER TABLE workmanship_agent_orch_panoramas
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL AFTER tenant_gid;

CREATE INDEX IF NOT EXISTS idx_agent_orch_panorama_scope
  ON workmanship_agent_orch_panoramas (tenant_gid, project_gid, updated_at);

-- Child projections carry their own scope for defense in depth. They remain
-- nullable during the compatibility window; existing rows are backfilled by
-- the operator before the project scope is made mandatory.
ALTER TABLE workmanship_agent_orch_versions
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_versions
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_axis_views
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_axis_views
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_business_nodes
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_business_nodes
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_flow_edges
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_flow_edges
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_items
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_items
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_item_edges
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_item_edges
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_capability_bindings
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_capability_bindings
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_context_bindings
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_context_bindings
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_workload_baselines
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_workload_baselines
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_runs
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_runs
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_run_events
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_run_events
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_acceptance_facts
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_acceptance_facts
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_metric_snapshots
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_agent_orch_metric_snapshots
  ADD COLUMN IF NOT EXISTS project_gid VARCHAR(128) NULL;
