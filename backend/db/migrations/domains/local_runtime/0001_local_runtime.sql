-- Independent Local Runtime database; apply only through AI00_LOCAL_RUNTIME_DDL_DB_URL.
CREATE TABLE IF NOT EXISTS workmanship_runtime_schema_migrations (
    version VARCHAR(128) PRIMARY KEY, checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_runtime_devices (
    gid VARCHAR(128) PRIMARY KEY, owner_user_gid VARCHAR(191) NOT NULL, team_gid VARCHAR(191) NULL,
    display_name VARCHAR(255) NOT NULL, platform VARCHAR(64) NOT NULL DEFAULT 'windows',
    runtime_version VARCHAR(64) NOT NULL DEFAULT '', token_hash CHAR(64) NOT NULL,
    capabilities JSON NULL, status VARCHAR(32) NOT NULL DEFAULT 'offline', last_seen_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_runtime_device_owner (owner_user_gid, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_runtime_enrollments (
    gid VARCHAR(128) PRIMARY KEY, token_hash CHAR(64) NOT NULL UNIQUE, created_by VARCHAR(191) NOT NULL,
    team_gid VARCHAR(191) NULL, display_name VARCHAR(255) NOT NULL, expires_at DATETIME(6) NOT NULL,
    used_at DATETIME(6) NULL, created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_runtime_commands (
    gid VARCHAR(128) PRIMARY KEY, device_gid VARCHAR(128) NOT NULL, capability_id VARCHAR(128) NOT NULL,
    capability_version INT NOT NULL, protocol_version VARCHAR(64) NOT NULL, payload JSON NOT NULL,
    payload_hash CHAR(64) NOT NULL, requested_by VARCHAR(191) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'queued',
    attempts INT NOT NULL DEFAULT 0, expires_at DATETIME(6) NOT NULL, lease_id VARCHAR(128) NULL,
    lease_until DATETIME(6) NULL, result JSON NULL, error VARCHAR(128) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_runtime_command_lease (device_gid, status, expires_at, created_at),
    INDEX idx_runtime_command_owner (requested_by, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
