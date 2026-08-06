CREATE TABLE IF NOT EXISTS workmanship_craft_validation_policies (
    gid VARCHAR(128) PRIMARY KEY,
    policy_kind VARCHAR(32) NOT NULL,
    policy_version VARCHAR(128) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    test_evidence_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'published',
    published_by VARCHAR(128) NOT NULL,
    published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_craft_validation_policy_version (policy_kind, policy_version),
    UNIQUE KEY uq_craft_validation_policy_hash (content_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_craft_validation_policy_checks (
    policy_gid VARCHAR(128) NOT NULL,
    check_id VARCHAR(128) NOT NULL,
    source_ref VARCHAR(1024) NOT NULL,
    source_kind VARCHAR(32) NOT NULL,
    owner VARCHAR(128) NOT NULL,
    scope_ref VARCHAR(512) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    mechanism VARCHAR(128) NOT NULL,
    check_version VARCHAR(128) NOT NULL,
    threshold_value VARCHAR(1024) NOT NULL,
    algorithm_ref VARCHAR(1024) NOT NULL,
    verified TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (policy_gid, check_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
