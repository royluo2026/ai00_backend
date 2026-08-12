-- Project Management owns this schema and is migrated with its DDL credential.
CREATE TABLE IF NOT EXISTS `workmanship_project_management_schema_migrations` (
    migration_id VARCHAR(64) PRIMARY KEY,
    applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `workmanship_app_wb_annotations` (
    `key`      VARCHAR(500) PRIMARY KEY,
    data       VARCHAR(8192) NOT NULL DEFAULT ('{}'),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_app_workbench_configs` (
    gid        CHAR(36) PRIMARY KEY,
    owner_type VARCHAR(255) NOT NULL DEFAULT ('user'),
    owner_gid  TEXT NOT NULL,
    name       VARCHAR(512) NOT NULL DEFAULT ('工作台'),
    sort_order INT NOT NULL DEFAULT 0,
    widgets    JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_app_workbench_member_overrides` (
    gid           CHAR(36) PRIMARY KEY,
    workbench_gid CHAR(36) NOT NULL,
    user_gid      CHAR(36) NOT NULL,
    widgets       JSON NOT NULL,
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_wb_overrides (workbench_gid, user_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_proj_approval_orders` (
    gid           CHAR(36) PRIMARY KEY,
    project_gid   CHAR(36) DEFAULT NULL,
    order_type    VARCHAR(255) NOT NULL DEFAULT ('general'),
    title         VARCHAR(512) NOT NULL DEFAULT (''),
    applicant_gid CHAR(36) NOT NULL,
    reviewer_gid  CHAR(36) DEFAULT NULL,
    status        VARCHAR(255) NOT NULL DEFAULT ('pending'),
    source_ref    TEXT,
    content       JSON NOT NULL,
    opinions      JSON NOT NULL,
    share_scope   VARCHAR(255) NOT NULL DEFAULT ('project'),
    meta          JSON NOT NULL,
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_proj_collab_sessions` (
    gid         CHAR(36) PRIMARY KEY,
    section_gid TEXT NOT NULL,
    owner_gid   CHAR(36) NOT NULL,
    status      VARCHAR(255) NOT NULL DEFAULT ('active'),
    participants JSON NOT NULL,
    meta        JSON NOT NULL,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ended_at    DATETIME(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_proj_issues` (
    gid                   CHAR(36) PRIMARY KEY,
    display_id            VARCHAR(255) NOT NULL DEFAULT (''),
    title                 VARCHAR(512) NOT NULL DEFAULT (''),
    description           VARCHAR(2048) NOT NULL DEFAULT (''),
    severity              VARCHAR(255) NOT NULL DEFAULT ('low'),
    status                VARCHAR(255) NOT NULL DEFAULT ('open'),
    owner_gid             VARCHAR(255) NOT NULL DEFAULT (''),
    owner_user_gid        CHAR(36) DEFAULT NULL,
    assignee_team_gid     CHAR(36) DEFAULT NULL,
    project_gid           CHAR(36) DEFAULT NULL,
    tracking_refs         JSON NOT NULL,
    occurrence_root_cause TEXT,
    escape_root_cause     TEXT,
    interim_action        TEXT,
    permanent_action      TEXT,
    source_ref            JSON NOT NULL,
    related_task_gid      CHAR(36) DEFAULT NULL,
    related_knowledge_gid CHAR(36) DEFAULT NULL,
    approval_order_gid    CHAR(36) DEFAULT NULL,
    bop_entry_gid         CHAR(36) DEFAULT NULL,
    share_scope           VARCHAR(255) NOT NULL DEFAULT ('project'),
    list_gid              CHAR(36) DEFAULT NULL,
    attachments           JSON NOT NULL,
    scheduled_date        DATE DEFAULT NULL,
    -- 飞书相关
    feishu_assignee_open_id TEXT,
    feishu_assignee_name    TEXT,
    feishu_group_chat_id    TEXT,
    feishu_group_name       TEXT,
    feishu_groups           JSON,
    feishu_docs             JSON,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_proj_projects` (
    gid               CHAR(36) PRIMARY KEY,
    name              VARCHAR(512) NOT NULL DEFAULT (''),
    project_code      VARCHAR(255) NOT NULL DEFAULT (''),
    model_year        INT DEFAULT NULL,
    suffix            VARCHAR(255) NOT NULL DEFAULT (''),
    description       VARCHAR(2048) NOT NULL DEFAULT (''),
    status            VARCHAR(255) NOT NULL DEFAULT ('preparing'),
    vehicle_model_gid CHAR(36) DEFAULT NULL,
    team_id           CHAR(36) DEFAULT NULL,
    owner_gid         CHAR(36) DEFAULT NULL,
    factory_gid       CHAR(36) DEFAULT NULL,
    share_scope       VARCHAR(255) NOT NULL DEFAULT ('team'),
    jph               DOUBLE DEFAULT NULL,
    is_deleted        TINYINT(1) NOT NULL DEFAULT 0,
    is_archived       TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at        DATETIME(6) DEFAULT NULL,
    archived_at       DATETIME(6) DEFAULT NULL,
    project_type      VARCHAR(255) NOT NULL DEFAULT ('active'),
    meta              JSON NOT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_proj_task_dependencies` (
    gid           CHAR(36) PRIMARY KEY,
    source_gid    CHAR(36) NOT NULL,
    target_gid    CHAR(36) NOT NULL,
    edge_type     VARCHAR(255) NOT NULL DEFAULT ('prerequisite'),
    dep_condition VARCHAR(255) NOT NULL DEFAULT ('done'),
    dep_group     TEXT,
    label         VARCHAR(512) NOT NULL DEFAULT (''),
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_proj_tasks` (
    gid                  CHAR(36) PRIMARY KEY,
    display_id           VARCHAR(255) NOT NULL DEFAULT (''),
    title                VARCHAR(512) NOT NULL DEFAULT (''),
    description          VARCHAR(2048) NOT NULL DEFAULT (''),
    owner_gid            VARCHAR(255) NOT NULL DEFAULT (''),
    owner_user_gid       CHAR(36) DEFAULT NULL,
    assignee_team_gid    CHAR(36) DEFAULT NULL,
    project_gid          CHAR(36) DEFAULT NULL,
    status               VARCHAR(255) NOT NULL DEFAULT ('pending'),
    priority             VARCHAR(255) NOT NULL DEFAULT ('normal'),
    source_ref           JSON NOT NULL,
    review_date          TEXT,
    meeting_level        VARCHAR(255) NOT NULL DEFAULT ('none'),
    meeting_doc_link     TEXT,
    progress_logs        JSON NOT NULL,
    due_date             TEXT,
    plan_start           TEXT,
    plan_end             TEXT,
    actual_start         TEXT,
    actual_end           TEXT,
    share_scope          VARCHAR(255) NOT NULL DEFAULT ('project'),
    list_gid             CHAR(36) DEFAULT NULL,
    attachments          JSON NOT NULL,
    -- 软删除
    is_deleted           TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at           DATETIME(6) DEFAULT NULL,
    -- 时间线
    scheduled_date       DATE DEFAULT NULL,
    scheduled_start_time TIME DEFAULT NULL,
    time_estimate        INT DEFAULT NULL,
    -- 画布视图
    parent_task_gid      CHAR(36) DEFAULT NULL,
    canvas_x             DOUBLE DEFAULT NULL,
    canvas_y             DOUBLE DEFAULT NULL,
    completion           INT NOT NULL DEFAULT 0,
    node_type            VARCHAR(255) NOT NULL DEFAULT ('normal'),
    canvas_icon          VARCHAR(255) NOT NULL DEFAULT ('star'),
    canvas_row_gid       CHAR(36) DEFAULT NULL,
    canvas_col_gid       CHAR(36) DEFAULT NULL,
    -- 飞书相关
    feishu_assignee_open_id TEXT,
    feishu_assignee_name    TEXT,
    feishu_group_chat_id    TEXT,
    feishu_group_name       TEXT,
    feishu_groups           JSON,
    feishu_docs             JSON,
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_proj_vehicle_models` (
    gid          CHAR(36) PRIMARY KEY,
    name         VARCHAR(512) NOT NULL DEFAULT (''),
    brand        VARCHAR(255) NOT NULL DEFAULT (''),
    platform     VARCHAR(255) NOT NULL DEFAULT (''),
    vehicle_type VARCHAR(255) DEFAULT (''),
    team_id      CHAR(36) DEFAULT NULL,
    meta         JSON NOT NULL,
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_follows` (
    gid        CHAR(36) PRIMARY KEY,
    user_gid   CHAR(36) NOT NULL,
    item_type  TEXT NOT NULL,
    item_gid   TEXT NOT NULL,
    item_title VARCHAR(512) NOT NULL DEFAULT (''),
    notify_on  VARCHAR(255) NOT NULL DEFAULT ('key_changes'),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_follows (user_gid, item_type(32), item_gid(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_issues` (
    gid                   CHAR(36) PRIMARY KEY,
    display_id            VARCHAR(255) NOT NULL DEFAULT (''),
    title                 VARCHAR(512) NOT NULL DEFAULT (''),
    description           VARCHAR(2048) NOT NULL DEFAULT (''),
    severity              VARCHAR(255) NOT NULL DEFAULT ('low'),
    status                VARCHAR(255) NOT NULL DEFAULT ('open'),
    owner_gid             VARCHAR(255) NOT NULL DEFAULT (''),
    owner_user_gid        CHAR(36) DEFAULT NULL,
    assignee_team_gid     CHAR(36) DEFAULT NULL,
    project_gid           CHAR(36) DEFAULT NULL,
    tracking_refs         JSON NOT NULL,
    occurrence_root_cause TEXT,
    escape_root_cause     TEXT,
    interim_action        TEXT,
    permanent_action      TEXT,
    source_ref            JSON NOT NULL,
    related_task_gid      CHAR(36) DEFAULT NULL,
    related_knowledge_gid CHAR(36) DEFAULT NULL,
    approval_order_gid    CHAR(36) DEFAULT NULL,
    bop_entry_gid         CHAR(36) DEFAULT NULL,
    share_scope           VARCHAR(255) NOT NULL DEFAULT ('project'),
    list_gid              CHAR(36) DEFAULT NULL,
    attachments           JSON NOT NULL,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_item_change_logs` (
    gid VARCHAR(128) PRIMARY KEY,
    item_type VARCHAR(64) NOT NULL,
    item_gid VARCHAR(128) NOT NULL,
    list_gid VARCHAR(128) NULL,
    changed_by VARCHAR(128) NOT NULL,
    changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    field_name VARCHAR(255) NOT NULL,
    old_value LONGTEXT NULL,
    new_value LONGTEXT NULL,
    INDEX idx_change_logs_item (item_type, item_gid),
    INDEX idx_change_logs_list (list_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_item_entries` (
    gid           CHAR(36) PRIMARY KEY,
    id            TEXT NOT NULL,
    item_type     TEXT NOT NULL,
    item_gid      TEXT NOT NULL,
    parent_id     TEXT,
    section       VARCHAR(255) NOT NULL DEFAULT ('detail'),
    author        VARCHAR(255) NOT NULL DEFAULT ('human'),
    author_name   VARCHAR(512) DEFAULT (''),
    author_gid    VARCHAR(255) DEFAULT (''),
    content       LONGTEXT NULL,
    resolved      TINYINT(1) NOT NULL DEFAULT 0,
    sort_order    DOUBLE NOT NULL DEFAULT 0,
    read_by_human TINYINT(1) NOT NULL DEFAULT 1,
    ai_status     VARCHAR(255) DEFAULT ('unread'),
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_item_shares` (
    gid VARCHAR(128) PRIMARY KEY,
    item_type VARCHAR(64) NOT NULL,
    item_gid VARCHAR(128) NOT NULL,
    shared_to VARCHAR(128) NOT NULL,
    permission VARCHAR(32) NOT NULL DEFAULT 'read',
    shared_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_item_shares_target (item_type, item_gid, shared_to),
    INDEX idx_item_shares_user (shared_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_list_bitable_bindings` (
    list_gid VARCHAR(128) PRIMARY KEY,
    app_token VARCHAR(512) NOT NULL,
    table_id VARCHAR(255) NOT NULL,
    field_mapping JSON NOT NULL,
    sync_enabled TINYINT(1) NOT NULL DEFAULT 1,
    webhook_secret VARCHAR(512) NULL,
    has_remote_updates TINYINT(1) NOT NULL DEFAULT 0,
    last_push_at DATETIME(6) NULL,
    last_pull_at DATETIME(6) NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at DATETIME(6) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_list_bitable_record_map` (
    list_gid VARCHAR(128) NOT NULL,
    item_gid VARCHAR(128) NOT NULL,
    record_id VARCHAR(255) NOT NULL,
    ai00_updated_at DATETIME(6) NULL,
    feishu_updated_at DATETIME(6) NULL,
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at DATETIME(6) NULL,
    PRIMARY KEY (list_gid, item_gid),
    INDEX idx_bitable_record_map_record (list_gid, record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_list_shares` (
    gid VARCHAR(128) PRIMARY KEY,
    list_gid VARCHAR(128) NOT NULL,
    shared_to VARCHAR(128) NOT NULL,
    permission VARCHAR(32) NOT NULL DEFAULT 'read',
    shared_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_list_shares_target (list_gid, shared_to),
    INDEX idx_list_shares_user (shared_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_lists` (
    gid           CHAR(36) PRIMARY KEY,
    name          TEXT NOT NULL,
    color         VARCHAR(255) NOT NULL DEFAULT ('#5b8dee'),
    storage_scope VARCHAR(255) NOT NULL DEFAULT ('cloud'),
    owner_type    VARCHAR(255) NOT NULL DEFAULT ('user'),
    owner_gid     VARCHAR(255) NOT NULL DEFAULT (''),
    creator_gid   VARCHAR(255) NOT NULL DEFAULT (''),
    item_type     VARCHAR(255) NOT NULL DEFAULT ('task'),
    sort_order    INT NOT NULL DEFAULT 0,
    visibility    VARCHAR(255) NOT NULL DEFAULT ('team'),
    project_gid   CHAR(36) DEFAULT NULL,
    shared_team_gid CHAR(36) DEFAULT NULL,
    read_scope    TEXT,
    write_scope   TEXT,
    deleted_at    DATETIME(6) DEFAULT NULL,
    created_at    DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_notifications` (
    gid        CHAR(36) PRIMARY KEY,
    user_gid   CHAR(36) NOT NULL,
    type       TEXT NOT NULL,
    item_type  TEXT,
    item_gid   TEXT,
    title      VARCHAR(512) NOT NULL DEFAULT (''),
    body       LONGTEXT NULL,
    is_read    TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_permission_requests` (
    gid VARCHAR(128) PRIMARY KEY,
    requester_gid VARCHAR(128) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    target_gid VARCHAR(128) NOT NULL,
    want_permission VARCHAR(32) NOT NULL DEFAULT 'read',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    message VARCHAR(2048) NOT NULL DEFAULT '',
    responded_by VARCHAR(128) NULL,
    responded_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_perm_req_target (target_type, target_gid),
    INDEX idx_perm_req_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_share_links` (
    token VARCHAR(191) PRIMARY KEY,
    target_type VARCHAR(64) NOT NULL,
    target_gid VARCHAR(128) NOT NULL,
    item_type VARCHAR(64) NULL,
    display_name VARCHAR(512) NOT NULL DEFAULT '',
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NULL,
    INDEX idx_share_links_target (target_type, target_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_task_dependencies` (
    gid CHAR(36) PRIMARY KEY,
    source_gid CHAR(36) NOT NULL,
    target_gid CHAR(36) NOT NULL,
    edge_type VARCHAR(64) NOT NULL DEFAULT ('prerequisite'),
    dep_condition VARCHAR(64) NOT NULL DEFAULT ('done'),
    dep_group TEXT NULL,
    label VARCHAR(512) NOT NULL DEFAULT (''),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_work_task_deps_src (source_gid),
    INDEX idx_work_task_deps_tgt (target_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_task_template_items` (
    gid             CHAR(36) PRIMARY KEY,
    template_gid    CHAR(36) NOT NULL,
    title_pattern   TEXT NOT NULL,
    description     VARCHAR(2048) NOT NULL DEFAULT (''),
    priority        VARCHAR(255) NOT NULL DEFAULT ('normal'),
    assignee_role   TEXT,
    due_offset_days INT DEFAULT NULL,
    share_scope     VARCHAR(255) NOT NULL DEFAULT ('team'),
    sort_order      INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_task_templates` (
    gid         CHAR(36) PRIMARY KEY,
    name        TEXT NOT NULL,
    description VARCHAR(2048) NOT NULL DEFAULT (''),
    scope       VARCHAR(255) NOT NULL DEFAULT ('system'),
    owner_gid   CHAR(36) DEFAULT NULL,
    version     INT NOT NULL DEFAULT 1,
    is_active   TINYINT(1) NOT NULL DEFAULT 1,
    entries     JSON,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workmanship_work_tasks` (
    gid               CHAR(36) PRIMARY KEY,
    display_id        VARCHAR(255) NOT NULL DEFAULT (''),
    title             VARCHAR(512) NOT NULL DEFAULT (''),
    description       VARCHAR(2048) NOT NULL DEFAULT (''),
    owner_gid         VARCHAR(255) NOT NULL DEFAULT (''),
    owner_user_gid    CHAR(36) DEFAULT NULL,
    assignee_team_gid CHAR(36) DEFAULT NULL,
    project_gid       CHAR(36) DEFAULT NULL,
    status            VARCHAR(255) NOT NULL DEFAULT ('pending'),
    priority          VARCHAR(255) NOT NULL DEFAULT ('normal'),
    source_ref        JSON NOT NULL,
    review_date       TEXT,
    meeting_level     VARCHAR(255) NOT NULL DEFAULT ('none'),
    meeting_doc_link  TEXT,
    progress_logs     JSON NOT NULL,
    due_date          TEXT,
    plan_start        TEXT,
    plan_end          TEXT,
    actual_start      TEXT,
    actual_end        TEXT,
    share_scope       VARCHAR(255) NOT NULL DEFAULT ('project'),
    list_gid          CHAR(36) DEFAULT NULL,
    attachments       JSON NOT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
