"""
backend/db/migrate.py
──────────────────────
MySQL 启动时幂等迁移（替代 PostgreSQL DO $$ 块和 _ensure_* 函数）。

对于 mysql_schema.sql 涵盖的主表，此文件只做：
  1. 确保 display_id_counters 初始化
  2. 创建 schema.sql 未包含的辅助表（bitable_bindings 等）
  3. 为旧数据库补列（新增字段）

run_safe_migrations() 在 backend/main.py lifespan 中调用一次。
"""
import logging

_log = logging.getLogger("backend.db.migrate")


def run_safe_migrations(conn) -> None:
    """幂等执行所有安全迁移，MySQL 8.0 语法。"""
    _run_ddl_batch(conn, _COUNTER_INITS, "counters")
    _run_ddl_batch(conn, _BITABLE_TABLES, "bitable_tables")
    _run_ddl_batch(conn, _COLUMN_PATCHES, "column_patches")
    _run_ddl_batch(conn, _SEED_DATA, "seed_data")


def _run_ddl_batch(conn, stmts: list, label: str) -> None:
    for stmt in stmts:
        try:
            with conn.cursor() as cur:
                cur.execute(stmt)
            conn.commit()
        except Exception as e:
            conn.rollback()
            code = e.args[0] if e.args else 0
            if code not in (1060, 1061, 1050):  # 忽略列/索引/表已存在
                _log.debug("migrate[%s] stmt skip: %s | %s", label, stmt[:60], e)


# ─────────────────────────────────────────────────────────────────────────────
# 1. display_id 计数器初始化
# ─────────────────────────────────────────────────────────────────────────────

