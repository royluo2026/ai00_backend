CREATE TABLE IF NOT EXISTS workmanship_base_domain_inbox (
    tenant_gid VARCHAR(128) NOT NULL, event_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(128) NOT NULL, event_version INT NOT NULL,
    producer_domain VARCHAR(64) NOT NULL, envelope_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL, completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_base_search_projection (
    tenant_gid VARCHAR(128) NOT NULL, subject_ref VARCHAR(255) NOT NULL,
    source_domain VARCHAR(64) NOT NULL, source_version BIGINT NOT NULL,
    revision_ref VARCHAR(255) NOT NULL, updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, subject_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
