-- Scope columns become mandatory in one self-contained DDL migration.  There
-- is deliberately no long-lived synthetic tenant/project default: if a legacy
-- database still contains NULL scope, this migration fails closed and requires
-- an auditable tenant/project backfill before the schema can be promoted.
ALTER TABLE workmanship_agent_orch_panoramas MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_versions MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_axis_views MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_business_nodes MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_flow_edges MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_items MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_item_edges MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_capability_bindings MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_context_bindings MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_workload_baselines MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_runs MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_run_events MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_acceptance_facts MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_agent_orch_metric_snapshots MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL, MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
