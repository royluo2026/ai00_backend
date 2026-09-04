CREATE TABLE IF NOT EXISTS workmanship_agent_orch_panoramas (
    gid CHAR(36) NOT NULL,
    tenant_gid VARCHAR(128) NOT NULL,
    owner_user_gid VARCHAR(191) NOT NULL,
    name VARCHAR(255) NOT NULL,
    current_version_gid CHAR(36) NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_panorama_tenant_updated (tenant_gid, updated_at)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_versions (
    gid CHAR(36) NOT NULL,
    panorama_gid CHAR(36) NOT NULL,
    status VARCHAR(32) NOT NULL,
    mode VARCHAR(32) NOT NULL DEFAULT 'fixed',
    revision BIGINT NOT NULL DEFAULT 1,
    parent_version_gid CHAR(36) NULL,
    catalog_release VARCHAR(128) NULL,
    snapshot_gid VARCHAR(128) NULL,
    updated_by VARCHAR(191) NULL,
    published_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_version_panorama_status (panorama_gid, status)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_axis_views (
    gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    x_items_json JSON NOT NULL,
    y_items_json JSON NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_axis_version (version_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_business_nodes (
    gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    node_key VARCHAR(128) NOT NULL,
    title VARCHAR(255) NOT NULL,
    objective TEXT NULL,
    owner_ref VARCHAR(255) NULL,
    x_item_key VARCHAR(128) NOT NULL,
    y_item_key VARCHAR(128) NOT NULL,
    position_json JSON NULL,
    inputs_json JSON NULL,
    outputs_json JSON NULL,
    acceptance_json JSON NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    UNIQUE KEY uq_agent_orch_node_version_key (version_gid, node_key),
    KEY idx_agent_orch_node_coordinates (version_gid, y_item_key, x_item_key)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_flow_edges (
    gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    edge_type VARCHAR(32) NOT NULL,
    source_node_gid CHAR(36) NOT NULL,
    target_node_gid CHAR(36) NOT NULL,
    label VARCHAR(255) NULL,
    route_points_json JSON NULL,
    metadata_json JSON NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_flow_version_type (version_gid, edge_type)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_items (
    gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    business_node_gid CHAR(36) NOT NULL,
    item_type VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    sequence_no INT NOT NULL DEFAULT 0,
    config_json JSON NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_item_node_sequence (business_node_gid, sequence_no)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_item_edges (
    gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    source_item_gid CHAR(36) NOT NULL,
    target_item_gid CHAR(36) NOT NULL,
    relation_type VARCHAR(32) NOT NULL,
    sequence_no INT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_item_edge_source (version_gid, source_item_gid, relation_type)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_capability_bindings (
    gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    source_item_gid CHAR(36) NOT NULL,
    capability_id VARCHAR(128) NULL,
    capability_version_gid VARCHAR(128) NOT NULL,
    purpose VARCHAR(500) NOT NULL,
    version_constraint VARCHAR(64) NULL,
    input_mapping_json JSON NULL,
    output_mapping_json JSON NULL,
    authorization_scope_json JSON NULL,
    execution_policy_json JSON NULL,
    evidence_policy_json JSON NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    UNIQUE KEY uq_agent_orch_cap_binding (version_gid, source_item_gid, capability_version_gid, purpose),
    KEY idx_agent_orch_capability_ref (capability_version_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_context_bindings (
    gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    source_item_gid CHAR(36) NOT NULL,
    ref_type VARCHAR(32) NOT NULL,
    ref_gid VARCHAR(128) NOT NULL,
    ref_version VARCHAR(128) NULL,
    snapshot_gid VARCHAR(128) NULL,
    purpose VARCHAR(500) NOT NULL,
    metadata_json JSON NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    UNIQUE KEY uq_agent_orch_context_binding (version_gid, source_item_gid, ref_type, ref_gid, purpose),
    KEY idx_agent_orch_context_ref (ref_type, ref_gid)
);
