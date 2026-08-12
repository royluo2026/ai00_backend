CREATE TABLE IF NOT EXISTS workmanship_base_schema_migrations (
    migration_id VARCHAR(64) PRIMARY KEY,
    applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_base_approvals (
    tenant_gid VARCHAR(64) NOT NULL,
    approval_id VARCHAR(64) NOT NULL,
    subject_ref VARCHAR(191) NOT NULL,
    requester_gid VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    expected_state VARCHAR(32) NOT NULL,
    request_json JSON NOT NULL,
    decision_json JSON NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, approval_id),
    KEY idx_base_approval_subject (tenant_gid, subject_ref, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_base_notifications (
    tenant_gid VARCHAR(64) NOT NULL,
    notification_id VARCHAR(64) NOT NULL,
    recipient_gid VARCHAR(64) NOT NULL,
    subject_ref VARCHAR(191) NOT NULL,
    payload_json JSON NOT NULL,
    read_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, notification_id),
    KEY idx_base_notification_recipient (tenant_gid, recipient_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_base_notification_preferences (
    tenant_gid VARCHAR(64) NOT NULL,
    user_gid VARCHAR(64) NOT NULL,
    version BIGINT NOT NULL,
    preferences_json JSON NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, user_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_base_workspace_templates (
    tenant_gid VARCHAR(64) NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    version BIGINT NOT NULL,
    template_json JSON NOT NULL,
    published_by VARCHAR(64) NOT NULL,
    published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (tenant_gid, template_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
