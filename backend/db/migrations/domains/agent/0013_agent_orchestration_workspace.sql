CREATE TABLE IF NOT EXISTS workmanship_agent_orch_workspaces (
    version_gid CHAR(36) NOT NULL,
    tenant_gid VARCHAR(128) NOT NULL,
    project_gid VARCHAR(128) NULL,
    definition_json JSON NOT NULL,
    PRIMARY KEY (version_gid),
    KEY idx_agent_orch_workspace_scope (tenant_gid, project_gid)
);
