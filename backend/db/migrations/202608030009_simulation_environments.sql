CREATE TABLE IF NOT EXISTS workmanship_sim_environments (
    gid VARCHAR(128) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    owner_gid VARCHAR(128) NOT NULL,
    team_gid VARCHAR(128) NULL,
    source_bop_version_gid VARCHAR(128) NOT NULL,
    source_bop_revision INT NOT NULL,
    source_bop_hash CHAR(64) NOT NULL,
    execution_plan_snapshot_uri VARCHAR(2048) NOT NULL,
    pinned_source JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sim_environment_owner (owner_gid, updated_at),
    INDEX idx_sim_environment_team (team_gid, updated_at),
    INDEX idx_sim_environment_source (source_bop_version_gid, source_bop_revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
