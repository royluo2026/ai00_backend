-- ════════════════════════════════════════════════════════════════════════
-- AI00 MySQL 8.0 Schema
-- 由 backend/db/schema.sql + bop_schema_v2.sql 合并转换
-- 执行方式：在 MySQL Workbench 或命令行执行
--   mysql -u root -p < mysql_schema.sql
-- ════════════════════════════════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS ai00 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai00;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ════════════════════════════════════════════════════════════════════════
-- auth（身份认证域）
-- ════════════════════════════════════════════════════════════════════════

-- 团队表
CREATE TABLE IF NOT EXISTS workmanship_auth_teams (
    gid               CHAR(36) PRIMARY KEY,
    name              TEXT NOT NULL DEFAULT (''),
    is_active         TINYINT(1) NOT NULL DEFAULT 1,
    config            JSON NOT NULL DEFAULT (JSON_OBJECT()),
    feishu_dept_id    TEXT DEFAULT NULL,
    parent_team_gid   CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE UNIQUE INDEX idx_teams_feishu_dept ON workmanship_auth_teams (feishu_dept_id(191));

-- 用户表
CREATE TABLE IF NOT EXISTS workmanship_auth_users (
    gid               CHAR(36) PRIMARY KEY,
    feishu_open_id    TEXT NOT NULL,
    name              TEXT NOT NULL DEFAULT (''),
    email             TEXT NOT NULL DEFAULT (''),
    avatar_url        TEXT NOT NULL DEFAULT (''),
    -- 系统角色：super_admin / team_admin / project_admin /
    --           rule_admin / knowledge_admin / member / external
    system_role       TEXT NOT NULL DEFAULT ('external'),
    -- 外部子类型：outsource / rd / factory / supplier
    external_subtype  TEXT DEFAULT NULL,
    team_id           CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    is_active         TINYINT(1) NOT NULL DEFAULT 1,
    notification_prefs JSON NOT NULL DEFAULT (JSON_OBJECT()),
    org_role          TEXT DEFAULT NULL,
    feishu_access_token  TEXT NOT NULL DEFAULT (''),
    feishu_refresh_token TEXT NOT NULL DEFAULT (''),
    feishu_token_expires_at DATETIME(6) DEFAULT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_users_feishu_open_id (feishu_open_id(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_users_feishu_id ON workmanship_auth_users (feishu_open_id(191));
CREATE INDEX idx_users_role      ON workmanship_auth_users (system_role(64));
CREATE INDEX idx_users_team      ON workmanship_auth_users (team_id);

-- 项目成员表
CREATE TABLE IF NOT EXISTS workmanship_auth_project_members (
    gid         CHAR(36) PRIMARY KEY,
    project_gid CHAR(36) NOT NULL,
    user_gid    CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
    -- role: project_manager | section_owner | se_owner | bid_owner
    role        TEXT NOT NULL DEFAULT ('project_manager'),
    -- scope_type: project | section | bid_section
    scope_type  TEXT NOT NULL DEFAULT ('project'),
    -- scope_gid: NULL for project_manager
    scope_gid   TEXT DEFAULT NULL,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 同角色同范围唯一索引（简化版，去掉 WHERE 条件）
CREATE UNIQUE INDEX idx_pm_unique_global  ON workmanship_auth_project_members (project_gid, role(64));
CREATE UNIQUE INDEX idx_pm_unique_scoped  ON workmanship_auth_project_members (project_gid, role(64), scope_gid(191));
CREATE INDEX idx_pm_project               ON workmanship_auth_project_members (project_gid);
CREATE INDEX idx_pm_user                  ON workmanship_auth_project_members (user_gid);
CREATE INDEX idx_pm_scope                 ON workmanship_auth_project_members (scope_type(32), scope_gid(191));

-- 标段表
CREATE TABLE IF NOT EXISTS workmanship_auth_bid_sections (
    gid         CHAR(36) PRIMARY KEY,
    project_gid CHAR(36) NOT NULL,
    name        TEXT NOT NULL DEFAULT (''),
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bid_sections_project ON workmanship_auth_bid_sections (project_gid);

-- 登录状态轮询表（OAuth 回调后写入，客户端轮询读取）
CREATE TABLE IF NOT EXISTS workmanship_auth_auth_pending (
    state      VARCHAR(255) PRIMARY KEY,
    jwt        TEXT DEFAULT NULL,
    error      TEXT DEFAULT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 项目成员角色（section_owners）
CREATE TABLE IF NOT EXISTS workmanship_auth_section_owners (
    gid         CHAR(36) PRIMARY KEY,
    project_gid CHAR(36) NOT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE CASCADE,
    user_gid    CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT ('section_owner'),
    section_gid TEXT DEFAULT NULL,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_section_owners_project ON workmanship_auth_section_owners (project_gid);
CREATE INDEX idx_section_owners_user    ON workmanship_auth_section_owners (user_gid);


-- ════════════════════════════════════════════════════════════════════════
-- app（应用配置域）
-- ════════════════════════════════════════════════════════════════════════

-- 全局系统配置表
CREATE TABLE IF NOT EXISTS workmanship_app_system_config (
    `key`       VARCHAR(500) PRIMARY KEY,
    `value`     TEXT NOT NULL DEFAULT (''),
    description TEXT NOT NULL DEFAULT (''),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ════════════════════════════════════════════════════════════════════════
-- proj（项目域）
-- ════════════════════════════════════════════════════════════════════════

-- 车型表
CREATE TABLE IF NOT EXISTS workmanship_proj_vehicle_models (
    gid          CHAR(36) PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT (''),
    brand        TEXT NOT NULL DEFAULT (''),
    platform     TEXT NOT NULL DEFAULT (''),
    vehicle_type TEXT DEFAULT (''),
    team_id      CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    meta         JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 项目表
CREATE TABLE IF NOT EXISTS workmanship_proj_projects (
    gid               CHAR(36) PRIMARY KEY,
    name              TEXT NOT NULL DEFAULT (''),
    project_code      TEXT NOT NULL DEFAULT (''),
    model_year        INT DEFAULT NULL,
    suffix            TEXT NOT NULL DEFAULT (''),
    description       TEXT NOT NULL DEFAULT (''),
    status            TEXT NOT NULL DEFAULT ('preparing'),
    vehicle_model_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_vehicle_models(gid) ON DELETE SET NULL,
    team_id           CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    owner_gid         CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    factory_gid       CHAR(36) DEFAULT NULL REFERENCES workmanship_factory_factories(gid) ON DELETE SET NULL,
    share_scope       TEXT NOT NULL DEFAULT ('team'),
    jph               DOUBLE DEFAULT NULL,
    is_deleted        TINYINT(1) NOT NULL DEFAULT 0,
    is_archived       TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at        DATETIME(6) DEFAULT NULL,
    archived_at       DATETIME(6) DEFAULT NULL,
    project_type      TEXT NOT NULL DEFAULT ('active'),
    meta              JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_projects_team   ON workmanship_proj_projects (team_id);
CREATE INDEX idx_projects_status ON workmanship_proj_projects (status(32));

-- 协同会话表
CREATE TABLE IF NOT EXISTS workmanship_proj_collab_sessions (
    gid         CHAR(36) PRIMARY KEY,
    section_gid TEXT NOT NULL,
    owner_gid   CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT ('active'),
    participants JSON NOT NULL DEFAULT (JSON_ARRAY()),
    meta        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    ended_at    DATETIME(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_collab_sessions_section ON workmanship_proj_collab_sessions (section_gid(191));

-- 审批单表
CREATE TABLE IF NOT EXISTS workmanship_proj_approval_orders (
    gid           CHAR(36) PRIMARY KEY,
    project_gid   CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE SET NULL,
    order_type    TEXT NOT NULL DEFAULT ('general'),
    title         TEXT NOT NULL DEFAULT (''),
    applicant_gid CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
    reviewer_gid  CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT ('pending'),
    source_ref    TEXT DEFAULT NULL,
    content       JSON NOT NULL DEFAULT (JSON_OBJECT()),
    opinions      JSON NOT NULL DEFAULT (JSON_ARRAY()),
    share_scope   TEXT NOT NULL DEFAULT ('project'),
    meta          JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_approval_orders_project   ON workmanship_proj_approval_orders (project_gid);
CREATE INDEX idx_approval_orders_applicant ON workmanship_proj_approval_orders (applicant_gid);
CREATE INDEX idx_approval_orders_status    ON workmanship_proj_approval_orders (status(32));

-- 任务依赖关系表
CREATE TABLE IF NOT EXISTS workmanship_proj_task_dependencies (
    gid           CHAR(36) PRIMARY KEY,
    source_gid    CHAR(36) NOT NULL,
    target_gid    CHAR(36) NOT NULL,
    edge_type     TEXT NOT NULL DEFAULT ('prerequisite'),
    dep_condition TEXT NOT NULL DEFAULT ('done'),
    dep_group     TEXT DEFAULT NULL,
    label         TEXT NOT NULL DEFAULT (''),
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_task_deps_source ON workmanship_proj_task_dependencies (source_gid);
CREATE INDEX idx_task_deps_target ON workmanship_proj_task_dependencies (target_gid);

-- 任务表（proj schema 版，现役）
CREATE TABLE IF NOT EXISTS workmanship_proj_tasks (
    gid                  CHAR(36) PRIMARY KEY,
    display_id           TEXT NOT NULL DEFAULT (''),
    title                TEXT NOT NULL DEFAULT (''),
    description          TEXT NOT NULL DEFAULT (''),
    owner_gid            TEXT NOT NULL DEFAULT (''),
    owner_user_gid       CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    assignee_team_gid    CHAR(36) DEFAULT NULL,
    project_gid          CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT ('pending'),
    priority             TEXT NOT NULL DEFAULT ('normal'),
    source_ref           JSON NOT NULL DEFAULT (JSON_OBJECT()),
    review_date          TEXT DEFAULT NULL,
    meeting_level        TEXT NOT NULL DEFAULT ('none'),
    meeting_doc_link     TEXT DEFAULT NULL,
    progress_logs        JSON NOT NULL DEFAULT (JSON_ARRAY()),
    due_date             TEXT DEFAULT NULL,
    plan_start           TEXT DEFAULT NULL,
    plan_end             TEXT DEFAULT NULL,
    actual_start         TEXT DEFAULT NULL,
    actual_end           TEXT DEFAULT NULL,
    share_scope          TEXT NOT NULL DEFAULT ('project'),
    list_gid             CHAR(36) DEFAULT NULL,
    attachments          JSON NOT NULL DEFAULT (JSON_ARRAY()),
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
    node_type            TEXT NOT NULL DEFAULT ('normal'),
    canvas_icon          TEXT NOT NULL DEFAULT ('star'),
    canvas_row_gid       CHAR(36) DEFAULT NULL,
    canvas_col_gid       CHAR(36) DEFAULT NULL,
    -- 飞书相关
    feishu_assignee_open_id TEXT DEFAULT NULL,
    feishu_assignee_name    TEXT DEFAULT NULL,
    feishu_group_chat_id    TEXT DEFAULT NULL,
    feishu_group_name       TEXT DEFAULT NULL,
    feishu_groups           JSON DEFAULT (JSON_ARRAY()),
    feishu_docs             JSON DEFAULT (JSON_ARRAY()),
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_tasks_owner   ON workmanship_proj_tasks (owner_user_gid);
CREATE INDEX idx_proj_tasks_project ON workmanship_proj_tasks (project_gid);
CREATE INDEX idx_proj_tasks_list    ON workmanship_proj_tasks (list_gid);
CREATE INDEX idx_proj_tasks_status  ON workmanship_proj_tasks (status(32));
CREATE INDEX idx_proj_tasks_deleted ON workmanship_proj_tasks (deleted_at);

-- 问题表（proj schema 版，现役）
CREATE TABLE IF NOT EXISTS workmanship_proj_issues (
    gid                   CHAR(36) PRIMARY KEY,
    display_id            TEXT NOT NULL DEFAULT (''),
    title                 TEXT NOT NULL DEFAULT (''),
    description           TEXT NOT NULL DEFAULT (''),
    severity              TEXT NOT NULL DEFAULT ('low'),
    status                TEXT NOT NULL DEFAULT ('open'),
    owner_gid             TEXT NOT NULL DEFAULT (''),
    owner_user_gid        CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    assignee_team_gid     CHAR(36) DEFAULT NULL,
    project_gid           CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE SET NULL,
    tracking_refs         JSON NOT NULL DEFAULT (JSON_ARRAY()),
    occurrence_root_cause TEXT DEFAULT NULL,
    escape_root_cause     TEXT DEFAULT NULL,
    interim_action        TEXT DEFAULT NULL,
    permanent_action      TEXT DEFAULT NULL,
    source_ref            JSON NOT NULL DEFAULT (JSON_OBJECT()),
    related_task_gid      CHAR(36) DEFAULT NULL,
    related_knowledge_gid CHAR(36) DEFAULT NULL,
    approval_order_gid    CHAR(36) DEFAULT NULL,
    bop_entry_gid         CHAR(36) DEFAULT NULL,
    share_scope           TEXT NOT NULL DEFAULT ('project'),
    list_gid              CHAR(36) DEFAULT NULL,
    attachments           JSON NOT NULL DEFAULT (JSON_ARRAY()),
    scheduled_date        DATE DEFAULT NULL,
    -- 飞书相关
    feishu_assignee_open_id TEXT DEFAULT NULL,
    feishu_assignee_name    TEXT DEFAULT NULL,
    feishu_group_chat_id    TEXT DEFAULT NULL,
    feishu_group_name       TEXT DEFAULT NULL,
    feishu_groups           JSON DEFAULT (JSON_ARRAY()),
    feishu_docs             JSON DEFAULT (JSON_ARRAY()),
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_issues_owner   ON workmanship_proj_issues (owner_user_gid);
CREATE INDEX idx_proj_issues_project ON workmanship_proj_issues (project_gid);
CREATE INDEX idx_proj_issues_status  ON workmanship_proj_issues (status(32));


-- ════════════════════════════════════════════════════════════════════════
-- factory（工厂资源域）
-- ════════════════════════════════════════════════════════════════════════

-- 工厂表
CREATE TABLE IF NOT EXISTS workmanship_factory_factories (
    gid        CHAR(36) PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT (''),
    team_id    CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    meta       JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 工段（物理区域）
CREATE TABLE IF NOT EXISTS workmanship_factory_factory_sections (
    gid         CHAR(36) PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT (''),
    factory_gid CHAR(36) NOT NULL REFERENCES workmanship_factory_factories(gid) ON DELETE CASCADE,
    sort_order  INT NOT NULL DEFAULT 0,
    color       TEXT NOT NULL DEFAULT ('#7287fd'),
    canvas_x    DOUBLE NOT NULL DEFAULT 0,
    canvas_y    DOUBLE NOT NULL DEFAULT 0,
    canvas_w    DOUBLE NOT NULL DEFAULT 400,
    canvas_h    DOUBLE NOT NULL DEFAULT 300,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 物理产线
CREATE TABLE IF NOT EXISTS workmanship_factory_factory_lines (
    gid         CHAR(36) PRIMARY KEY,
    factory_gid CHAR(36) NOT NULL,
    name        TEXT NOT NULL,
    code        TEXT DEFAULT NULL,
    line_type   TEXT DEFAULT NULL,
    description TEXT DEFAULT NULL,
    sort_order  INT NOT NULL DEFAULT 0,
    meta        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by  TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_factory_lines_factory ON workmanship_factory_factory_lines (factory_gid);

-- 工位（物理站位）
CREATE TABLE IF NOT EXISTS workmanship_factory_factory_stations (
    gid                 CHAR(36) PRIMARY KEY,
    code                TEXT NOT NULL DEFAULT (''),
    name                TEXT NOT NULL DEFAULT (''),
    factory_section_gid CHAR(36) NOT NULL REFERENCES workmanship_factory_factory_sections(gid) ON DELETE CASCADE,
    factory_line_gid    CHAR(36) DEFAULT NULL,
    canvas_x            DOUBLE NOT NULL DEFAULT 0,
    canvas_y            DOUBLE NOT NULL DEFAULT 0,
    takt_time           DOUBLE NOT NULL DEFAULT 60,
    height_mm           INT NOT NULL DEFAULT 1200,
    meta                JSON NOT NULL DEFAULT (JSON_OBJECT()),
    ext                 JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_factory_stations_section  ON workmanship_factory_factory_stations (factory_section_gid);
CREATE INDEX idx_factory_sta_line          ON workmanship_factory_factory_stations (factory_line_gid);

-- 工厂工具实物
CREATE TABLE IF NOT EXISTS workmanship_factory_factory_tools (
    gid          CHAR(36) PRIMARY KEY,
    asset_no     TEXT NOT NULL,
    template_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_tpl_vpps_tools(gid) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT ('in_use'),
    team_id      CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    meta         JSON NOT NULL DEFAULT (JSON_OBJECT()),
    ext          JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_factory_tools_asset_no (asset_no(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 工厂设备实物
CREATE TABLE IF NOT EXISTS workmanship_factory_factory_equipments (
    gid          CHAR(36) PRIMARY KEY,
    asset_no     TEXT NOT NULL,
    template_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_tpl_vpps_equipments(gid) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT ('in_use'),
    team_id      CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    meta         JSON NOT NULL DEFAULT (JSON_OBJECT()),
    ext          JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_factory_equip_asset_no (asset_no(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 工厂工装实物
CREATE TABLE IF NOT EXISTS workmanship_factory_factory_fixtures (
    gid          CHAR(36) PRIMARY KEY,
    asset_no     TEXT NOT NULL,
    template_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_tpl_vpps_fixtures(gid) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT ('in_use'),
    team_id      CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    meta         JSON NOT NULL DEFAULT (JSON_OBJECT()),
    ext          JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_factory_fix_asset_no (asset_no(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 工厂布局模板
CREATE TABLE IF NOT EXISTS workmanship_factory_factory_layout_templates (
    gid         CHAR(36) PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT (''),
    factory_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_factory_factories(gid) ON DELETE CASCADE,
    team_id     CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    stations    JSON NOT NULL DEFAULT (JSON_ARRAY()),
    meta        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_layout_tpl_factory ON workmanship_factory_factory_layout_templates (factory_gid);


-- ════════════════════════════════════════════════════════════════════════
-- template（模板库域）
-- ════════════════════════════════════════════════════════════════════════

-- GBOP 版本管理
CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_versions (
    gid                CHAR(36) PRIMARY KEY,
    name               TEXT NOT NULL DEFAULT (''),
    version_family_gid TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT ('draft'),
    frozen_at          DATETIME(6) DEFAULT NULL,
    archived_at        DATETIME(6) DEFAULT NULL,
    vehicle_model      TEXT NOT NULL DEFAULT (''),
    team_id            CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    created_by         CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- GBOP 树形节点
CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_entries (
    gid               CHAR(36) PRIMARY KEY,
    version_gid       CHAR(36) NOT NULL REFERENCES workmanship_tpl_gbop_versions(gid) ON DELETE CASCADE,
    parent_gid        CHAR(36) DEFAULT NULL REFERENCES workmanship_tpl_gbop_entries(gid) ON DELETE SET NULL,
    level             SMALLINT NOT NULL DEFAULT 0,
    node_type         TEXT NOT NULL DEFAULT ('process'),
    seq_no            DOUBLE NOT NULL DEFAULT 0,
    vpps              TEXT DEFAULT NULL,
    vpps_desc         TEXT NOT NULL DEFAULT (''),
    vpps_attr         TEXT NOT NULL DEFAULT (''),
    vpps_part         TEXT NOT NULL DEFAULT (''),
    part_feed         TINYINT(1) NOT NULL DEFAULT 0,
    importance        TEXT NOT NULL DEFAULT (''),
    torque_importance TEXT NOT NULL DEFAULT (''),
    vehicle_model     TEXT NOT NULL DEFAULT (''),
    parent_vpps       TEXT NOT NULL DEFAULT (''),
    status            TEXT NOT NULL DEFAULT ('active'),
    sort_order        DOUBLE NOT NULL DEFAULT 0,
    child_vpps        JSON NOT NULL DEFAULT (JSON_ARRAY()),
    meta              JSON NOT NULL DEFAULT (JSON_OBJECT()),
    team_id           TEXT DEFAULT NULL,
    created_by        TEXT DEFAULT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_gbop_entries_version ON workmanship_tpl_gbop_entries (version_gid);
CREATE INDEX idx_gbop_entries_parent  ON workmanship_tpl_gbop_entries (parent_gid);
CREATE INDEX idx_gbop_entries_vpps    ON workmanship_tpl_gbop_entries (vpps(191));

-- GBOP 工艺卡片（L4 总装工艺独立实体）
CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_processes (
    gid               CHAR(36) PRIMARY KEY,
    version_gid       CHAR(36) NOT NULL REFERENCES workmanship_tpl_gbop_versions(gid) ON DELETE CASCADE,
    vpps              TEXT DEFAULT NULL,
    vpps_desc         TEXT NOT NULL DEFAULT (''),
    vpps_part         TEXT NOT NULL DEFAULT (''),
    part_feed         TINYINT(1) NOT NULL DEFAULT 0,
    op_code           TEXT NOT NULL DEFAULT (''),
    op_name           TEXT NOT NULL DEFAULT (''),
    standard_time     DOUBLE DEFAULT NULL,
    description       TEXT NOT NULL DEFAULT (''),
    steps             JSON NOT NULL DEFAULT (JSON_ARRAY()),
    required_tools    JSON NOT NULL DEFAULT (JSON_ARRAY()),
    parameters        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    importance        TEXT NOT NULL DEFAULT (''),
    torque_importance TEXT NOT NULL DEFAULT (''),
    vehicle_model     TEXT NOT NULL DEFAULT (''),
    status            TEXT NOT NULL DEFAULT ('active'),
    meta              JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_by        TEXT DEFAULT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_gbop_processes_version ON workmanship_tpl_gbop_processes (version_gid);
CREATE INDEX idx_gbop_processes_vpps    ON workmanship_tpl_gbop_processes (vpps(191));

-- GBOP 操作卡片（L5 总装操作独立实体）
CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_operations (
    gid               CHAR(36) PRIMARY KEY,
    version_gid       CHAR(36) NOT NULL REFERENCES workmanship_tpl_gbop_versions(gid) ON DELETE CASCADE,
    process_gid       CHAR(36) DEFAULT NULL REFERENCES workmanship_tpl_gbop_processes(gid) ON DELETE SET NULL,
    vpps              TEXT DEFAULT NULL,
    vpps_desc         TEXT NOT NULL DEFAULT (''),
    vpps_part         TEXT NOT NULL DEFAULT (''),
    part_feed         TINYINT(1) NOT NULL DEFAULT 0,
    op_code           TEXT NOT NULL DEFAULT (''),
    op_name           TEXT NOT NULL DEFAULT (''),
    standard_time     DOUBLE DEFAULT NULL,
    description       TEXT NOT NULL DEFAULT (''),
    steps             JSON NOT NULL DEFAULT (JSON_ARRAY()),
    required_tools    JSON NOT NULL DEFAULT (JSON_ARRAY()),
    parameters        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    importance        TEXT NOT NULL DEFAULT (''),
    torque_importance TEXT NOT NULL DEFAULT (''),
    vehicle_model     TEXT NOT NULL DEFAULT (''),
    status            TEXT NOT NULL DEFAULT ('active'),
    meta              JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_by        TEXT DEFAULT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_gbop_operations_version ON workmanship_tpl_gbop_operations (version_gid);
CREATE INDEX idx_gbop_operations_process ON workmanship_tpl_gbop_operations (process_gid);
CREATE INDEX idx_gbop_operations_vpps    ON workmanship_tpl_gbop_operations (vpps(191));

-- GBOP 节点-实体联结表
CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_entry_links (
    gid        CHAR(36) PRIMARY KEY,
    entry_gid  CHAR(36) NOT NULL REFERENCES workmanship_tpl_gbop_entries(gid) ON DELETE CASCADE,
    link_type  TEXT NOT NULL,
    ref_gid    TEXT NOT NULL,
    is_primary TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by TEXT DEFAULT NULL,
    UNIQUE KEY uq_gbop_entry_links (entry_gid, link_type(64), ref_gid(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_gbop_entry_links_entry ON workmanship_tpl_gbop_entry_links (entry_gid);
CREATE INDEX idx_gbop_entry_links_ref   ON workmanship_tpl_gbop_entry_links (ref_gid(191));

-- VPPS 工具模板
CREATE TABLE IF NOT EXISTS workmanship_tpl_vpps_tools (
    gid                TEXT,
    vpps               TEXT DEFAULT NULL,
    name               TEXT NOT NULL DEFAULT (''),
    gun_model          TEXT NOT NULL DEFAULT (''),
    matou_part_no      TEXT NOT NULL DEFAULT (''),
    importance         TEXT NOT NULL DEFAULT (''),
    gun_type           TEXT NOT NULL DEFAULT (''),
    wireless           TEXT NOT NULL DEFAULT (''),
    output_square      TEXT NOT NULL DEFAULT (''),
    torque_min         TEXT NOT NULL DEFAULT (''),
    torque_recommended TEXT NOT NULL DEFAULT (''),
    cad_model_no       TEXT NOT NULL DEFAULT (''),
    socket_model       TEXT NOT NULL DEFAULT (''),
    fastener_type      TEXT NOT NULL DEFAULT (''),
    fastener_params    TEXT NOT NULL DEFAULT (''),
    extension_model    TEXT NOT NULL DEFAULT (''),
    socket_cad_no      TEXT NOT NULL DEFAULT (''),
    extension_cad_no   TEXT NOT NULL DEFAULT (''),
    category           TEXT NOT NULL DEFAULT (''),
    status             TEXT NOT NULL DEFAULT ('active'),
    spec               JSON NOT NULL DEFAULT (JSON_OBJECT()),
    team_id            CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (gid(36))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_vpps_tools_vpps ON workmanship_tpl_vpps_tools (vpps(191));

-- VPPS 设备模板
CREATE TABLE IF NOT EXISTS workmanship_tpl_vpps_equipments (
    gid        TEXT,
    name       TEXT NOT NULL DEFAULT (''),
    category   TEXT NOT NULL DEFAULT (''),
    status     TEXT NOT NULL DEFAULT ('active'),
    spec       JSON NOT NULL DEFAULT (JSON_OBJECT()),
    team_id    CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (gid(36))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- VPPS 工装模板
CREATE TABLE IF NOT EXISTS workmanship_tpl_vpps_fixtures (
    gid        TEXT,
    name       TEXT NOT NULL DEFAULT (''),
    category   TEXT NOT NULL DEFAULT (''),
    status     TEXT NOT NULL DEFAULT ('active'),
    spec       JSON NOT NULL DEFAULT (JSON_OBJECT()),
    team_id    CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (gid(36))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 紧固件规格库
CREATE TABLE IF NOT EXISTS workmanship_tpl_fastener_spec (
    gid             CHAR(36) PRIMARY KEY,
    fastener_type   TEXT NOT NULL DEFAULT (''),
    part_no         TEXT NOT NULL DEFAULT (''),
    name            TEXT NOT NULL DEFAULT (''),
    thread_spec     TEXT NOT NULL DEFAULT (''),
    model           TEXT NOT NULL DEFAULT (''),
    shank_length    TEXT NOT NULL DEFAULT (''),
    guide_type      TEXT NOT NULL DEFAULT (''),
    guide_length    TEXT NOT NULL DEFAULT (''),
    has_adhesive    TEXT NOT NULL DEFAULT (''),
    drive_size      TEXT NOT NULL DEFAULT (''),
    flange_diameter TEXT NOT NULL DEFAULT (''),
    first_vehicle   TEXT NOT NULL DEFAULT (''),
    status          TEXT NOT NULL DEFAULT ('active'),
    meta            JSON NOT NULL DEFAULT (JSON_OBJECT()),
    team_id         CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- VPPS 零件模板
CREATE TABLE IF NOT EXISTS workmanship_tpl_vpps_parts (
    gid                   CHAR(36) PRIMARY KEY,
    vpps_description      TEXT NOT NULL DEFAULT (''),
    part_category         TEXT NOT NULL DEFAULT (''),
    description           TEXT NOT NULL DEFAULT (''),
    level                 TEXT NOT NULL DEFAULT (''),
    vpps_desc_cn          TEXT NOT NULL DEFAULT (''),
    vpps                  TEXT DEFAULT NULL,
    importance            TEXT NOT NULL DEFAULT (''),
    vehicle_model         TEXT NOT NULL DEFAULT (''),
    parent_vpps           TEXT NOT NULL DEFAULT (''),
    status                TEXT NOT NULL DEFAULT ('active'),
    flex_type             TEXT NOT NULL DEFAULT ('待定'),
    ref_main_vpps         TEXT NOT NULL DEFAULT (''),
    ref_main_vpps_desc    TEXT NOT NULL DEFAULT (''),
    ref_install_direction TEXT NOT NULL DEFAULT (''),
    ref_static_clearance  TEXT NOT NULL DEFAULT (''),
    ref_install_clearance TEXT NOT NULL DEFAULT (''),
    meta                  JSON NOT NULL DEFAULT (JSON_OBJECT()),
    team_id               CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_teams(gid) ON DELETE SET NULL,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_vpps_parts_vpps ON workmanship_tpl_vpps_parts (vpps(191));


-- ════════════════════════════════════════════════════════════════════════
-- bop（工艺规划域）
-- ════════════════════════════════════════════════════════════════════════

-- PBOM 版本
CREATE TABLE IF NOT EXISTS workmanship_bop_pbom_versions (
    gid         CHAR(36) PRIMARY KEY,
    project_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE CASCADE,
    version_tag TEXT NOT NULL DEFAULT (''),
    name        TEXT DEFAULT (''),
    source_type TEXT NOT NULL DEFAULT ('manual'),
    status      TEXT NOT NULL DEFAULT ('draft'),
    meta        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bom_snapshots_project ON workmanship_bop_pbom_versions (project_gid);

-- PBOM 零件表（合并所有扩展列）
CREATE TABLE IF NOT EXISTS workmanship_bop_pbom (
    gid                      CHAR(36) PRIMARY KEY,
    snapshot_gid             CHAR(36) NOT NULL REFERENCES workmanship_bop_pbom_versions(gid) ON DELETE CASCADE,
    part_no                  TEXT NOT NULL DEFAULT (''),
    title                    TEXT NOT NULL DEFAULT (''),
    quantity                 DOUBLE NOT NULL DEFAULT 1,
    unit                     TEXT NOT NULL DEFAULT ('pcs'),
    material                 TEXT DEFAULT NULL,
    parent_gid               CHAR(36) DEFAULT NULL,
    vpps                     TEXT DEFAULT NULL,
    vpps_desc                TEXT DEFAULT (''),
    parent_vpps              TEXT DEFAULT (''),
    parent_vpps_name         TEXT DEFAULT (''),
    bom_row                  TEXT DEFAULT (''),
    bom_row_label            TEXT DEFAULT (''),
    component_id             TEXT DEFAULT (''),
    component_type           TEXT DEFAULT (''),
    component_version_status TEXT DEFAULT (''),
    purchase_status          TEXT DEFAULT (''),
    variable_formula         TEXT DEFAULT (''),
    torque                   TEXT DEFAULT (''),
    torque_importance        TEXT DEFAULT (''),
    ownership_user           TEXT DEFAULT (''),
    level                    INT DEFAULT NULL,
    home                     TEXT DEFAULT (''),
    configuration            TEXT DEFAULT (''),
    parent_bom_row           TEXT DEFAULT (''),
    catia_occurrence_name    TEXT DEFAULT (''),
    catia_file_name          TEXT DEFAULT (''),
    catia_uuid               TEXT DEFAULT (''),
    default_matrix           TEXT DEFAULT (''),
    abs_matrix               TEXT DEFAULT (''),
    rel_matrix               TEXT DEFAULT (''),
    local_bbox               TEXT DEFAULT (''),
    ecn                      TEXT DEFAULT (''),
    fna                      TEXT DEFAULT (''),
    geo_main_part            TEXT DEFAULT (''),
    ref_main_vpps_desc       TEXT DEFAULT (''),
    ref_main_vpps            TEXT DEFAULT (''),
    main_part_consistency    TEXT DEFAULT (''),
    geo_evidence             TEXT DEFAULT (''),
    lr_side                  TEXT DEFAULT (''),
    vpps_source              TEXT NOT NULL DEFAULT ('auto'),
    vpps_reported_at         DATETIME(6) DEFAULT NULL,
    remark                   TEXT DEFAULT (''),
    temp_vpps                TEXT DEFAULT NULL,
    is_deleted               TINYINT(1) NOT NULL DEFAULT 0,
    meta                     JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at               DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_part_entries_snapshot ON workmanship_bop_pbom (snapshot_gid);
CREATE INDEX idx_part_entries_vpps     ON workmanship_bop_pbom (vpps(191));

-- CAD 模型实例
CREATE TABLE IF NOT EXISTS workmanship_bop_cad_model_instances (
    gid             CHAR(36) PRIMARY KEY,
    part_entry_gid  CHAR(36) NOT NULL REFERENCES workmanship_bop_pbom(gid) ON DELETE CASCADE,
    model_file_path TEXT NOT NULL DEFAULT (''),
    transform       JSON NOT NULL DEFAULT (JSON_OBJECT()),
    meta            JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- BOP 版本（合并 schema.sql + bop_schema_v2.sql 所有字段）
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_versions (
    gid               CHAR(36) PRIMARY KEY,
    project_gid       CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE CASCADE,
    factory_gid       CHAR(36) DEFAULT NULL REFERENCES workmanship_factory_factories(gid) ON DELETE SET NULL,
    vehicle_model_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_vehicle_models(gid) ON DELETE SET NULL,
    version_tag       TEXT NOT NULL DEFAULT (''),
    version_no        TEXT DEFAULT NULL,
    base_version_gid  CHAR(36) DEFAULT NULL,
    parent_version_gid CHAR(36) DEFAULT NULL,
    change_note       TEXT DEFAULT NULL,
    maturity          TEXT NOT NULL DEFAULT ('concept'),
    takt_time         DOUBLE NOT NULL DEFAULT 60,
    status            TEXT NOT NULL DEFAULT ('active'),
    description       TEXT DEFAULT NULL,
    created_by        TEXT DEFAULT NULL,
    meta              JSON NOT NULL DEFAULT (JSON_OBJECT()),
    -- 版本族
    version_family_gid CHAR(36) DEFAULT NULL,
    bop_name          TEXT NOT NULL DEFAULT (''),
    -- 归属/关联
    owner_gid         CHAR(36) DEFAULT NULL,
    pbom_version_gid  CHAR(36) DEFAULT NULL,
    -- 时间戳
    frozen_at         DATETIME(6) DEFAULT NULL,
    archived_at       DATETIME(6) DEFAULT NULL,
    published_at      DATETIME(6) DEFAULT NULL,
    -- 生命周期
    lifecycle_phase   TEXT NOT NULL DEFAULT ('init'),
    lifecycle_state   JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted        TINYINT(1) NOT NULL DEFAULT 0,
    is_archived       TINYINT(1) NOT NULL DEFAULT 0,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at        DATETIME(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_versions_project ON workmanship_bop_bop_versions (project_gid);
CREATE INDEX idx_bop_versions_factory ON workmanship_bop_bop_versions (factory_gid);
CREATE INDEX idx_bop_versions_family  ON workmanship_bop_bop_versions (version_family_gid);
CREATE INDEX idx_bop_ver_parent       ON workmanship_bop_bop_versions (parent_version_gid);

-- BOP 条目骨架树（合并所有字段）
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_entries (
    gid                   CHAR(36) PRIMARY KEY,
    version_gid           CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    sort_order            DOUBLE NOT NULL DEFAULT 0,
    level                 INT DEFAULT NULL,
    ai00_level            SMALLINT DEFAULT NULL,
    node_type             TEXT NOT NULL,
    title                 TEXT DEFAULT NULL,
    vpps                  TEXT DEFAULT NULL,
    vpps_desc             TEXT DEFAULT NULL,
    vpps_part             TEXT NOT NULL DEFAULT (''),
    part_feed             TINYINT(1) NOT NULL DEFAULT 0,
    catia_occurrence_name TEXT NOT NULL DEFAULT (''),
    parent_vpps_name      TEXT NOT NULL DEFAULT (''),
    parent_gid            CHAR(36) DEFAULT NULL REFERENCES workmanship_bop_bop_entries(gid) ON DELETE SET NULL,
    parent_bop_title      TEXT DEFAULT NULL,
    parent_bop_label      TEXT DEFAULT NULL,
    source_entry_gid      CHAR(36) DEFAULT NULL,
    owner_gid             CHAR(36) DEFAULT NULL,
    process_flow_pic      JSON DEFAULT NULL,
    process_chart_pic     JSON DEFAULT NULL,
    child_vpps            JSON NOT NULL DEFAULT (JSON_ARRAY()),
    bom_row_owner         TEXT DEFAULT NULL,
    is_deleted            TINYINT(1) NOT NULL DEFAULT 0,
    is_archived           TINYINT(1) NOT NULL DEFAULT 0,
    assignee_user_gid     CHAR(36) DEFAULT NULL,
    scheduled_date        DATE DEFAULT NULL,
    meta                  JSON NOT NULL DEFAULT (JSON_OBJECT()),
    deleted_at            DATETIME(6) DEFAULT NULL,
    archived_at           DATETIME(6) DEFAULT NULL,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by            TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_ent_version       ON workmanship_bop_bop_entries (version_gid);
CREATE INDEX idx_bop_ent_parent        ON workmanship_bop_bop_entries (parent_gid);
CREATE INDEX idx_bop_ent_version_level ON workmanship_bop_bop_entries (version_gid, level);
CREATE INDEX idx_bop_ent_version_type  ON workmanship_bop_bop_entries (version_gid, node_type(64));
CREATE INDEX idx_bop_ent_vpps          ON workmanship_bop_bop_entries (vpps(191));
CREATE INDEX idx_bop_entries_source    ON workmanship_bop_bop_entries (source_entry_gid);

-- BOP 条目关联（含 snapshot_data）
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_entry_links (
    gid             CHAR(36) PRIMARY KEY,
    entry_gid       CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_entries(gid) ON DELETE CASCADE,
    link_type       TEXT NOT NULL,
    entity_gid      TEXT DEFAULT NULL,
    is_primary      TINYINT(1) NOT NULL DEFAULT 0,
    is_inherited    TINYINT(1) NOT NULL DEFAULT 0,
    gbop_source_gid CHAR(36) DEFAULT NULL,
    snapshot_data   JSON DEFAULT NULL,
    version_gid     CHAR(36) DEFAULT NULL,
    is_deleted      TINYINT(1) NOT NULL DEFAULT 0,
    is_archived     TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at      DATETIME(6) DEFAULT NULL,
    archived_at     DATETIME(6) DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by      TEXT DEFAULT NULL,
    UNIQUE KEY uq_bop_entry_links (entry_gid, link_type(64), entity_gid(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_links_entry   ON workmanship_bop_bop_entry_links (entry_gid);
CREATE INDEX idx_bop_links_entity  ON workmanship_bop_bop_entry_links (entity_gid(191), link_type(64));
CREATE INDEX idx_bop_links_type    ON workmanship_bop_bop_entry_links (link_type(64));
CREATE INDEX idx_bop_links_primary ON workmanship_bop_bop_entry_links (entry_gid, is_primary);
CREATE INDEX idx_bop_links_version ON workmanship_bop_bop_entry_links (version_gid);

-- 线体工艺详情
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_line (
    gid             CHAR(36) PRIMARY KEY,
    project_gid     CHAR(36) NOT NULL,
    title           TEXT NOT NULL,
    version_no      TEXT NOT NULL DEFAULT ('01'),
    vpps            TEXT DEFAULT NULL,
    owner_gid       CHAR(36) DEFAULT NULL,
    ext             JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted      TINYINT(1) NOT NULL DEFAULT 0,
    is_archived     TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at      DATETIME(6) DEFAULT NULL,
    archived_at     DATETIME(6) DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by      TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_asm_line_proc_proj ON workmanship_bop_bop_line (project_gid);
CREATE INDEX idx_asm_line_proc_vpps ON workmanship_bop_bop_line (vpps(191));

-- 工位工艺详情
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_station (
    gid         CHAR(36) PRIMARY KEY,
    project_gid CHAR(36) NOT NULL,
    title       TEXT NOT NULL,
    version_no  TEXT NOT NULL DEFAULT ('01'),
    vpps        TEXT DEFAULT NULL,
    owner_gid   CHAR(36) DEFAULT NULL,
    ext         JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted  TINYINT(1) NOT NULL DEFAULT 0,
    is_archived TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at  DATETIME(6) DEFAULT NULL,
    archived_at DATETIME(6) DEFAULT NULL,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by  TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_asm_station_proc_proj ON workmanship_bop_bop_station (project_gid);
CREATE INDEX idx_asm_sta_proc_vpps     ON workmanship_bop_bop_station (vpps(191));

-- 工序实体
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_process (
    gid             CHAR(36) PRIMARY KEY,
    project_gid     CHAR(36) NOT NULL,
    bop_version_gid CHAR(36) NOT NULL,
    name            TEXT NOT NULL,
    process_code    TEXT DEFAULT NULL,
    standard_time   DECIMAL(10,2) DEFAULT NULL,
    version_no      TEXT NOT NULL DEFAULT ('01'),
    vpps            TEXT DEFAULT NULL,
    vpps_desc       TEXT DEFAULT NULL,
    vpps_part       TEXT NOT NULL DEFAULT (''),
    part_feed       TINYINT(1) NOT NULL DEFAULT 0,
    params          JSON NOT NULL DEFAULT (JSON_OBJECT()),
    source_type     TEXT DEFAULT NULL,
    source_ref_gid  CHAR(36) DEFAULT NULL,
    ext             JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted      TINYINT(1) NOT NULL DEFAULT 0,
    is_archived     TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at      DATETIME(6) DEFAULT NULL,
    archived_at     DATETIME(6) DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by      TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_process_proj    ON workmanship_bop_bop_process (project_gid);
CREATE INDEX idx_bop_process_version ON workmanship_bop_bop_process (bop_version_gid);

-- 工序详情（bop_steps）
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_steps (
    gid               CHAR(36) PRIMARY KEY,
    project_gid       CHAR(36) NOT NULL,
    title             TEXT NOT NULL,
    operation_code    TEXT DEFAULT NULL,
    version_no        TEXT NOT NULL DEFAULT ('01'),
    station_height    DECIMAL(7,2) DEFAULT NULL,
    op_req_height     DECIMAL(7,2) DEFAULT NULL,
    vpps              TEXT DEFAULT NULL,
    vpps_desc         TEXT DEFAULT NULL,
    vpps_part         TEXT NOT NULL DEFAULT (''),
    part_feed         TINYINT(1) NOT NULL DEFAULT 0,
    params            JSON NOT NULL DEFAULT (JSON_OBJECT()),
    source_type       TEXT DEFAULT NULL,
    source_ref_gid    CHAR(36) DEFAULT NULL,
    -- 降级字段
    vd_time           DOUBLE DEFAULT NULL,
    total_time        DOUBLE DEFAULT NULL,
    floor_height_need INT DEFAULT NULL,
    process_flow_pic  JSON DEFAULT NULL,
    process_chart_pic JSON DEFAULT NULL,
    ext               JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted        TINYINT(1) NOT NULL DEFAULT 0,
    is_archived       TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at        DATETIME(6) DEFAULT NULL,
    archived_at       DATETIME(6) DEFAULT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by        TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_asm_op_proj   ON workmanship_bop_bop_steps (project_gid);
CREATE INDEX idx_asm_op_code   ON workmanship_bop_bop_steps (operation_code(191));
CREATE INDEX idx_asm_op_source ON workmanship_bop_bop_steps (source_ref_gid);

-- 工步详情
CREATE TABLE IF NOT EXISTS workmanship_bop_asm_steps (
    gid            CHAR(36) PRIMARY KEY,
    project_gid    CHAR(36) NOT NULL,
    name           TEXT NOT NULL,
    step_code      TEXT DEFAULT NULL,
    version_no     TEXT NOT NULL DEFAULT ('01'),
    vpps           TEXT DEFAULT NULL,
    source_type    TEXT DEFAULT NULL,
    source_ref_gid CHAR(36) DEFAULT NULL,
    created_at     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by     TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_asm_step_proj   ON workmanship_bop_asm_steps (project_gid);
CREATE INDEX idx_asm_step_source ON workmanship_bop_asm_steps (source_ref_gid);
CREATE INDEX idx_asm_step_vpps   ON workmanship_bop_asm_steps (vpps(191));

-- 项目设备需求
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_equipments (
    gid                   CHAR(36) PRIMARY KEY,
    project_gid           CHAR(36) NOT NULL,
    title                 TEXT NOT NULL,
    version_no            TEXT NOT NULL DEFAULT ('01'),
    factory_equip_ref_gid CHAR(36) DEFAULT NULL,
    spec                  TEXT DEFAULT NULL,
    quantity              INT NOT NULL DEFAULT 1,
    status                TEXT NOT NULL DEFAULT ('pending'),
    owner_gid             CHAR(36) DEFAULT NULL,
    vpps                  TEXT DEFAULT NULL,
    ext                   JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted            TINYINT(1) NOT NULL DEFAULT 0,
    is_archived           TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at            DATETIME(6) DEFAULT NULL,
    archived_at           DATETIME(6) DEFAULT NULL,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by            TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_equip_proj ON workmanship_bop_bop_equipments (project_gid);
CREATE INDEX idx_proj_equip_vpps ON workmanship_bop_bop_equipments (vpps(191));

-- 项目工装需求
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_fixtures (
    gid                     CHAR(36) PRIMARY KEY,
    project_gid             CHAR(36) NOT NULL,
    title                   TEXT NOT NULL,
    version_no              TEXT NOT NULL DEFAULT ('01'),
    factory_tooling_ref_gid CHAR(36) DEFAULT NULL,
    spec                    TEXT DEFAULT NULL,
    quantity                INT NOT NULL DEFAULT 1,
    status                  TEXT NOT NULL DEFAULT ('pending'),
    owner_gid               CHAR(36) DEFAULT NULL,
    vpps                    TEXT DEFAULT NULL,
    ext                     JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted              TINYINT(1) NOT NULL DEFAULT 0,
    is_archived             TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at              DATETIME(6) DEFAULT NULL,
    archived_at             DATETIME(6) DEFAULT NULL,
    created_at              DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at              DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by              TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_tooling_proj ON workmanship_bop_bop_fixtures (project_gid);
CREATE INDEX idx_proj_tooling_vpps ON workmanship_bop_bop_fixtures (vpps(191));

-- 项目工具需求
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_tools (
    gid                  CHAR(36) PRIMARY KEY,
    project_gid          CHAR(36) NOT NULL,
    title                TEXT NOT NULL,
    version_no           TEXT NOT NULL DEFAULT ('01'),
    factory_tool_ref_gid CHAR(36) DEFAULT NULL,
    spec                 TEXT DEFAULT NULL,
    quantity             INT NOT NULL DEFAULT 1,
    status               TEXT NOT NULL DEFAULT ('pending'),
    owner_gid            CHAR(36) DEFAULT NULL,
    vpps                 TEXT DEFAULT NULL,
    ext                  JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted           TINYINT(1) NOT NULL DEFAULT 0,
    is_archived          TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at           DATETIME(6) DEFAULT NULL,
    archived_at          DATETIME(6) DEFAULT NULL,
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by           TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_tools_proj ON workmanship_bop_bop_tools (project_gid);
CREATE INDEX idx_proj_tools_vpps ON workmanship_bop_bop_tools (vpps(191));

-- 项目岗位需求
CREATE TABLE IF NOT EXISTS workmanship_bop_project_roles (
    gid                  CHAR(36) PRIMARY KEY,
    project_gid          CHAR(36) NOT NULL,
    name                 TEXT NOT NULL,
    version_no           TEXT NOT NULL DEFAULT ('01'),
    factory_role_ref_gid CHAR(36) DEFAULT NULL,
    role_type            TEXT DEFAULT NULL,
    headcount            INT NOT NULL DEFAULT 1,
    owner_gid            CHAR(36) DEFAULT NULL,
    vpps                 TEXT DEFAULT NULL,
    ext                  JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by           TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_roles_proj ON workmanship_bop_project_roles (project_gid);
CREATE INDEX idx_proj_roles_vpps ON workmanship_bop_project_roles (vpps(191));

-- 岗位工艺详情
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_operator (
    gid             CHAR(36) PRIMARY KEY,
    project_gid     CHAR(36) NOT NULL,
    title           TEXT NOT NULL,
    version_no      TEXT NOT NULL DEFAULT ('01'),
    operator_code   TEXT DEFAULT NULL,
    headcount       INT NOT NULL DEFAULT 1,
    owner_gid       CHAR(36) DEFAULT NULL,
    vpps            TEXT DEFAULT NULL,
    ext             JSON NOT NULL DEFAULT (JSON_OBJECT()),
    is_deleted      TINYINT(1) NOT NULL DEFAULT 0,
    is_archived     TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at      DATETIME(6) DEFAULT NULL,
    archived_at     DATETIME(6) DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by      TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_asm_op_proc_proj ON workmanship_bop_bop_operator (project_gid);
CREATE INDEX idx_asm_op_proc_vpps ON workmanship_bop_bop_operator (vpps(191));

-- 人机姿态
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_jack_pos (
    gid             CHAR(36) PRIMARY KEY,
    project_gid     CHAR(36) NOT NULL,
    title           TEXT NOT NULL,
    version_no      TEXT NOT NULL DEFAULT ('01'),
    jack_pos_type   TEXT DEFAULT NULL,
    ergonomic_score INT DEFAULT NULL,
    posture_desc    TEXT DEFAULT NULL,
    image_ref       JSON NOT NULL DEFAULT (JSON_OBJECT()),
    params          JSON NOT NULL DEFAULT (JSON_OBJECT()),
    status          TEXT NOT NULL DEFAULT ('draft'),
    owner_gid       CHAR(36) DEFAULT NULL,
    vpps            TEXT DEFAULT NULL,
    is_deleted      TINYINT(1) NOT NULL DEFAULT 0,
    is_archived     TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at      DATETIME(6) DEFAULT NULL,
    archived_at     DATETIME(6) DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by      TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_jack_pos_proj ON workmanship_bop_bop_jack_pos (project_gid);
CREATE INDEX idx_proj_jack_pos_vpps ON workmanship_bop_bop_jack_pos (vpps(191));

-- 地面高度（现有）
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_floor_height (
    gid             CHAR(36) PRIMARY KEY,
    project_gid     CHAR(36) NOT NULL,
    title           TEXT NOT NULL DEFAULT (''),
    height_mm       INT NOT NULL DEFAULT 0,
    measured_at     DATETIME(6) DEFAULT NULL,
    measured_by     TEXT DEFAULT NULL,
    station_ref_gid CHAR(36) DEFAULT NULL,
    notes           TEXT DEFAULT NULL,
    status          TEXT NOT NULL DEFAULT ('active'),
    owner_gid       CHAR(36) DEFAULT NULL,
    vpps            TEXT DEFAULT NULL,
    is_deleted      TINYINT(1) NOT NULL DEFAULT 0,
    is_archived     TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at      DATETIME(6) DEFAULT NULL,
    archived_at     DATETIME(6) DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by      TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_floor_h_proj ON workmanship_bop_bop_floor_height (project_gid);
CREATE INDEX idx_proj_floor_h_vpps ON workmanship_bop_bop_floor_height (vpps(191));

-- 控制计划
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_control_plan (
    gid              CHAR(36) PRIMARY KEY,
    project_gid      CHAR(36) NOT NULL,
    title            TEXT NOT NULL DEFAULT (''),
    display_id       TEXT NOT NULL DEFAULT (''),
    version_no       TEXT NOT NULL DEFAULT ('01'),
    status           TEXT NOT NULL DEFAULT ('draft'),
    content_ref      JSON NOT NULL DEFAULT (JSON_OBJECT()),
    applicable_scope JSON NOT NULL DEFAULT (JSON_OBJECT()),
    owner_gid        CHAR(36) DEFAULT NULL,
    attachments      JSON NOT NULL DEFAULT (JSON_ARRAY()),
    vpps             TEXT DEFAULT NULL,
    is_deleted       TINYINT(1) NOT NULL DEFAULT 0,
    is_archived      TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at       DATETIME(6) DEFAULT NULL,
    archived_at      DATETIME(6) DEFAULT NULL,
    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by       TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_ctrl_plan_proj ON workmanship_bop_bop_control_plan (project_gid);
CREATE INDEX idx_proj_ctrl_plan_vpps ON workmanship_bop_bop_control_plan (vpps(191));

-- 工艺卡
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_process_charts (
    gid         CHAR(36) PRIMARY KEY,
    project_gid CHAR(36) NOT NULL,
    title       TEXT NOT NULL DEFAULT (''),
    display_id  TEXT NOT NULL DEFAULT (''),
    version_no  TEXT NOT NULL DEFAULT ('01'),
    status      TEXT NOT NULL DEFAULT ('draft'),
    chart_type  TEXT DEFAULT NULL,
    content_ref JSON NOT NULL DEFAULT (JSON_OBJECT()),
    owner_gid   CHAR(36) DEFAULT NULL,
    attachments JSON NOT NULL DEFAULT (JSON_ARRAY()),
    vpps        TEXT DEFAULT NULL,
    is_deleted  TINYINT(1) NOT NULL DEFAULT 0,
    is_archived TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at  DATETIME(6) DEFAULT NULL,
    archived_at DATETIME(6) DEFAULT NULL,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    created_by  TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_proj_proc_chart_proj ON workmanship_bop_bop_process_charts (project_gid);
CREATE INDEX idx_proj_proc_chart_vpps ON workmanship_bop_bop_process_charts (vpps(191));

-- 画布多项目叠加配置
CREATE TABLE IF NOT EXISTS workmanship_bop_canvas_bop_layers (
    gid             CHAR(36) PRIMARY KEY,
    canvas_gid      CHAR(36) NOT NULL,
    bop_version_gid CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    project_gid     CHAR(36) NOT NULL,
    layer_color     TEXT DEFAULT NULL,
    display_order   INT NOT NULL DEFAULT 0,
    is_base         TINYINT(1) NOT NULL DEFAULT 0,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_canvas_bop_layers (canvas_gid, bop_version_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_canvas_layers_canvas  ON workmanship_bop_canvas_bop_layers (canvas_gid);
CREATE INDEX idx_canvas_layers_version ON workmanship_bop_canvas_bop_layers (bop_version_gid);

-- BOP Fork 预设
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_fork_presets (
    gid                CHAR(36) PRIMARY KEY,
    name               TEXT NOT NULL,
    description        TEXT DEFAULT NULL,
    include_node_types JSON DEFAULT NULL,
    field_rules        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    meta_key_rules     JSON NOT NULL DEFAULT (JSON_OBJECT()),
    team_gid           CHAR(36) DEFAULT NULL,
    created_by         TEXT DEFAULT NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_fork_presets_team ON workmanship_bop_bop_fork_presets (team_gid);

-- BOP 暂存箱
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_staging (
    gid                CHAR(36) PRIMARY KEY,
    bop_version_gid    CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    node_type          TEXT NOT NULL DEFAULT ('process'),
    title              TEXT NOT NULL DEFAULT (''),
    vpps               TEXT DEFAULT NULL,
    source_type        TEXT DEFAULT NULL,
    source_ref_gid     CHAR(36) DEFAULT NULL,
    original_entry_gid CHAR(36) DEFAULT NULL,
    child_count        INT NOT NULL DEFAULT 0,
    meta               JSON NOT NULL DEFAULT (JSON_OBJECT()),
    sort_order         DOUBLE NOT NULL DEFAULT 0,
    is_deleted         TINYINT(1) NOT NULL DEFAULT 0,
    is_archived        TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at         DATETIME(6) DEFAULT NULL,
    archived_at        DATETIME(6) DEFAULT NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_by         TEXT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_staging_version ON workmanship_bop_bop_staging (bop_version_gid);

-- BOP 生命周期阶段历史表
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_lifecycle_history (
    gid              CHAR(36) PRIMARY KEY,
    version_gid      CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    phase            TEXT NOT NULL,
    entered_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    confirmed_at     DATETIME(6) DEFAULT NULL,
    confirmed_by_gid TEXT DEFAULT NULL,
    confirmed_by_name TEXT DEFAULT NULL,
    note             TEXT DEFAULT NULL,
    UNIQUE KEY uq_bop_lc_history (version_gid, phase(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_lc_history_ver ON workmanship_bop_bop_lifecycle_history (version_gid);

-- BOP 完善度指标表
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_lifecycle_stats (
    gid                 CHAR(36) PRIMARY KEY,
    version_gid         CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    line_gid            CHAR(36) DEFAULT NULL,
    stats_snapshot_date DATE NOT NULL DEFAULT (CURRENT_DATE),
    nok_vpps            INT NOT NULL DEFAULT 0,
    nok_unbound_parts   INT NOT NULL DEFAULT 0,
    nok_unbound_ops     INT NOT NULL DEFAULT 0,
    tools_bound         INT NOT NULL DEFAULT 0,
    tools_total         INT NOT NULL DEFAULT 0,
    fixtures_bound      INT NOT NULL DEFAULT 0,
    fixtures_total      INT NOT NULL DEFAULT 0,
    equipment_bound     INT NOT NULL DEFAULT 0,
    equipment_total     INT NOT NULL DEFAULT 0,
    coverage_ok         TINYINT(1) NOT NULL DEFAULT 0,
    balance_ok          TINYINT(1) NOT NULL DEFAULT 0,
    tasks_done          INT NOT NULL DEFAULT 0,
    tasks_total         INT NOT NULL DEFAULT 0,
    issues_open         INT NOT NULL DEFAULT 0,
    rules_warn          INT NOT NULL DEFAULT 0,
    rules_block         INT NOT NULL DEFAULT 0,
    refreshed_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- MySQL 无法直接用 COALESCE 创建唯一索引，用普通唯一索引替代
CREATE UNIQUE INDEX idx_bop_lc_stats_unique ON workmanship_bop_bop_lifecycle_stats (version_gid, line_gid, stats_snapshot_date);
CREATE INDEX idx_bop_lc_stats_ver           ON workmanship_bop_bop_lifecycle_stats (version_gid);
CREATE INDEX idx_bop_lc_stats_date          ON workmanship_bop_bop_lifecycle_stats (stats_snapshot_date);

-- BOP 线体快照（Checkpoint）表
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_line_checkpoints (
    gid             CHAR(36) PRIMARY KEY,
    version_gid     CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    line_gid        CHAR(36) NOT NULL,
    label           TEXT DEFAULT NULL,
    created_by      TEXT DEFAULT NULL,
    created_by_name TEXT DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    snapshot        JSON NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_ckpt_ver_line ON workmanship_bop_bop_line_checkpoints (version_gid, line_gid, created_at);

-- BOP 线体操作日志表
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_line_operation_log (
    gid               CHAR(36) PRIMARY KEY,
    version_gid       CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    line_gid          CHAR(36) NOT NULL,
    batch_id          TEXT NOT NULL,
    op_type           TEXT NOT NULL,
    entity_gid        CHAR(36) DEFAULT NULL,
    entity_title      TEXT DEFAULT NULL,
    old_state         JSON DEFAULT NULL,
    new_state         JSON DEFAULT NULL,
    op_seq            INT NOT NULL DEFAULT 0,
    performed_by      TEXT DEFAULT NULL,
    performed_by_name TEXT DEFAULT NULL,
    performed_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    rolled_back       TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_oplog_ver_line ON workmanship_bop_bop_line_operation_log (version_gid, line_gid, performed_at);
CREATE INDEX idx_bop_oplog_batch    ON workmanship_bop_bop_line_operation_log (batch_id(191));

-- BOP 版本族群级元数据表
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_version_families (
    gid                CHAR(36) PRIMARY KEY,
    bop_name           TEXT NOT NULL DEFAULT (''),
    lifecycle_phase    TEXT NOT NULL DEFAULT ('init'),
    active_version_gid CHAR(36) DEFAULT NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bop_families_active ON workmanship_bop_bop_version_families (active_version_gid);

-- PBOM 差异工作队列
CREATE TABLE IF NOT EXISTS workmanship_bop_bop_pbom_diff_queue (
    gid             CHAR(36) PRIMARY KEY,
    family_gid      CHAR(36) NOT NULL,
    bop_version_gid CHAR(36) NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
    pbom_base_gid   CHAR(36) DEFAULT NULL,
    pbom_target_gid CHAR(36) NOT NULL,
    pbom_part_gid   CHAR(36) NOT NULL,
    diff_type       TEXT NOT NULL,
    vpps            TEXT DEFAULT NULL,
    vpps_desc       TEXT DEFAULT NULL,
    status          TEXT NOT NULL DEFAULT ('pending'),
    note            TEXT DEFAULT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_pbom_diff_ver    ON workmanship_bop_bop_pbom_diff_queue (bop_version_gid, status(32));
CREATE INDEX idx_pbom_diff_family ON workmanship_bop_bop_pbom_diff_queue (family_gid);


-- ════════════════════════════════════════════════════════════════════════
-- work（工作流域）
-- ════════════════════════════════════════════════════════════════════════

-- 关注表
CREATE TABLE IF NOT EXISTS workmanship_work_follows (
    gid        CHAR(36) PRIMARY KEY,
    user_gid   CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
    item_type  TEXT NOT NULL,
    item_gid   TEXT NOT NULL,
    item_title TEXT NOT NULL DEFAULT (''),
    notify_on  TEXT NOT NULL DEFAULT ('key_changes'),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_follows (user_gid, item_type(32), item_gid(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_follows_user ON workmanship_work_follows (user_gid);
CREATE INDEX idx_follows_item ON workmanship_work_follows (item_type(32), item_gid(191));

-- 通知表
CREATE TABLE IF NOT EXISTS workmanship_work_notifications (
    gid        CHAR(36) PRIMARY KEY,
    user_gid   CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    item_type  TEXT DEFAULT NULL,
    item_gid   TEXT DEFAULT NULL,
    title      TEXT NOT NULL DEFAULT (''),
    body       TEXT NOT NULL DEFAULT (''),
    is_read    TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_notif_user_unread ON workmanship_work_notifications (user_gid, is_read);

-- 清单表
CREATE TABLE IF NOT EXISTS workmanship_work_lists (
    gid           CHAR(36) PRIMARY KEY,
    name          TEXT NOT NULL,
    color         TEXT NOT NULL DEFAULT ('#5b8dee'),
    storage_scope TEXT NOT NULL DEFAULT ('cloud'),
    owner_type    TEXT NOT NULL DEFAULT ('user'),
    owner_gid     TEXT NOT NULL DEFAULT (''),
    creator_gid   TEXT NOT NULL DEFAULT (''),
    item_type     TEXT NOT NULL DEFAULT ('task'),
    sort_order    INT NOT NULL DEFAULT 0,
    visibility    TEXT NOT NULL DEFAULT ('team'),
    project_gid   CHAR(36) DEFAULT NULL,
    read_scope    TEXT DEFAULT NULL,
    write_scope   TEXT DEFAULT NULL,
    deleted_at    DATETIME(6) DEFAULT NULL,
    created_at    DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_lists_owner     ON workmanship_work_lists (owner_type(16), owner_gid(191));
CREATE INDEX idx_lists_item_type ON workmanship_work_lists (item_type(32));

-- 任务表（work schema 旧版，保留兼容）
CREATE TABLE IF NOT EXISTS workmanship_work_tasks (
    gid               CHAR(36) PRIMARY KEY,
    display_id        TEXT NOT NULL DEFAULT (''),
    title             TEXT NOT NULL DEFAULT (''),
    description       TEXT NOT NULL DEFAULT (''),
    owner_gid         TEXT NOT NULL DEFAULT (''),
    owner_user_gid    CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    assignee_team_gid CHAR(36) DEFAULT NULL,
    project_gid       CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE SET NULL,
    status            TEXT NOT NULL DEFAULT ('pending'),
    priority          TEXT NOT NULL DEFAULT ('normal'),
    source_ref        JSON NOT NULL DEFAULT (JSON_OBJECT()),
    review_date       TEXT DEFAULT NULL,
    meeting_level     TEXT NOT NULL DEFAULT ('none'),
    meeting_doc_link  TEXT DEFAULT NULL,
    progress_logs     JSON NOT NULL DEFAULT (JSON_ARRAY()),
    due_date          TEXT DEFAULT NULL,
    plan_start        TEXT DEFAULT NULL,
    plan_end          TEXT DEFAULT NULL,
    actual_start      TEXT DEFAULT NULL,
    actual_end        TEXT DEFAULT NULL,
    share_scope       TEXT NOT NULL DEFAULT ('project'),
    list_gid          CHAR(36) DEFAULT NULL REFERENCES workmanship_work_lists(gid) ON DELETE SET NULL,
    attachments       JSON NOT NULL DEFAULT (JSON_ARRAY()),
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_tasks_owner   ON workmanship_work_tasks (owner_user_gid);
CREATE INDEX idx_tasks_project ON workmanship_work_tasks (project_gid);
CREATE INDEX idx_tasks_status  ON workmanship_work_tasks (status(32));

-- 问题表（work schema 旧版，保留兼容）
CREATE TABLE IF NOT EXISTS workmanship_work_issues (
    gid                   CHAR(36) PRIMARY KEY,
    display_id            TEXT NOT NULL DEFAULT (''),
    title                 TEXT NOT NULL DEFAULT (''),
    description           TEXT NOT NULL DEFAULT (''),
    severity              TEXT NOT NULL DEFAULT ('low'),
    status                TEXT NOT NULL DEFAULT ('open'),
    owner_gid             TEXT NOT NULL DEFAULT (''),
    owner_user_gid        CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    assignee_team_gid     CHAR(36) DEFAULT NULL,
    project_gid           CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE SET NULL,
    tracking_refs         JSON NOT NULL DEFAULT (JSON_ARRAY()),
    occurrence_root_cause TEXT DEFAULT NULL,
    escape_root_cause     TEXT DEFAULT NULL,
    interim_action        TEXT DEFAULT NULL,
    permanent_action      TEXT DEFAULT NULL,
    source_ref            JSON NOT NULL DEFAULT (JSON_OBJECT()),
    related_task_gid      CHAR(36) DEFAULT NULL,
    related_knowledge_gid CHAR(36) DEFAULT NULL,
    approval_order_gid    CHAR(36) DEFAULT NULL,
    bop_entry_gid         CHAR(36) DEFAULT NULL,
    share_scope           TEXT NOT NULL DEFAULT ('project'),
    list_gid              CHAR(36) DEFAULT NULL REFERENCES workmanship_work_lists(gid) ON DELETE SET NULL,
    attachments           JSON NOT NULL DEFAULT (JSON_ARRAY()),
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_issues_owner   ON workmanship_work_issues (owner_user_gid);
CREATE INDEX idx_issues_project ON workmanship_work_issues (project_gid);
CREATE INDEX idx_issues_status  ON workmanship_work_issues (status(32));

-- 任务模板
CREATE TABLE IF NOT EXISTS workmanship_work_task_templates (
    gid         CHAR(36) PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT (''),
    scope       TEXT NOT NULL DEFAULT ('system'),
    owner_gid   CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    version     INT NOT NULL DEFAULT 1,
    is_active   TINYINT(1) NOT NULL DEFAULT 1,
    entries     JSON DEFAULT (JSON_ARRAY()),
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 任务模板条目
CREATE TABLE IF NOT EXISTS workmanship_work_task_template_items (
    gid             CHAR(36) PRIMARY KEY,
    template_gid    CHAR(36) NOT NULL REFERENCES workmanship_work_task_templates(gid) ON DELETE CASCADE,
    title_pattern   TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT (''),
    priority        TEXT NOT NULL DEFAULT ('normal'),
    assignee_role   TEXT DEFAULT NULL,
    due_offset_days INT DEFAULT NULL,
    share_scope     TEXT NOT NULL DEFAULT ('team'),
    sort_order      INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_tti_template ON workmanship_work_task_template_items (template_gid);

-- 条目沟通历史表
CREATE TABLE IF NOT EXISTS workmanship_work_item_entries (
    gid           CHAR(36) PRIMARY KEY,
    id            TEXT NOT NULL,
    item_type     TEXT NOT NULL,
    item_gid      TEXT NOT NULL,
    parent_id     TEXT DEFAULT NULL,
    section       TEXT NOT NULL DEFAULT ('detail'),
    author        TEXT NOT NULL DEFAULT ('human'),
    author_name   TEXT DEFAULT (''),
    author_gid    TEXT DEFAULT (''),
    content       TEXT DEFAULT (''),
    resolved      TINYINT(1) NOT NULL DEFAULT 0,
    sort_order    DOUBLE NOT NULL DEFAULT 0,
    read_by_human TINYINT(1) NOT NULL DEFAULT 1,
    ai_status     TEXT DEFAULT ('unread'),
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_item_entries_item   ON workmanship_work_item_entries (item_type(32), item_gid(191));
CREATE INDEX idx_item_entries_parent ON workmanship_work_item_entries (parent_id(191));


-- ════════════════════════════════════════════════════════════════════════
-- knowledge（知识库域）
-- ════════════════════════════════════════════════════════════════════════

-- 知识条目（合并两个文件的所有字段）
CREATE TABLE IF NOT EXISTS workmanship_know_entries (
    gid                    CHAR(36) PRIMARY KEY,
    display_id             TEXT NOT NULL DEFAULT (''),
    title                  TEXT NOT NULL DEFAULT (''),
    entry_type             TEXT NOT NULL DEFAULT ('guide'),
    status                 TEXT NOT NULL DEFAULT ('draft'),
    share_scope            TEXT NOT NULL DEFAULT ('team'),
    list_gid               CHAR(36) DEFAULT NULL,
    source_gid             CHAR(36) DEFAULT NULL,
    source_label           TEXT NOT NULL DEFAULT (''),
    maintainer_gid         CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    contributors           JSON NOT NULL DEFAULT (JSON_ARRAY()),
    attachments            JSON NOT NULL DEFAULT (JSON_ARRAY()),
    tags                   JSON NOT NULL DEFAULT (JSON_ARRAY()),
    content_ref            JSON NOT NULL DEFAULT (JSON_OBJECT()),
    content_md             TEXT NOT NULL DEFAULT (''),
    related_part_nos       JSON NOT NULL DEFAULT (JSON_ARRAY()),
    related_operation_gids JSON NOT NULL DEFAULT (JSON_ARRAY()),
    creator_gid            CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    source_project_gid     CHAR(36) DEFAULT NULL REFERENCES workmanship_proj_projects(gid) ON DELETE SET NULL,
    scheduled_date         DATE DEFAULT NULL,
    -- 本体绑定
    onto_class_gid         CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE SET NULL,
    onto_property_gid      CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_properties(gid) ON DELETE SET NULL,
    created_at             DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at             DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_knowledge_entries_list   ON workmanship_know_entries (list_gid);
CREATE INDEX idx_knowledge_entries_type   ON workmanship_know_entries (entry_type(32));
CREATE INDEX idx_knowledge_entries_status ON workmanship_know_entries (status(32));
CREATE INDEX idx_knowledge_project        ON workmanship_know_entries (source_project_gid);
CREATE INDEX idx_knowledge_scope          ON workmanship_know_entries (share_scope(32));
CREATE INDEX idx_know_onto_class          ON workmanship_know_entries (onto_class_gid);

-- 规则条目（合并所有字段）
CREATE TABLE IF NOT EXISTS workmanship_know_craft_rules (
    gid                  CHAR(36) PRIMARY KEY,
    display_id           TEXT NOT NULL DEFAULT (''),
    code                 TEXT NOT NULL DEFAULT (''),
    name                 TEXT NOT NULL DEFAULT (''),
    rule_type            TEXT NOT NULL DEFAULT ('other'),
    enforcement_level    TEXT NOT NULL DEFAULT ('advisory'),
    rule_definition      JSON NOT NULL DEFAULT (JSON_OBJECT()),
    applicable_scope     JSON NOT NULL DEFAULT (JSON_OBJECT()),
    status               TEXT NOT NULL DEFAULT ('draft'),
    knowledge_source_gid CHAR(36) DEFAULT NULL,
    share_scope          TEXT NOT NULL DEFAULT ('team'),
    list_gid             CHAR(36) DEFAULT NULL,
    attachments          JSON NOT NULL DEFAULT (JSON_ARRAY()),
    scheduled_date       DATE DEFAULT NULL,
    owner_user_gid       CHAR(36) DEFAULT NULL,
    -- 本体 CEL 表达式
    expression           TEXT DEFAULT NULL,
    context_class_gid    CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE SET NULL,
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_craft_rules_status ON workmanship_know_craft_rules (status(32));
CREATE INDEX idx_craft_rules_scope  ON workmanship_know_craft_rules (share_scope(32));
CREATE INDEX idx_craft_rules_list   ON workmanship_know_craft_rules (list_gid);
CREATE INDEX idx_craft_rules_class  ON workmanship_know_craft_rules (context_class_gid);

-- 知识库文件夹
CREATE TABLE IF NOT EXISTS workmanship_know_folders (
    gid        CHAR(36) PRIMARY KEY,
    parent_gid CHAR(36) DEFAULT NULL,
    scope_type TEXT NOT NULL DEFAULT ('personal'),
    team_gid   CHAR(36) DEFAULT NULL,
    name       TEXT NOT NULL DEFAULT (''),
    sort_order INT NOT NULL DEFAULT 0,
    creator_gid TEXT DEFAULT (''),
    created_at  DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_kfolders_scope ON workmanship_know_folders (scope_type(32), team_gid);

-- 知识条目（文件）
CREATE TABLE IF NOT EXISTS workmanship_know_items (
    gid          CHAR(36) PRIMARY KEY,
    folder_gid   CHAR(36) DEFAULT NULL,
    scope_type   TEXT NOT NULL DEFAULT ('personal'),
    team_gid     CHAR(36) DEFAULT NULL,
    item_type    TEXT NOT NULL DEFAULT ('richtext'),
    title        TEXT NOT NULL DEFAULT (''),
    status       TEXT NOT NULL DEFAULT ('draft'),
    content_body JSON DEFAULT NULL,
    content_md   TEXT DEFAULT (''),
    file_path    TEXT DEFAULT (''),
    url          TEXT DEFAULT (''),
    site_ref     JSON DEFAULT NULL,
    tags         JSON DEFAULT (JSON_ARRAY()),
    is_system    TINYINT(1) NOT NULL DEFAULT 0,
    is_pinned    TINYINT(1) NOT NULL DEFAULT 0,
    is_hidden    TINYINT(1) NOT NULL DEFAULT 0,
    creator_gid  TEXT DEFAULT (''),
    created_at   DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at   DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_kitems_folder ON workmanship_know_items (folder_gid);
CREATE INDEX idx_kitems_scope  ON workmanship_know_items (scope_type(32));

-- 系统内置条目 seed（幂等）
INSERT IGNORE INTO workmanship_know_items (
    gid, folder_gid, scope_type, team_gid, item_type, title, status,
    site_ref, is_system, creator_gid, created_at, updated_at
) VALUES (
    'system-project-info',
    NULL, 'public', NULL, 'site_page', '项目信息', 'published',
    '{"path": "knowledge_hub/pages/project_info.html", "label": "项目信息"}',
    1, 'system', NOW(6), NOW(6)
);

-- 知识收藏
CREATE TABLE IF NOT EXISTS workmanship_know_favorites (
    user_gid   TEXT NOT NULL,
    item_gid   CHAR(36) NOT NULL,
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_gid(191), item_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 最近访问
CREATE TABLE IF NOT EXISTS workmanship_know_recent (
    user_gid    TEXT NOT NULL,
    item_gid    CHAR(36) NOT NULL,
    accessed_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_gid(191), item_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ════════════════════════════════════════════════════════════════════════
-- 本体编辑器（onto_* 系列，属于 knowledge 域但用 workmanship_onto_ 前缀）
-- ════════════════════════════════════════════════════════════════════════

-- 本体类
CREATE TABLE IF NOT EXISTS workmanship_onto_classes (
    gid                  CHAR(36) PRIMARY KEY,
    name                 TEXT NOT NULL DEFAULT (''),
    label_zh             TEXT NOT NULL DEFAULT (''),
    label_en             TEXT NOT NULL DEFAULT (''),
    parent_gid           CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE SET NULL,
    node_type_binding    TEXT DEFAULT NULL,
    is_abstract          TINYINT(1) NOT NULL DEFAULT 0,
    color                TEXT DEFAULT NULL,
    icon                 TEXT DEFAULT NULL,
    description          TEXT NOT NULL DEFAULT (''),
    sort_order           INT NOT NULL DEFAULT 0,
    abbr                 TEXT DEFAULT NULL,
    ai00_level           INT DEFAULT NULL,
    display_layer        TEXT DEFAULT NULL,
    stats_priority       INT DEFAULT 99,
    is_hidden_in_layout  TINYINT(1) NOT NULL DEFAULT 0,
    suggested_child_type TEXT DEFAULT NULL,
    entity_table         TEXT DEFAULT NULL,
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_onto_classes_parent       ON workmanship_onto_classes (parent_gid);
CREATE INDEX idx_onto_classes_binding      ON workmanship_onto_classes (node_type_binding(64));
CREATE INDEX idx_onto_classes_entity_table ON workmanship_onto_classes (entity_table(128));
CREATE INDEX idx_onto_classes_node_type    ON workmanship_onto_classes (node_type_binding(64));

-- 本体属性
CREATE TABLE IF NOT EXISTS workmanship_onto_properties (
    gid                   CHAR(36) PRIMARY KEY,
    class_gid             CHAR(36) NOT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE CASCADE,
    name                  TEXT NOT NULL,
    label_zh              TEXT NOT NULL DEFAULT (''),
    prop_kind             TEXT NOT NULL DEFAULT ('data'),
    data_type             TEXT DEFAULT NULL,
    range_class_gid       CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE SET NULL,
    enum_values           JSON NOT NULL DEFAULT (JSON_ARRAY()),
    required              TINYINT(1) NOT NULL DEFAULT 0,
    min_val               DOUBLE DEFAULT NULL,
    max_val               DOUBLE DEFAULT NULL,
    description           TEXT NOT NULL DEFAULT (''),
    sort_order            INT NOT NULL DEFAULT 0,
    storage_hint          TEXT NOT NULL DEFAULT ('meta'),
    field_widget          TEXT NOT NULL DEFAULT ('text'),
    field_config          JSON NOT NULL DEFAULT (JSON_OBJECT()),
    show_in_create_dialog TINYINT(1) NOT NULL DEFAULT 1,
    dialog_order          INT NOT NULL DEFAULT 99,
    show_in_detail        TINYINT(1) NOT NULL DEFAULT 1,
    detail_order          INT NOT NULL DEFAULT 99,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_onto_props_class ON workmanship_onto_properties (class_gid);

-- 本体关系
CREATE TABLE IF NOT EXISTS workmanship_onto_relations (
    gid               CHAR(36) PRIMARY KEY,
    name              TEXT NOT NULL,
    label_zh          TEXT NOT NULL DEFAULT (''),
    domain_class_gid  CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE CASCADE,
    range_class_gid   CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE SET NULL,
    is_functional     TINYINT(1) NOT NULL DEFAULT 0,
    inverse_of_gid    CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_relations(gid) ON DELETE SET NULL,
    description       TEXT NOT NULL DEFAULT (''),
    link_type_binding TEXT DEFAULT NULL,
    deep_copy_on_fork TINYINT(1) NOT NULL DEFAULT 0,
    shared_on_fork    TINYINT(1) NOT NULL DEFAULT 0,
    skip_on_fork      TINYINT(1) NOT NULL DEFAULT 0,
    snapshot_on_freeze TINYINT(1) NOT NULL DEFAULT 0,
    sort_order        INT NOT NULL DEFAULT 0,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 本体公理
CREATE TABLE IF NOT EXISTS workmanship_onto_axioms (
    gid          CHAR(36) PRIMARY KEY,
    class_gid    CHAR(36) NOT NULL REFERENCES workmanship_onto_classes(gid) ON DELETE CASCADE,
    axiom_type   TEXT NOT NULL,
    target_gid   CHAR(36) DEFAULT NULL,
    expression   TEXT DEFAULT NULL,
    description  TEXT NOT NULL DEFAULT (''),
    property_gid CHAR(36) DEFAULT NULL,
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ════════════════════════════════════════════════════════════════════════
-- app（应用层）
-- ════════════════════════════════════════════════════════════════════════

-- 用户视图配置
CREATE TABLE IF NOT EXISTS workmanship_app_view_configs (
    gid        CHAR(36) PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT ('未命名视图'),
    module     TEXT NOT NULL DEFAULT (''),
    list_gid   CHAR(36) DEFAULT NULL,
    owner_gid  TEXT NOT NULL DEFAULT (''),
    is_shared  TINYINT(1) NOT NULL DEFAULT 0,
    config     JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_view_configs_owner    ON workmanship_app_view_configs (owner_gid(191));
CREATE INDEX idx_view_configs_module   ON workmanship_app_view_configs (module(64));
CREATE INDEX idx_view_configs_list_gid ON workmanship_app_view_configs (list_gid);

-- 导出模板配置
CREATE TABLE IF NOT EXISTS workmanship_app_export_templates (
    gid        CHAR(36) PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT (''),
    module     TEXT NOT NULL DEFAULT (''),
    owner_gid  CHAR(36) DEFAULT NULL REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
    is_shared  TINYINT(1) NOT NULL DEFAULT 0,
    config     JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_export_templates_module ON workmanship_app_export_templates (module(64));
CREATE INDEX idx_export_templates_owner  ON workmanship_app_export_templates (owner_gid);

-- 多工作台配置
CREATE TABLE IF NOT EXISTS workmanship_app_workbench_configs (
    gid        CHAR(36) PRIMARY KEY,
    owner_type TEXT NOT NULL DEFAULT ('user'),
    owner_gid  TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT ('工作台'),
    sort_order INT NOT NULL DEFAULT 0,
    widgets    JSON NOT NULL DEFAULT (JSON_ARRAY()),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_wb_configs_owner ON workmanship_app_workbench_configs (owner_type(16), owner_gid(191));

-- 工作台成员个性化覆盖
CREATE TABLE IF NOT EXISTS workmanship_app_workbench_member_overrides (
    gid           CHAR(36) PRIMARY KEY,
    workbench_gid CHAR(36) NOT NULL REFERENCES workmanship_app_workbench_configs(gid) ON DELETE CASCADE,
    user_gid      CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
    widgets       JSON NOT NULL DEFAULT (JSON_ARRAY()),
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_wb_overrides (workbench_gid, user_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_wb_overrides_wb   ON workmanship_app_workbench_member_overrides (workbench_gid);
CREATE INDEX idx_wb_overrides_user ON workmanship_app_workbench_member_overrides (user_gid);

-- 流程引擎
CREATE TABLE IF NOT EXISTS workmanship_app_flows (
    gid         CHAR(36) PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT (''),
    flowdef     TEXT NOT NULL DEFAULT (''),
    status      TEXT NOT NULL DEFAULT ('draft'),
    last_run_at DATETIME(6) DEFAULT NULL,
    deleted_at  DATETIME(6) DEFAULT NULL,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_flows_status ON workmanship_app_flows (status(32));

-- 流程运行记录
CREATE TABLE IF NOT EXISTS workmanship_app_flow_runs (
    gid             CHAR(36) PRIMARY KEY,
    flow_gid        CHAR(36) NOT NULL REFERENCES workmanship_app_flows(gid) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT ('pending'),
    mode            TEXT NOT NULL DEFAULT ('auto'),
    current_node_id TEXT DEFAULT NULL,
    context_data    JSON NOT NULL DEFAULT (JSON_OBJECT()),
    error_msg       TEXT DEFAULT NULL,
    started_at      DATETIME(6) DEFAULT NULL,
    completed_at    DATETIME(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_flow_runs_flow ON workmanship_app_flow_runs (flow_gid);

-- 工作台标注数据
CREATE TABLE IF NOT EXISTS workmanship_app_wb_annotations (
    `key`      VARCHAR(500) PRIMARY KEY,
    data       TEXT NOT NULL DEFAULT ('{}'),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 开发看板归档
CREATE TABLE IF NOT EXISTS workmanship_app_bug_tracker_snapshots (
    id           VARCHAR(64) PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT (''),
    type         TEXT NOT NULL DEFAULT ('bug'),
    priority     TEXT NOT NULL DEFAULT ('P1-高'),
    status       TEXT NOT NULL DEFAULT ('待处理'),
    ai_status    TEXT NOT NULL DEFAULT ('待处理'),
    user_confirm TEXT NOT NULL DEFAULT ('待确认'),
    module       TEXT NOT NULL DEFAULT (''),
    ui_id        TEXT NOT NULL DEFAULT (''),
    page         TEXT NOT NULL DEFAULT (''),
    files        TEXT NOT NULL DEFAULT (''),
    seq          INT DEFAULT NULL,
    detail       TEXT NOT NULL DEFAULT (''),
    comment      TEXT NOT NULL DEFAULT (''),
    ai_question  TEXT NOT NULL DEFAULT (''),
    commit       TEXT NOT NULL DEFAULT (''),
    links        JSON NOT NULL DEFAULT (JSON_ARRAY()),
    history      TEXT NOT NULL DEFAULT (''),
    entries      JSON NOT NULL DEFAULT (JSON_ARRAY()),
    created_at   DATETIME(6) DEFAULT NULL,
    updated_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    synced_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- AI 工具调用审计日志
CREATE TABLE IF NOT EXISTS workmanship_app_ai_audit_logs (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    gid           TEXT NOT NULL,
    session_gid   TEXT NOT NULL,
    user_gid      TEXT DEFAULT (''),
    tool_name     TEXT NOT NULL,
    is_write      TINYINT(1) DEFAULT 0,
    is_confirmed  TINYINT(1) DEFAULT 0,
    inputs_json   TEXT DEFAULT ('{}'),
    result_json   TEXT DEFAULT ('{}'),
    resource_gid  TEXT DEFAULT (''),
    resource_type TEXT DEFAULT (''),
    status        TEXT DEFAULT ('ok'),
    created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_ai_audit_gid (gid(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ai_audit_logs_session ON workmanship_app_ai_audit_logs (session_gid(191));
CREATE INDEX idx_ai_audit_logs_user    ON workmanship_app_ai_audit_logs (user_gid(191));
CREATE INDEX idx_ai_audit_logs_created ON workmanship_app_ai_audit_logs (created_at DESC);

-- Skill 库
CREATE TABLE IF NOT EXISTS workmanship_app_skills (
    gid         CHAR(36) PRIMARY KEY,
    name        TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT (''),
    skill_type  TEXT NOT NULL,
    scope       TEXT NOT NULL DEFAULT ('private'),
    status      TEXT NOT NULL DEFAULT ('draft'),
    owner_gid   TEXT NOT NULL DEFAULT (''),
    is_system   TINYINT(1) NOT NULL DEFAULT 0,
    content     JSON NOT NULL DEFAULT (JSON_OBJECT()),
    icon        TEXT NOT NULL DEFAULT (''),
    tags        JSON NOT NULL DEFAULT (JSON_ARRAY()),
    sort_order  INT NOT NULL DEFAULT 0,
    is_pinned   TINYINT(1) NOT NULL DEFAULT 0,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at  DATETIME(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 注：MySQL 中 WHERE deleted_at IS NULL 的部分唯一索引需改为普通唯一索引
CREATE UNIQUE INDEX idx_skills_name  ON workmanship_app_skills (name(191));
CREATE INDEX idx_skills_owner        ON workmanship_app_skills (owner_gid(191));
CREATE INDEX idx_skills_scope        ON workmanship_app_skills (scope(32), status(32));


-- ════════════════════════════════════════════════════════════════════════
-- integration（外部数据源集成域）
-- ════════════════════════════════════════════════════════════════════════

-- 外部数据源
CREATE TABLE IF NOT EXISTS workmanship_int_ext_datasources (
    gid            CHAR(36) PRIMARY KEY,
    name           TEXT NOT NULL,
    db_type        TEXT NOT NULL,
    host           TEXT NOT NULL,
    port           INT NOT NULL,
    `database`     TEXT NOT NULL,
    username       TEXT NOT NULL,
    password_enc   TEXT NOT NULL DEFAULT (''),
    status         TEXT NOT NULL DEFAULT ('untested'),
    last_tested_at DATETIME(6) DEFAULT NULL,
    last_error     TEXT DEFAULT NULL,
    created_by     TEXT DEFAULT NULL,
    created_at     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 外部数据源映射
CREATE TABLE IF NOT EXISTS workmanship_int_ext_mappings (
    gid               CHAR(36) PRIMARY KEY,
    datasource_gid    CHAR(36) NOT NULL REFERENCES workmanship_int_ext_datasources(gid) ON DELETE CASCADE,
    ext_table         TEXT NOT NULL,
    onto_class_gid    CHAR(36) NOT NULL REFERENCES workmanship_onto_classes(gid),
    filter_sql        TEXT DEFAULT NULL,
    unique_key_col    TEXT DEFAULT NULL,
    last_import_at    DATETIME(6) DEFAULT NULL,
    last_import_count INT DEFAULT NULL,
    created_by        TEXT DEFAULT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ext_mappings_ds ON workmanship_int_ext_mappings (datasource_gid);

-- 外部字段映射
CREATE TABLE IF NOT EXISTS workmanship_int_ext_field_mappings (
    gid               CHAR(36) PRIMARY KEY,
    mapping_gid       CHAR(36) NOT NULL REFERENCES workmanship_int_ext_mappings(gid) ON DELETE CASCADE,
    ext_column        TEXT NOT NULL,
    target_type       TEXT NOT NULL DEFAULT ('property'),
    onto_property_gid CHAR(36) DEFAULT NULL REFERENCES workmanship_onto_properties(gid),
    bop_field         TEXT DEFAULT NULL,
    transform_expr    TEXT DEFAULT NULL,
    is_ignored        TINYINT(1) NOT NULL DEFAULT 0,
    sort_order        INT NOT NULL DEFAULT 0,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ext_field_mappings_m ON workmanship_int_ext_field_mappings (mapping_gid);


-- ════════════════════════════════════════════════════════════════════════
-- display_id_counters（替代 PostgreSQL SEQUENCE，统一计数器表）
-- ════════════════════════════════════════════════════════════════════════
-- 用法：SELECT val FROM workmanship_display_id_counters WHERE seq_name='tasks_display_seq' FOR UPDATE;
--       UPDATE workmanship_display_id_counters SET val=val+1 WHERE seq_name='tasks_display_seq';

CREATE TABLE IF NOT EXISTS workmanship_display_id_counters (
    seq_name VARCHAR(64) PRIMARY KEY,
    val      BIGINT NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 初始化所有序列
INSERT IGNORE INTO workmanship_display_id_counters (seq_name, val) VALUES
    ('tasks_display_seq',      1),
    ('issues_display_seq',     1),
    ('rules_display_seq',      1),
    ('knowledge_display_seq',  1),
    ('proj_tasks_display_seq', 1),
    ('proj_issues_display_seq',1);


SET FOREIGN_KEY_CHECKS = 1;

-- ════════════════════════════════════════════════════════════════════════
-- 说明
-- 1. gid 列均使用 CHAR(36)，适配 UUID v4 或雪花算法转 hex 格式。
-- 2. JSONB 已全部转为 JSON；JSON DEFAULT 使用 MySQL 8.0 表达式默认值语法。
-- 3. PostgreSQL SEQUENCE 由 workmanship_display_id_counters 表替代。
-- 4. 所有 WHERE 子句的条件索引（partial index）已去掉 WHERE，改为普通索引。
-- 5. bop_entry_links 的 version_gid 索引已删除（该列不存在于表结构中）。
-- 6. 数据迁移 UPDATE 语句（status 值迁移等）不包含在本文件中，新库直接建表。
-- 7. pgvector 相关内容已跳过（MySQL 使用向量搜索需要 MySQL 9.x 或插件）。
-- ════════════════════════════════════════════════════════════════════════