_COUNTER_INITS = [
    """
    CREATE TABLE IF NOT EXISTS workmanship_display_id_counters (
        seq_name VARCHAR(64) PRIMARY KEY,
        next_val BIGINT NOT NULL DEFAULT 1
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "INSERT IGNORE INTO workmanship_display_id_counters VALUES ('knowledge_display_seq', 1)",
    "INSERT IGNORE INTO workmanship_display_id_counters VALUES ('rules_display_seq', 1)",
    "INSERT IGNORE INTO workmanship_display_id_counters VALUES ('proj_tasks_display_seq', 1)",
    "INSERT IGNORE INTO workmanship_display_id_counters VALUES ('proj_issues_display_seq', 1)",
    "INSERT IGNORE INTO workmanship_display_id_counters VALUES ('work_tasks_display_seq', 1)",
    "INSERT IGNORE INTO workmanship_display_id_counters VALUES ('work_issues_display_seq', 1)",
    "INSERT IGNORE INTO workmanship_display_id_counters VALUES ('std_op_display_seq', 1)",
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. 运行时动态建表（原 _ensure_* 函数创建，不在 mysql_schema.sql 中）
# ─────────────────────────────────────────────────────────────────────────────

_BITABLE_TABLES = [
    # ── 飞书多维表格同步 ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_list_bitable_bindings (
        list_gid           CHAR(36) PRIMARY KEY,
        app_token          TEXT NOT NULL,
        table_id           TEXT NOT NULL,
        field_mapping      JSON NOT NULL DEFAULT (JSON_OBJECT()),
        sync_enabled       TINYINT(1) NOT NULL DEFAULT 1,
        webhook_secret     TEXT,
        has_remote_updates TINYINT(1) NOT NULL DEFAULT 0,
        last_push_at       DATETIME(6),
        last_pull_at       DATETIME(6),
        created_by         TEXT NOT NULL,
        created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        is_deleted         TINYINT(1) NOT NULL DEFAULT 0,
        deleted_at         DATETIME(6)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_list_bitable_record_map (
        list_gid          CHAR(36) NOT NULL,
        item_gid          CHAR(36) NOT NULL,
        record_id         TEXT NOT NULL,
        ai00_updated_at   DATETIME(6),
        feishu_updated_at DATETIME(6),
        is_deleted        TINYINT(1) NOT NULL DEFAULT 0,
        deleted_at        DATETIME(6),
        PRIMARY KEY (list_gid, item_gid)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bitable_record_map_record
        ON workmanship_work_list_bitable_record_map (list_gid, record_id(191))
    """,
    """
    CREATE TABLE IF NOT EXISTS workmanship_bop_gbop_nav_bindings (
        gid                    CHAR(36) PRIMARY KEY,
        pbom_version_gid       CHAR(36) NOT NULL,
        gbop_process_entry_gid CHAR(36),
        gbop_op_entry_gid      CHAR(36) NOT NULL,
        pbom_entry_gid         CHAR(36) NOT NULL,
        is_part_feed           TINYINT(1) NOT NULL DEFAULT 0,
        created_at             DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        UNIQUE KEY uq_gbop_nav (pbom_version_gid, gbop_op_entry_gid, pbom_entry_gid)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    # ── 权限授权表（_ensure_permission_tables）───────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_auth_permission_grants (
        gid         CHAR(36) PRIMARY KEY,
        grantee_gid CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
        grant_type  TEXT NOT NULL,
        scope_gid   CHAR(36),
        granted_by  CHAR(36) REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
        granted_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        expires_at  DATETIME(6),
        note        TEXT NOT NULL DEFAULT (''),
        UNIQUE KEY uq_grants (grantee_gid, grant_type(64), scope_gid(36))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_grants_grantee    ON workmanship_auth_permission_grants (grantee_gid)",
    "CREATE INDEX IF NOT EXISTS idx_grants_type_scope ON workmanship_auth_permission_grants (grant_type(64), scope_gid(36))",
    # ── 清单共享表（_ensure_share_tables）────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_list_shares (
        gid        CHAR(36) PRIMARY KEY,
        list_gid   CHAR(36) NOT NULL REFERENCES workmanship_work_lists(gid) ON DELETE CASCADE,
        shared_to  CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
        permission TEXT NOT NULL DEFAULT ('read'),
        shared_by  TEXT NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        UNIQUE KEY uq_list_share (list_gid, shared_to)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_item_shares (
        gid        CHAR(36) PRIMARY KEY,
        item_type  TEXT NOT NULL,
        item_gid   CHAR(36) NOT NULL,
        shared_to  CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
        permission TEXT NOT NULL DEFAULT ('read'),
        shared_by  TEXT NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        UNIQUE KEY uq_item_share (item_type(64), item_gid, shared_to)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    # ── 分享链接 + 权限申请（_ensure_deep_link_tables）───────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_share_links (
        token        VARCHAR(128) PRIMARY KEY,
        target_type  TEXT NOT NULL,
        target_gid   CHAR(36) NOT NULL,
        item_type    TEXT DEFAULT NULL,
        display_name TEXT NOT NULL DEFAULT (''),
        created_by   CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
        created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        expires_at   DATETIME(6) DEFAULT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_permission_requests (
        gid             CHAR(36) PRIMARY KEY,
        requester_gid   CHAR(36) NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
        target_type     TEXT NOT NULL,
        target_gid      CHAR(36) NOT NULL,
        want_permission TEXT NOT NULL DEFAULT ('read'),
        status          TEXT NOT NULL DEFAULT ('pending'),
        message         TEXT DEFAULT (''),
        responded_by    CHAR(36) REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
        responded_at    DATETIME(6),
        created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    # ── 条目变更日志（_ensure_change_log_tables）─────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_item_change_logs (
        gid        CHAR(36) PRIMARY KEY,
        item_type  TEXT NOT NULL,
        item_gid   CHAR(36) NOT NULL,
        list_gid   CHAR(36) DEFAULT NULL,
        changed_by TEXT NOT NULL,
        changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        field_name TEXT NOT NULL,
        old_value  TEXT,
        new_value  TEXT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_change_logs_item ON workmanship_work_item_change_logs (item_type(64), item_gid)",
    "CREATE INDEX IF NOT EXISTS idx_change_logs_list ON workmanship_work_item_change_logs (list_gid)",
    # ── AI 记忆（_ensure_ai_memory_table）────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_app_ai_memory (
        gid        CHAR(36) PRIMARY KEY,
        user_gid   TEXT NOT NULL DEFAULT (''),
        memory_key TEXT NOT NULL DEFAULT (''),
        content    TEXT NOT NULL DEFAULT (''),
        tag        TEXT NOT NULL DEFAULT ('preference'),
        scope      TEXT NOT NULL DEFAULT ('user'),
        confidence DOUBLE NOT NULL DEFAULT 1.0,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
        UNIQUE KEY uq_ai_memory (user_gid(191), memory_key(191))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_ai_memory_user ON workmanship_app_ai_memory (user_gid(191), tag(64))",
    # ── VPPS 操作审计（_ensure_vpps_operations_table）────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_bop_vpps_operations (
        gid              CHAR(36) PRIMARY KEY,
        pbom_version_gid CHAR(36) NOT NULL,
        pbom_row_gid     CHAR(36) NOT NULL,
        operation_type   TEXT NOT NULL,
        rule_no          INTEGER,
        field_name       TEXT,
        original_value   TEXT,
        new_value        TEXT,
        actor_gid        CHAR(36) NOT NULL,
        actor_name       TEXT,
        created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        notes            TEXT,
        is_active        TINYINT(1) NOT NULL DEFAULT 1,
        reverted_at      DATETIME(6),
        reverted_by_gid  CHAR(36),
        reverted_by_name TEXT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_vpps_ops_version ON workmanship_bop_vpps_operations (pbom_version_gid)",
    "CREATE INDEX IF NOT EXISTS idx_vpps_ops_row     ON workmanship_bop_vpps_operations (pbom_row_gid)",
    # ── 飞书搜索缓存（feishu_cache_service）──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_app_feishu_search_cache (
        user_gid    CHAR(36)    NOT NULL,
        entity_type VARCHAR(64) NOT NULL,
        entity_id   VARCHAR(255) NOT NULL,
        name        TEXT        NOT NULL DEFAULT (''),
        search_ext  TEXT        NOT NULL DEFAULT (''),
        data        JSON        NOT NULL DEFAULT (JSON_OBJECT()),
        updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (user_gid, entity_type, entity_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_feishu_cache_name    ON workmanship_app_feishu_search_cache (user_gid, entity_type, name(191))",
    "CREATE INDEX IF NOT EXISTS idx_feishu_cache_updated ON workmanship_app_feishu_search_cache (user_gid, entity_type, updated_at)",
    # ── 画布表（canvases.py _ensure_table）──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_app_wfc_canvases (
        gid        CHAR(36) PRIMARY KEY,
        owner_gid  TEXT NOT NULL DEFAULT (''),
        title      TEXT NOT NULL DEFAULT ('未命名画布'),
        data       JSON NOT NULL DEFAULT (JSON_OBJECT()),
        is_shared  TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_wfc_canvases_owner ON workmanship_app_wfc_canvases (owner_gid(191))",
    # ── GBOP 匹配暂存（_bop/gbop.py _ensure_gbop_tables）────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_bop_gbop_match_staging (
        gid                CHAR(36) PRIMARY KEY,
        pbom_version_gid   CHAR(36) NOT NULL,
        gbop_entry_gid     CHAR(36),
        pbom_entry_gid     CHAR(36) NOT NULL,
        bop_version_gid    CHAR(36),
        match_status       TEXT NOT NULL DEFAULT ('pending'),
        extra_entry_gids   JSON NOT NULL DEFAULT (JSON_ARRAY()),
        created_entry_gid  CHAR(36),
        confirmed_by       TEXT,
        confirmed_at       DATETIME(6),
        created_by         TEXT,
        created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        UNIQUE KEY uq_gbop_staging (pbom_version_gid, pbom_entry_gid)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_gbop_staging_pbom_ver ON workmanship_bop_gbop_match_staging (pbom_version_gid)",
    # ── AI 会话和对话（app.ai_sessions / app.ai_turns）─────────────────────────
    """
    CREATE TABLE IF NOT EXISTS workmanship_app_ai_sessions (
        gid        CHAR(36) PRIMARY KEY,
        user_gid   TEXT NOT NULL DEFAULT (''),
        title      TEXT NOT NULL DEFAULT ('新对话'),
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS workmanship_app_ai_turns (
        gid        CHAR(36) PRIMARY KEY,
        session_gid CHAR(36) NOT NULL,
        role       TEXT NOT NULL,
        content    TEXT NOT NULL DEFAULT (''),
        tool_calls JSON NOT NULL DEFAULT (JSON_ARRAY()),
        sort_order DOUBLE NOT NULL DEFAULT 0,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_ai_turns_session ON workmanship_app_ai_turns (session_gid)",
    # ── work.task_dependencies（旧 work schema，独立于 proj.task_dependencies）──
    """
    CREATE TABLE IF NOT EXISTS workmanship_work_task_dependencies (
        gid           CHAR(36) PRIMARY KEY,
        source_gid    CHAR(36) NOT NULL,
        target_gid    CHAR(36) NOT NULL,
        edge_type     TEXT NOT NULL DEFAULT ('prerequisite'),
        dep_condition TEXT NOT NULL DEFAULT ('done'),
        dep_group     TEXT DEFAULT NULL,
        label         TEXT NOT NULL DEFAULT (''),
        created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX IF NOT EXISTS idx_work_task_deps_src ON workmanship_work_task_dependencies (source_gid)",
    "CREATE INDEX IF NOT EXISTS idx_work_task_deps_tgt ON workmanship_work_task_dependencies (target_gid)",
]

# ─────────────────────────────────────────────────────────────────────────────
# 3. 新增列补丁（用于已有数据库升级，新库 mysql_schema.sql 已包含这些列）
# ─────────────────────────────────────────────────────────────────────────────

_COLUMN_PATCHES = [
    # auth.users 飞书 token 字段
    "ALTER TABLE workmanship_auth_users ADD COLUMN feishu_access_token  TEXT NOT NULL DEFAULT ('')",
    "ALTER TABLE workmanship_auth_users ADD COLUMN feishu_refresh_token TEXT NOT NULL DEFAULT ('')",
    "ALTER TABLE workmanship_auth_users ADD COLUMN feishu_token_expires_at DATETIME(6)",
    "ALTER TABLE workmanship_auth_users ADD COLUMN org_role TEXT DEFAULT NULL",
    # teams sort_order
    "ALTER TABLE workmanship_auth_teams ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0",
    # bop_versions 补列
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN visibility TEXT NOT NULL DEFAULT ('team')",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN shared_team_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN shared_project_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN data_stage TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN snapshot_data JSON DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN version_type TEXT DEFAULT ('working')",
    # pbom_versions 补列
    "ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN visibility TEXT NOT NULL DEFAULT ('team')",
    "ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN shared_team_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN shared_project_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN name TEXT DEFAULT ('')",
    # work.lists 补列
    "ALTER TABLE workmanship_work_lists ADD COLUMN shared_team_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_work_lists ADD COLUMN project_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_work_lists ADD COLUMN read_scope TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_work_lists ADD COLUMN write_scope TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_work_lists ADD COLUMN is_orphaned TINYINT(1) NOT NULL DEFAULT 0",
    # knowledge_items 补列
    "ALTER TABLE workmanship_know_items ADD COLUMN is_pinned TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_know_items ADD COLUMN is_hidden TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_know_items ADD COLUMN shared_project_gid CHAR(36) DEFAULT NULL",
    # onto_classes 补列（本体升级 Phase 1）
    "ALTER TABLE workmanship_onto_classes ADD COLUMN abbr TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_onto_classes ADD COLUMN ai00_level INTEGER DEFAULT NULL",
    "ALTER TABLE workmanship_onto_classes ADD COLUMN display_layer TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_onto_classes ADD COLUMN stats_priority INTEGER DEFAULT 99",
    "ALTER TABLE workmanship_onto_classes ADD COLUMN is_hidden_in_layout TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_onto_classes ADD COLUMN suggested_child_type TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_onto_classes ADD COLUMN entity_table TEXT DEFAULT NULL",
    # bop_entry_links 补列
    "ALTER TABLE workmanship_bop_bop_entry_links ADD COLUMN entity_gid CHAR(36) DEFAULT NULL",
    # ── factory.factory_sections 补列 ──────────────────────────────────────────
    "ALTER TABLE workmanship_factory_factory_sections ADD COLUMN owner_gid TEXT DEFAULT ('')",
    # ── integration.ext_mappings 补列 ──────────────────────────────────────────
    "ALTER TABLE workmanship_int_ext_mappings ADD COLUMN unique_key_col TEXT DEFAULT NULL",
    # ── knowledge.craft_rules 补列 ─────────────────────────────────────────────
    "ALTER TABLE workmanship_know_craft_rules ADD COLUMN deviation_count INTEGER DEFAULT 0",
    "ALTER TABLE workmanship_know_craft_rules ADD COLUMN creator_gid TEXT DEFAULT ('')",
    "ALTER TABLE workmanship_know_craft_rules ADD COLUMN scheduled_date DATE DEFAULT NULL",
    "ALTER TABLE workmanship_know_craft_rules ADD COLUMN owner_user_gid CHAR(36) DEFAULT NULL",
    # ── knowledge.knowledge_entries 补列 ───────────────────────────────────────
    "ALTER TABLE workmanship_know_entries ADD COLUMN scheduled_date DATE DEFAULT NULL",
    "ALTER TABLE workmanship_know_entries ADD COLUMN onto_class_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_know_entries ADD COLUMN onto_property_gid CHAR(36) DEFAULT NULL",
    # ── onto_properties 补列 ───────────────────────────────────────────────────
    "ALTER TABLE workmanship_onto_properties ADD COLUMN mapped_column TEXT DEFAULT NULL",
    # ── onto_relations 补列 ────────────────────────────────────────────────────
    "ALTER TABLE workmanship_onto_relations ADD COLUMN show_in_detail TINYINT(1) NOT NULL DEFAULT 1",
    # ── proj.issues 补列（软删除）──────────────────────────────────────────────
    "ALTER TABLE workmanship_proj_issues ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_proj_issues ADD COLUMN deleted_at DATETIME(6) DEFAULT NULL",
    "ALTER TABLE workmanship_proj_issues ADD COLUMN scheduled_date DATE DEFAULT NULL",
    # ── proj.issues 飞书字段 ───────────────────────────────────────────────────
    "ALTER TABLE workmanship_proj_issues ADD COLUMN feishu_assignee_open_id TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_issues ADD COLUMN feishu_assignee_name TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_issues ADD COLUMN feishu_group_chat_id TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_issues ADD COLUMN feishu_group_name TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_issues ADD COLUMN feishu_groups JSON NOT NULL DEFAULT (JSON_ARRAY())",
    "ALTER TABLE workmanship_proj_issues ADD COLUMN feishu_docs JSON NOT NULL DEFAULT (JSON_ARRAY())",
    # ── proj.tasks 飞书字段 ────────────────────────────────────────────────────
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN feishu_assignee_open_id TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN feishu_assignee_name TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN feishu_group_chat_id TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN feishu_group_name TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN feishu_groups JSON NOT NULL DEFAULT (JSON_ARRAY())",
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN feishu_docs JSON NOT NULL DEFAULT (JSON_ARRAY())",
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN canvas_row_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_proj_tasks ADD COLUMN canvas_col_gid CHAR(36) DEFAULT NULL",
    # ── work.tasks canvas 补列 ─────────────────────────────────────────────────
    "ALTER TABLE workmanship_work_tasks ADD COLUMN parent_task_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_work_tasks ADD COLUMN canvas_x DOUBLE DEFAULT NULL",
    "ALTER TABLE workmanship_work_tasks ADD COLUMN canvas_y DOUBLE DEFAULT NULL",
    "ALTER TABLE workmanship_work_tasks ADD COLUMN completion INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_work_tasks ADD COLUMN node_type TEXT NOT NULL DEFAULT ('normal')",
    "ALTER TABLE workmanship_work_tasks ADD COLUMN canvas_icon TEXT NOT NULL DEFAULT ('star')",
    # ── bop_versions 补列 ─────────────────────────────────────────────────────
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN is_archived TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN owner_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN pbom_version_gid CHAR(36) DEFAULT NULL",
    # ── bop_entry_links 版本和软删除补列（如果 schema.sql 没包含）──────────────
    "ALTER TABLE workmanship_bop_bop_entry_links ADD COLUMN version_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_entry_links ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_entry_links ADD COLUMN is_archived TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_entry_links ADD COLUMN deleted_at DATETIME(6) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_entry_links ADD COLUMN archived_at DATETIME(6) DEFAULT NULL",
    # ── pbom 补列 ─────────────────────────────────────────────────────────────
    "ALTER TABLE workmanship_bop_pbom ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_pbom ADD COLUMN vpps_source TEXT NOT NULL DEFAULT ('auto')",
    "ALTER TABLE workmanship_bop_pbom ADD COLUMN vpps_reported_at DATETIME(6) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_pbom ADD COLUMN remark TEXT DEFAULT ('')",
    "ALTER TABLE workmanship_bop_pbom ADD COLUMN temp_vpps TEXT DEFAULT NULL",
    # ── bop 实体表软删除补列（大量表）────────────────────────────────────────
    "ALTER TABLE workmanship_bop_bop_staging ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_staging ADD COLUMN is_archived TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_staging ADD COLUMN deleted_at DATETIME(6) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_staging ADD COLUMN archived_at DATETIME(6) DEFAULT NULL",
    # ── bop_entries 补列（核心列）────────────────────────────────────────────
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN child_vpps JSON NOT NULL DEFAULT (JSON_ARRAY())",
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN is_archived TINYINT(1) NOT NULL DEFAULT 0",
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN assignee_user_gid CHAR(36) DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN scheduled_date DATE DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN process_chart_pic JSON DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN bom_row_owner TEXT DEFAULT NULL",
    "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN parent_bop_title TEXT DEFAULT NULL",
    # ── tpl_vpps_parts 补列 ───────────────────────────────────────────────────
    "ALTER TABLE workmanship_tpl_vpps_parts ADD COLUMN alias JSON NOT NULL DEFAULT (JSON_ARRAY())",
]

# ─────────────────────────────────────────────────────────────────────────────
# 4. 种子数据
# ─────────────────────────────────────────────────────────────────────────────

_SEED_DATA = [
    """
    INSERT IGNORE INTO workmanship_know_folders
      (gid, parent_gid, scope_type, team_gid, name, sort_order, creator_gid)
    VALUES
      ('system-folder-public-resources', NULL, 'public', NULL, '公共资料', 0, 'system')
    """,
    """
    INSERT INTO workmanship_know_items
      (gid, folder_gid, scope_type, team_gid, item_type, title, status, is_system,
       content_md, file_path, url, site_ref, tags, creator_gid)
    VALUES
      ('system-project-info',
       'system-folder-public-resources',
       'public', NULL, 'site_page', '业务基础信息', 'published', TRUE,
       '', '', '',
       '{"path": "knowledge_hub/pages/project_info.html"}',
       '[]', 'system')
    ON DUPLICATE KEY UPDATE
      folder_gid = VALUES(folder_gid),
      is_system  = VALUES(is_system),
      site_ref   = VALUES(site_ref)
    """,
]
