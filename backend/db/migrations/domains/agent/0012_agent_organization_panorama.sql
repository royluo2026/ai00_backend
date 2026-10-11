-- Organization graph definitions have no project. Execution evidence remains project-scoped.
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_panoramas ADD COLUMN IF NOT EXISTS scope_kind VARCHAR(32) NOT NULL DEFAULT 'project';
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_panoramas MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_versions MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_axis_views MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_business_nodes MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_flow_edges MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_items MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_item_edges MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_capability_bindings MODIFY COLUMN project_gid VARCHAR(128) NULL;
-- AI00: RESUMABLE NULLABILITY
ALTER TABLE workmanship_agent_orch_context_bindings MODIFY COLUMN project_gid VARCHAR(128) NULL;

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_organization_roots (
    tenant_gid VARCHAR(128) NOT NULL,
    panorama_gid CHAR(36) NULL,
    PRIMARY KEY (tenant_gid),
    UNIQUE KEY uq_agent_orch_organization_panorama (panorama_gid)
);
