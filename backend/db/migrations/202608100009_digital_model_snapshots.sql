CREATE TABLE IF NOT EXISTS workmanship_model_models (
    model_id VARCHAR(128) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    project_ref VARCHAR(255) NOT NULL,
    owner_gid VARCHAR(128) NOT NULL,
    team_gid VARCHAR(128) NULL,
    latest_version_id VARCHAR(128) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_model_project (project_ref, updated_at),
    INDEX idx_model_owner (owner_gid, updated_at),
    INDEX idx_model_team (team_gid, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_model_versions (
    version_id VARCHAR(128) PRIMARY KEY,
    model_id VARCHAR(128) NOT NULL,
    version_label VARCHAR(128) NOT NULL,
    parent_version_id VARCHAR(128) NULL,
    snapshot_hash VARCHAR(72) NOT NULL,
    artifact_id VARCHAR(256) NOT NULL,
    artifact_media_type VARCHAR(255) NOT NULL,
    artifact_sha256 CHAR(64) NOT NULL,
    artifact_byte_size BIGINT NOT NULL,
    artifact_version INT NOT NULL,
    snapshot_json JSON NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_model_version_label (model_id, version_label),
    UNIQUE KEY uq_model_snapshot_hash (model_id, snapshot_hash),
    INDEX idx_model_version_parent (model_id, parent_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_model_components (
    version_id VARCHAR(128) NOT NULL,
    component_id VARCHAR(256) NOT NULL,
    parent_component_id VARCHAR(256) NULL,
    name VARCHAR(512) NOT NULL,
    component_type VARCHAR(64) NOT NULL,
    geometry_summary JSON NOT NULL,
    PRIMARY KEY (version_id, component_id),
    INDEX idx_model_component_parent (version_id, parent_component_id),
    INDEX idx_model_component_name (version_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
