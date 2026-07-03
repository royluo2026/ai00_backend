"""
backend/main.py
────────────────
AI00 云端后端服务入口

部署：
  # 开发
  uvicorn backend.main:app --reload --port 8080

  # 生产（建议用 gunicorn + uvicorn worker）
  gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8080

  # Docker
  docker build -t ai00-backend . && docker run -p 8080:8080 --env-file .env ai00-backend
"""
import asyncio
import importlib
import logging
import os
import pkgutil
import sys
import time
from pathlib import Path as _Path

# 确保 packages/ 目录在 Python 路径中（供 packages.craft_plugin 等模块 import）
_PACKAGES_DIR = str(_Path(__file__).parent.parent / "packages")
if _PACKAGES_DIR not in sys.path:
    sys.path.insert(0, _PACKAGES_DIR)
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.log_setup import setup_logging
from backend.db.connection import init_pool

# ── 日志初始化（必须在所有模块 import 之前完成）─────────────────────────────────
setup_logging(os.getenv("LOG_LEVEL", "INFO"))

_log = logging.getLogger(__name__)


def _ensure_lists_table():
    """幂等建表：lists + list_gid 列补丁（无需手动 DBeaver 执行）。"""
    from backend.db.connection import get_conn
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_lists (
            gid           TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            color         TEXT NOT NULL DEFAULT '#5b8dee',
            storage_scope TEXT NOT NULL DEFAULT 'cloud',
            owner_type    TEXT NOT NULL DEFAULT 'user',
            owner_gid     TEXT NOT NULL DEFAULT '',
            item_type     TEXT NOT NULL DEFAULT 'task',
            sort_order    INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_lists_owner ON workmanship_work_lists (owner_type, owner_gid)",
        "CREATE INDEX IF NOT EXISTS idx_lists_item_type ON workmanship_work_lists (item_type)",
        "ALTER TABLE workmanship_work_lists ADD COLUMN IF NOT EXISTS item_type TEXT NOT NULL DEFAULT 'task'",
        "ALTER TABLE workmanship_work_tasks  ADD COLUMN IF NOT EXISTS list_gid TEXT",
        "ALTER TABLE workmanship_work_issues ADD COLUMN IF NOT EXISTS list_gid TEXT",
        # Task 5: 附件字段
        "ALTER TABLE workmanship_work_tasks  ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'",
        "ALTER TABLE workmanship_work_issues ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'",
        # Task 7: factory_sections owner_gid
        "ALTER TABLE workmanship_factory_factory_sections ADD COLUMN IF NOT EXISTS owner_gid TEXT DEFAULT ''",
        # Task 8: knowledge_entries 补全
        """
        CREATE TABLE IF NOT EXISTS workmanship_know_entries (
            gid            TEXT PRIMARY KEY,
            title          TEXT NOT NULL DEFAULT '',
            entry_type     TEXT NOT NULL DEFAULT 'guide',
            content_ref    JSONB DEFAULT '{}',
            content_md     TEXT DEFAULT '',
            related_part_nos JSONB DEFAULT '[]',
            related_operation_gids JSONB DEFAULT '[]',
            tags           JSONB DEFAULT '[]',
            source_project_gid TEXT,
            creator_gid    TEXT DEFAULT '',
            status         TEXT NOT NULL DEFAULT 'draft',
            share_scope    TEXT NOT NULL DEFAULT 'team',
            list_gid       TEXT,
            source_gid     TEXT,
            source_label   TEXT DEFAULT '',
            maintainer_gid TEXT DEFAULT '',
            contributors   JSONB DEFAULT '[]',
            attachments    JSONB DEFAULT '[]',
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            updated_at     TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "ALTER TABLE workmanship_know_entries ADD COLUMN IF NOT EXISTS source_gid TEXT",
        "ALTER TABLE workmanship_know_entries ADD COLUMN IF NOT EXISTS source_label TEXT DEFAULT ''",
        "ALTER TABLE workmanship_know_entries ADD COLUMN IF NOT EXISTS maintainer_gid TEXT DEFAULT ''",
        "ALTER TABLE workmanship_know_entries ADD COLUMN IF NOT EXISTS contributors JSONB DEFAULT '[]'",
        "ALTER TABLE workmanship_know_entries ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'",
        # Task 9: craft_rules 云端表（CREATE 必须在 ALTER 之前）
        """
        CREATE TABLE IF NOT EXISTS workmanship_know_craft_rules (
            gid               TEXT PRIMARY KEY,
            code              TEXT NOT NULL DEFAULT '',
            name              TEXT NOT NULL DEFAULT '',
            rule_type         TEXT NOT NULL DEFAULT 'process',
            enforcement_level TEXT NOT NULL DEFAULT 'advisory',
            status            TEXT NOT NULL DEFAULT 'draft',
            share_scope       TEXT NOT NULL DEFAULT 'team',
            list_gid          TEXT,
            rule_definition   JSONB DEFAULT '{}',
            deviation_count   INTEGER DEFAULT 0,
            creator_gid       TEXT DEFAULT '',
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        # knowledge_display_seq + display_id（INSERT 需要）
        "CREATE SEQUENCE IF NOT EXISTS knowledge.knowledge_display_seq START 1",
        "ALTER TABLE workmanship_know_entries ADD COLUMN IF NOT EXISTS display_id TEXT NOT NULL DEFAULT ''",
        # rules_display_seq + display_id（INSERT 需要；schema.sql 建表时缺 deviation_count/creator_gid，补列）
        "CREATE SEQUENCE IF NOT EXISTS knowledge.rules_display_seq START 1",
        "ALTER TABLE workmanship_know_craft_rules ADD COLUMN IF NOT EXISTS display_id       TEXT    NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_know_craft_rules ADD COLUMN IF NOT EXISTS deviation_count  INTEGER DEFAULT 0",
        "ALTER TABLE workmanship_know_craft_rules ADD COLUMN IF NOT EXISTS creator_gid      TEXT    DEFAULT ''",
        # Phase 2-B: 工作台标注数据
        """
        CREATE TABLE IF NOT EXISTS workmanship_app_wb_annotations (
            key        TEXT PRIMARY KEY,
            data       TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        # item_entries：条目沟通历史表
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_item_entries (
            gid           TEXT PRIMARY KEY,
            id            TEXT NOT NULL,
            item_type     TEXT NOT NULL,
            item_gid      TEXT NOT NULL,
            parent_id     TEXT,
            section       TEXT NOT NULL DEFAULT 'detail',
            author        TEXT NOT NULL DEFAULT 'human',
            author_name   TEXT DEFAULT '',
            author_gid    TEXT DEFAULT '',
            content       TEXT DEFAULT '',
            resolved      BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order    DOUBLE PRECISION NOT NULL DEFAULT 0,
            read_by_human BOOLEAN NOT NULL DEFAULT TRUE,
            ai_status     TEXT DEFAULT 'unread',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_item_entries_item ON workmanship_work_item_entries (item_type, item_gid)",
        "CREATE INDEX IF NOT EXISTS idx_item_entries_parent ON workmanship_work_item_entries (parent_id)",
        # knowledge_hub 表（公共/团队知识库）
        """
        CREATE TABLE IF NOT EXISTS workmanship_know_folders (
          gid         TEXT PRIMARY KEY,
          parent_gid  TEXT DEFAULT NULL,
          scope_type  TEXT NOT NULL DEFAULT 'personal',
          team_gid    TEXT DEFAULT NULL,
          name        TEXT NOT NULL DEFAULT '',
          sort_order  INTEGER NOT NULL DEFAULT 0,
          creator_gid TEXT DEFAULT '',
          created_at  TIMESTAMPTZ DEFAULT NOW(),
          updated_at  TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_kfolders_scope ON workmanship_know_folders (scope_type, team_gid)",
        """
        CREATE TABLE IF NOT EXISTS workmanship_know_items (
          gid          TEXT PRIMARY KEY,
          folder_gid   TEXT DEFAULT NULL,
          scope_type   TEXT NOT NULL DEFAULT 'personal',
          team_gid     TEXT DEFAULT NULL,
          item_type    TEXT NOT NULL DEFAULT 'richtext',
          title        TEXT NOT NULL DEFAULT '',
          status       TEXT NOT NULL DEFAULT 'draft',
          content_body JSONB DEFAULT NULL,
          content_md   TEXT DEFAULT '',
          file_path    TEXT DEFAULT '',
          url          TEXT DEFAULT '',
          site_ref     JSONB DEFAULT NULL,
          tags         JSONB DEFAULT '[]',
          creator_gid  TEXT DEFAULT '',
          created_at   TIMESTAMPTZ DEFAULT NOW(),
          updated_at   TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_kitems_folder ON workmanship_know_items (folder_gid)",
        "CREATE INDEX IF NOT EXISTS idx_kitems_scope ON workmanship_know_items (scope_type)",
        """
        CREATE TABLE IF NOT EXISTS workmanship_know_favorites (
          user_gid   TEXT NOT NULL,
          item_gid   TEXT NOT NULL,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          PRIMARY KEY (user_gid, item_gid)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS workmanship_know_recent (
          user_gid    TEXT NOT NULL,
          item_gid    TEXT NOT NULL,
          accessed_at TIMESTAMPTZ DEFAULT NOW(),
          PRIMARY KEY (user_gid, item_gid)
        )
        """,
        # knowledge_items: is_system 列（系统内置条目标记，必须在 INSERT seed 之前）
        "ALTER TABLE workmanship_know_items ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE",
        # projects 表字段扩展（2026-05-12）
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS project_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS model_year INTEGER",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS suffix TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS jph REAL",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ",
        "ALTER TABLE workmanship_proj_projects ADD COLUMN IF NOT EXISTS share_scope TEXT NOT NULL DEFAULT 'team'",
        # 飞书用户 token 存储（用于代表用户访问文档等）
        "ALTER TABLE workmanship_auth_users ADD COLUMN IF NOT EXISTS feishu_access_token TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_auth_users ADD COLUMN IF NOT EXISTS feishu_refresh_token TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_auth_users ADD COLUMN IF NOT EXISTS feishu_token_expires_at TIMESTAMPTZ",
        # 飞书 open_id 冗余存储（org sync 用）
        "ALTER TABLE workmanship_auth_users ADD COLUMN IF NOT EXISTS feishu_open_id TEXT NOT NULL DEFAULT ''",
        "CREATE INDEX IF NOT EXISTS idx_users_feishu_open_id ON workmanship_auth_users (feishu_open_id) WHERE feishu_open_id != ''",
        # teams: sort_order（飞书部门顺序）
        "ALTER TABLE workmanship_auth_teams ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0",
        # 任务画布字段（2026-05-24）
        "ALTER TABLE workmanship_work_tasks ADD COLUMN IF NOT EXISTS parent_task_gid TEXT DEFAULT NULL",
        "ALTER TABLE workmanship_work_tasks ADD COLUMN IF NOT EXISTS canvas_x REAL DEFAULT NULL",
        "ALTER TABLE workmanship_work_tasks ADD COLUMN IF NOT EXISTS canvas_y REAL DEFAULT NULL",
        "ALTER TABLE workmanship_work_tasks ADD COLUMN IF NOT EXISTS completion INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE workmanship_work_tasks ADD COLUMN IF NOT EXISTS node_type TEXT NOT NULL DEFAULT 'normal'",
        "ALTER TABLE workmanship_work_tasks ADD COLUMN IF NOT EXISTS canvas_icon TEXT NOT NULL DEFAULT 'star'",
        # 任务依赖关系表（画布连线）
        """
        CREATE TABLE IF NOT EXISTS work.task_dependencies (
            gid           TEXT PRIMARY KEY,
            source_gid    TEXT NOT NULL,
            target_gid    TEXT NOT NULL,
            edge_type     TEXT NOT NULL DEFAULT 'prerequisite',
            dep_condition TEXT NOT NULL DEFAULT 'done',
            dep_group     TEXT DEFAULT NULL,
            label         TEXT NOT NULL DEFAULT '',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_task_deps_source ON work.task_dependencies(source_gid)",
        "CREATE INDEX IF NOT EXISTS idx_task_deps_target ON work.task_dependencies(target_gid)",
        # workmanship_proj_tasks 新列（现役表，旧数据库可能缺失）
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS list_gid             TEXT DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS is_deleted           BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS deleted_at           TIMESTAMPTZ DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS scheduled_date       DATE DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS scheduled_start_time TIME DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS time_estimate        INTEGER DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS attachments          JSONB NOT NULL DEFAULT '[]'",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS parent_task_gid      TEXT DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS canvas_x             REAL DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS canvas_y             REAL DEFAULT NULL",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS completion           INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS node_type            TEXT NOT NULL DEFAULT 'normal'",
        "ALTER TABLE workmanship_proj_tasks ADD COLUMN IF NOT EXISTS canvas_icon          TEXT NOT NULL DEFAULT 'star'",
        # workmanship_proj_issues 新列
        "ALTER TABLE workmanship_proj_issues ADD COLUMN IF NOT EXISTS scheduled_date      DATE DEFAULT NULL",
        "ALTER TABLE workmanship_proj_issues ADD COLUMN IF NOT EXISTS attachments         JSONB DEFAULT '[]'",
        # 可见范围统一管理：shared_team_gid 存储具体团队 gid
        "ALTER TABLE workmanship_work_lists ADD COLUMN IF NOT EXISTS shared_team_gid TEXT DEFAULT NULL",
        # BOP 版本 visibility 字段
        "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'team'",
        "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS shared_team_gid TEXT DEFAULT NULL",
        "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS shared_project_gid TEXT DEFAULT NULL",
        # BOP 版本 data_stage 字段（craft-plugin 新增）
        "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS data_stage TEXT DEFAULT NULL",
        "ALTER TABLE workmanship_bop_bop_versions ADD COLUMN IF NOT EXISTS snapshot_data JSONB DEFAULT NULL",
        # PBOM 版本 visibility 字段
        "ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'team'",
        "ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS shared_team_gid TEXT DEFAULT NULL",
        "ALTER TABLE workmanship_bop_pbom_versions ADD COLUMN IF NOT EXISTS shared_project_gid TEXT DEFAULT NULL",
        # knowledge_items 补充 project scope 支持
        "ALTER TABLE workmanship_know_items ADD COLUMN IF NOT EXISTS shared_project_gid TEXT DEFAULT NULL",
        # 系统内置 公共资料 文件夹（固定 GID，幂等）
        """
        INSERT INTO workmanship_know_folders
          (gid, parent_gid, scope_type, team_gid, name, sort_order, creator_gid, created_at, updated_at)
        VALUES
          ('system-folder-public-resources', NULL, 'public', NULL, '公共资料', 0, 'system', NOW(), NOW())
        ON CONFLICT (gid) DO NOTHING
        """,
        # 系统内置 项目信息 页面（固定 GID，置顶，仅超管可删）
        # ON CONFLICT DO UPDATE 确保已存在的记录也移入正确文件夹
        """
        INSERT INTO workmanship_know_items
          (gid, folder_gid, scope_type, team_gid, item_type, title, status, is_system,
           content_body, content_md, file_path, url, site_ref, tags,
           creator_gid, created_at, updated_at)
        VALUES
          ('system-project-info',
           'system-folder-public-resources',
           'public', NULL, 'site_page', '业务基础信息', 'published', TRUE,
           NULL, '', '', '',
           '{"path": "knowledge_hub/pages/project_info.html"}',
           '[]', 'system', NOW(), NOW())
        ON DUPLICATE KEY UPDATE
          folder_gid = VALUES(folder_gid),
          is_system  = VALUES(is_system),
          site_ref   = VALUES(site_ref)
        """,
    ]
    import logging
    for stmt in ddl_statements:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.commit()
        except Exception as e:
            logging.getLogger(__name__).warning("_ensure_lists_table stmt failed: %s | %s", stmt[:60], e)

    # BOP 加列（独立事务，避免被主 DDL 列表失败拖回滚）
    _bop_alters = [
        "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN IF NOT EXISTS process_flow_pic JSONB DEFAULT NULL",
        "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN IF NOT EXISTS process_chart_pic JSONB DEFAULT NULL",
        "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_bop_bop_entries ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workmanship_bop_bop_steps ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_bop_bop_steps ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workmanship_bop_bop_process ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_bop_bop_process ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for stmt in _bop_alters:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        conn.rollback()  # 单条失败不影响后续
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_lists_table BOP alters: %s", e)

    # BOP 暂存箱表（独立事务）
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS workmanship_bop_bop_staging (
                        gid                TEXT PRIMARY KEY,
                        bop_version_gid    TEXT NOT NULL REFERENCES workmanship_bop_bop_versions(gid) ON DELETE CASCADE,
                        node_type          TEXT NOT NULL DEFAULT 'process',
                        title              TEXT NOT NULL DEFAULT '',
                        vpps               TEXT,
                        source_type        TEXT,
                        source_ref_gid     TEXT,
                        original_entry_gid TEXT,
                        child_count        INTEGER NOT NULL DEFAULT 0,
                        meta               JSONB NOT NULL DEFAULT '{}',
                        sort_order         REAL NOT NULL DEFAULT 0,
                        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        created_by         TEXT
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bop_staging_version
                    ON workmanship_bop_bop_staging(bop_version_gid)
                """)
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_lists_table bop_staging: %s", e)


def _ensure_bitable_sync_tables():
    """幂等建表：list_bitable_bindings + list_bitable_record_map。"""
    from backend.db.connection import get_conn
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_list_bitable_bindings (
            list_gid           TEXT PRIMARY KEY,
            app_token          TEXT NOT NULL,
            table_id           TEXT NOT NULL,
            field_mapping      JSONB NOT NULL DEFAULT '{}',
            sync_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
            webhook_secret     TEXT,
            has_remote_updates BOOLEAN NOT NULL DEFAULT FALSE,
            last_push_at       TIMESTAMPTZ,
            last_pull_at       TIMESTAMPTZ,
            created_by         TEXT NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_deleted         BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at         TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_list_bitable_record_map (
            list_gid          TEXT NOT NULL,
            item_gid          TEXT NOT NULL,
            record_id         TEXT NOT NULL,
            ai00_updated_at   TIMESTAMPTZ,
            feishu_updated_at TIMESTAMPTZ,
            is_deleted        BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at        TIMESTAMPTZ,
            PRIMARY KEY (list_gid, item_gid)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bitable_record_map_record ON workmanship_work_list_bitable_record_map (list_gid, record_id)",
    ]
    import logging
    _log = logging.getLogger(__name__)
    for stmt in ddl:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.commit()
        except Exception as e:
            _log.warning("_ensure_bitable_sync_tables stmt failed: %s | %s", stmt[:60], e)


def _ensure_permission_tables():
    """幂等建表/加列：四层权限模型（Phase 1）。"""
    from backend.db.connection import get_conn
    ddl = [
        # 1. workmanship_auth_users 新增 org_role 列
        "ALTER TABLE workmanship_auth_users ADD COLUMN IF NOT EXISTS org_role TEXT DEFAULT NULL",
        # 2. 数据迁移：旧 system_role → org_role（幂等，只更新 NULL）
        """UPDATE workmanship_auth_users SET org_role = CASE
               WHEN system_role = 'super_admin' THEN 'super_admin'
               WHEN system_role = 'external'    THEN 'external'
               ELSE 'member'
           END WHERE org_role IS NULL""",
        # 3. permission_grants 表
        """
        CREATE TABLE IF NOT EXISTS workmanship_auth_permission_grants (
            gid         TEXT PRIMARY KEY,
            grantee_gid TEXT NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
            grant_type  TEXT NOT NULL,
            scope_gid   TEXT,
            granted_by  TEXT REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
            granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at  TIMESTAMPTZ,
            note        TEXT NOT NULL DEFAULT '',
            UNIQUE (grantee_gid, grant_type, scope_gid)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_grants_grantee    ON workmanship_auth_permission_grants (grantee_gid)",
        "CREATE INDEX IF NOT EXISTS idx_grants_type_scope ON workmanship_auth_permission_grants (grant_type, scope_gid)",
        # 4. workmanship_work_lists 孤儿标记
        "ALTER TABLE workmanship_work_lists ADD COLUMN IF NOT EXISTS is_orphaned BOOLEAN NOT NULL DEFAULT FALSE",
        # 5. 迁移旧 team_admin 角色 → permission_grants（幂等）
        """INSERT INTO workmanship_auth_permission_grants (gid, grantee_gid, grant_type, scope_gid, granted_by)
           SELECT 'mg_' || gid, gid, 'team_admin', team_id, NULL
           FROM workmanship_auth_users
           WHERE system_role = 'team_admin' AND team_id IS NOT NULL AND team_id != ''""",
    ]
    import logging
    for stmt in ddl:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.commit()
        except Exception as e:
            logging.getLogger(__name__).warning("_ensure_permission_tables stmt failed: %s | %s", stmt[:60], e)


def _ensure_gbop_tables():
    """幂等建表：GBOP 标准工序库 V2 全套表。"""
    from backend.db.connection import get_conn
    ddl = [
        "CREATE SCHEMA IF NOT EXISTS template",
        """
        CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_versions (
            gid                TEXT PRIMARY KEY,
            name               TEXT NOT NULL DEFAULT '',
            version_family_gid TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'draft',
            frozen_at          TIMESTAMPTZ,
            archived_at        TIMESTAMPTZ,
            vehicle_model      TEXT NOT NULL DEFAULT '',
            team_id            TEXT,
            created_by         TEXT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        """
        CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_entries (
            gid            TEXT PRIMARY KEY,
            version_gid    TEXT NOT NULL REFERENCES workmanship_tpl_gbop_versions(gid) ON DELETE CASCADE,
            parent_gid     TEXT REFERENCES workmanship_tpl_gbop_entries(gid) ON DELETE SET NULL,
            level          SMALLINT NOT NULL DEFAULT 0,
            node_type      TEXT NOT NULL DEFAULT 'process',
            seq_no         REAL NOT NULL DEFAULT 0,
            vpps           TEXT,
            vpps_desc      TEXT NOT NULL DEFAULT '',
            vpps_attr      TEXT NOT NULL DEFAULT '',
            importance     TEXT NOT NULL DEFAULT '',
            torque_importance TEXT NOT NULL DEFAULT '',
            vehicle_model  TEXT NOT NULL DEFAULT '',
            parent_vpps    TEXT NOT NULL DEFAULT '',
            status         TEXT NOT NULL DEFAULT 'active',
            sort_order     REAL NOT NULL DEFAULT 0,
            meta           JSONB NOT NULL DEFAULT '{}',
            team_id        TEXT,
            created_by     TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_gbop_entries_version ON workmanship_tpl_gbop_entries(version_gid)",
        "CREATE INDEX IF NOT EXISTS idx_gbop_entries_parent  ON workmanship_tpl_gbop_entries(parent_gid)",
        "CREATE INDEX IF NOT EXISTS idx_gbop_entries_vpps    ON workmanship_tpl_gbop_entries(vpps) WHERE vpps IS NOT NULL",
        """
        CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_processes (
            gid             TEXT PRIMARY KEY,
            version_gid     TEXT NOT NULL REFERENCES workmanship_tpl_gbop_versions(gid) ON DELETE CASCADE,
            vpps            TEXT,
            vpps_desc       TEXT NOT NULL DEFAULT '',
            op_code         TEXT NOT NULL DEFAULT '',
            op_name         TEXT NOT NULL DEFAULT '',
            standard_time   REAL,
            description     TEXT NOT NULL DEFAULT '',
            steps           JSONB NOT NULL DEFAULT '[]',
            required_tools  JSONB NOT NULL DEFAULT '[]',
            parameters      JSONB NOT NULL DEFAULT '{}',
            importance      TEXT NOT NULL DEFAULT '',
            torque_importance TEXT NOT NULL DEFAULT '',
            vehicle_model   TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'active',
            meta            JSONB NOT NULL DEFAULT '{}',
            created_by      TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_gbop_processes_version ON workmanship_tpl_gbop_processes(version_gid)",
        """
        CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_operations (
            gid             TEXT PRIMARY KEY,
            version_gid     TEXT NOT NULL REFERENCES workmanship_tpl_gbop_versions(gid) ON DELETE CASCADE,
            process_gid     TEXT REFERENCES workmanship_tpl_gbop_processes(gid) ON DELETE SET NULL,
            vpps            TEXT,
            vpps_desc       TEXT NOT NULL DEFAULT '',
            op_code         TEXT NOT NULL DEFAULT '',
            op_name         TEXT NOT NULL DEFAULT '',
            standard_time   REAL,
            description     TEXT NOT NULL DEFAULT '',
            steps           JSONB NOT NULL DEFAULT '[]',
            required_tools  JSONB NOT NULL DEFAULT '[]',
            parameters      JSONB NOT NULL DEFAULT '{}',
            importance      TEXT NOT NULL DEFAULT '',
            torque_importance TEXT NOT NULL DEFAULT '',
            vehicle_model   TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'active',
            meta            JSONB NOT NULL DEFAULT '{}',
            created_by      TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_gbop_operations_version ON workmanship_tpl_gbop_operations(version_gid)",
        "CREATE INDEX IF NOT EXISTS idx_gbop_operations_process ON workmanship_tpl_gbop_operations(process_gid)",
        """
        CREATE TABLE IF NOT EXISTS workmanship_tpl_gbop_entry_links (
            gid         TEXT PRIMARY KEY,
            entry_gid   TEXT NOT NULL REFERENCES workmanship_tpl_gbop_entries(gid) ON DELETE CASCADE,
            link_type   TEXT NOT NULL DEFAULT '',
            ref_gid     TEXT NOT NULL DEFAULT '',
            is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by  TEXT NOT NULL DEFAULT '',
            UNIQUE (entry_gid, link_type, ref_gid)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_gbop_entry_links_entry ON workmanship_tpl_gbop_entry_links(entry_gid)",
        "CREATE INDEX IF NOT EXISTS idx_gbop_entry_links_ref ON workmanship_tpl_gbop_entry_links(ref_gid)",
        # vpps_parts（标准零件库，import-vpps-parts 依赖此表）
        """
        CREATE TABLE IF NOT EXISTS workmanship_tpl_vpps_parts (
            gid              TEXT PRIMARY KEY,
            vpps_description TEXT NOT NULL DEFAULT '',
            part_category    TEXT NOT NULL DEFAULT '',
            description      TEXT NOT NULL DEFAULT '',
            level            TEXT NOT NULL DEFAULT '',
            vpps_desc_cn     TEXT NOT NULL DEFAULT '',
            vpps             TEXT,
            importance       TEXT NOT NULL DEFAULT '',
            vehicle_model    TEXT NOT NULL DEFAULT '',
            parent_vpps      TEXT NOT NULL DEFAULT '',
            status           TEXT NOT NULL DEFAULT 'active',
            meta             JSONB NOT NULL DEFAULT '{}',
            team_id          TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_vpps_parts_vpps ON workmanship_tpl_vpps_parts(vpps) WHERE vpps IS NOT NULL",
        # 幂等补列：旧表可能缺 parent_vpps
        "ALTER TABLE workmanship_tpl_vpps_parts ADD COLUMN IF NOT EXISTS parent_vpps TEXT NOT NULL DEFAULT ''",
        # vpps_part + part_feed（工序/操作所针对的零件 + 是否涉及上料）
        "ALTER TABLE workmanship_tpl_gbop_entries    ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_tpl_gbop_entries    ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workmanship_tpl_gbop_processes  ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_tpl_gbop_processes  ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workmanship_tpl_gbop_operations ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workmanship_tpl_gbop_operations ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for stmt in ddl:
                    cur.execute(stmt)
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_gbop_tables: %s", e)


def _ensure_vpps_operations_table():
    """幂等建表：bop.vpps_operations（VPPS 操作审计）。"""
    from backend.db.connection import get_conn
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS bop.vpps_operations (
            gid              TEXT PRIMARY KEY,
            pbom_version_gid TEXT NOT NULL,
            pbom_row_gid     TEXT NOT NULL,
            operation_type   TEXT NOT NULL,
            rule_no          INTEGER,
            field_name       TEXT,
            original_value   TEXT,
            new_value        TEXT,
            actor_gid        TEXT NOT NULL,
            actor_name       TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            notes            TEXT,
            is_active        BOOLEAN NOT NULL DEFAULT TRUE,
            reverted_at      TIMESTAMPTZ,
            reverted_by_gid  TEXT,
            reverted_by_name TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_vpps_ops_version ON bop.vpps_operations(pbom_version_gid)",
        "CREATE INDEX IF NOT EXISTS idx_vpps_ops_row     ON bop.vpps_operations(pbom_row_gid)",
    ]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for stmt in ddl:
                    cur.execute(stmt)
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_vpps_operations_table: %s", e)


def _ensure_share_tables():
    """幂等建表/加列：read_scope/write_scope + list_shares + item_shares（Phase 2）。"""
    from backend.db.connection import get_conn
    ddl = [
        "ALTER TABLE workmanship_work_lists ADD COLUMN IF NOT EXISTS read_scope  TEXT NOT NULL DEFAULT 'team'",
        "ALTER TABLE workmanship_work_lists ADD COLUMN IF NOT EXISTS write_scope TEXT NOT NULL DEFAULT 'personal'",
        """UPDATE workmanship_work_lists SET
            read_scope  = CASE visibility WHEN 'public' THEN 'global' WHEN 'private' THEN 'personal' ELSE 'team' END,
            write_scope = CASE visibility WHEN 'public' THEN 'team'   WHEN 'private' THEN 'personal' ELSE 'personal' END
           WHERE read_scope = 'team' AND write_scope = 'personal'""",
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_list_shares (
            gid        TEXT PRIMARY KEY,
            list_gid   TEXT NOT NULL REFERENCES workmanship_work_lists(gid) ON DELETE CASCADE,
            shared_to  TEXT NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
            permission TEXT NOT NULL DEFAULT 'read',
            shared_by  TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (list_gid, shared_to)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_list_shares_list ON workmanship_work_list_shares (list_gid)",
        "CREATE INDEX IF NOT EXISTS idx_list_shares_user ON workmanship_work_list_shares (shared_to)",
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_item_shares (
            gid        TEXT PRIMARY KEY,
            item_type  TEXT NOT NULL,
            item_gid   TEXT NOT NULL,
            shared_to  TEXT NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
            permission TEXT NOT NULL DEFAULT 'read',
            shared_by  TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (item_type, item_gid, shared_to)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_item_shares_item ON workmanship_work_item_shares (item_type, item_gid)",
        "CREATE INDEX IF NOT EXISTS idx_item_shares_user ON workmanship_work_item_shares (shared_to)",
    ]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for stmt in ddl:
                    cur.execute(stmt)
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_share_tables: %s", e)


def _ensure_deep_link_tables():
    """幂等建表：share_links + permission_requests（Phase 3）。"""
    from backend.db.connection import get_conn
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_share_links (
            token        TEXT PRIMARY KEY,
            target_type  TEXT NOT NULL,
            target_gid   TEXT NOT NULL,
            item_type    TEXT DEFAULT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            created_by   TEXT NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at   TIMESTAMPTZ DEFAULT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_share_links_target ON workmanship_work_share_links (target_type, target_gid)",
        """
        CREATE TABLE IF NOT EXISTS workmanship_work_permission_requests (
            gid             TEXT PRIMARY KEY,
            requester_gid   TEXT NOT NULL REFERENCES workmanship_auth_users(gid) ON DELETE CASCADE,
            target_type     TEXT NOT NULL,
            target_gid      TEXT NOT NULL,
            want_permission TEXT NOT NULL DEFAULT 'read',
            status          TEXT NOT NULL DEFAULT 'pending',
            message         TEXT DEFAULT '',
            responded_by    TEXT REFERENCES workmanship_auth_users(gid) ON DELETE SET NULL,
            responded_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_perm_req_target ON workmanship_work_permission_requests (target_type, target_gid)",
        "CREATE INDEX IF NOT EXISTS idx_perm_req_status ON workmanship_work_permission_requests (status)",
    ]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for stmt in ddl:
                    cur.execute(stmt)
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_deep_link_tables: %s", e)


def _ensure_change_log_tables():
    from backend.db.connection import get_conn
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS workmanship_work_item_change_logs (
                        gid        TEXT PRIMARY KEY,
                        item_type  TEXT NOT NULL,
                        item_gid   TEXT NOT NULL,
                        list_gid   TEXT DEFAULT NULL,
                        changed_by TEXT NOT NULL,
                        changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        field_name TEXT NOT NULL,
                        old_value  TEXT,
                        new_value  TEXT
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_change_logs_item
                    ON workmanship_work_item_change_logs (item_type, item_gid)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_change_logs_list
                    ON workmanship_work_item_change_logs (list_gid)
                    WHERE list_gid IS NOT NULL
                """)
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_change_log_tables: %s", e)


def _ensure_ai_memory_table():
    """幂等建表：workmanship_app_ai_memory（结构化 AI 记忆）。"""
    from backend.db.connection import get_conn
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS workmanship_app_ai_memory (
                        gid         TEXT PRIMARY KEY,
                        user_gid    TEXT NOT NULL DEFAULT '',
                        memory_key  TEXT NOT NULL DEFAULT '',
                        content     TEXT NOT NULL DEFAULT '',
                        tag         TEXT NOT NULL DEFAULT 'preference',
                        scope       TEXT NOT NULL DEFAULT 'user',
                        confidence  REAL NOT NULL DEFAULT 1.0,
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (user_gid, memory_key)
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_memory_user
                    ON workmanship_app_ai_memory (user_gid, tag)
                """)
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_ai_memory_table: %s", e)


def _ensure_feishu_cache_table():
    """幂等建表：workmanship_app_feishu_search_cache（飞书搜索结果持久化缓存）。"""
    try:
        from backend.services.feishu_cache_service import ensure_table
        ensure_table()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_feishu_cache_table: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    # MinIO 对象存储初始化（未配置则静默跳过，回退本地磁盘）
    from backend.core.storage import init_storage
    init_storage()
    # MySQL 启动时幂等迁移（替代所有 _ensure_* 函数）
    try:
        from backend.db.connection import get_conn
        from backend.db.migrate import run_safe_migrations
        with get_conn() as conn:
            run_safe_migrations(conn)
    except Exception as _e:
        _log.warning("run_safe_migrations 跳过: %s", _e)
    # 确保附件目录存在
    Path(__file__).parent.joinpath("static", "uploads").mkdir(parents=True, exist_ok=True)
    # 工程框架技能种子数据（INSERT IGNORE，幂等安全）
    try:
        from backend.ai_assistant.engineering_skills_seed import seed_engineering_skills
        seed_engineering_skills()
    except Exception as _e:
        _log.warning(f"seed_engineering_skills 跳过: {_e}")
    yield


app = FastAPI(
    title="AI00 Cloud Backend",
    version="1.0.0",  # ⚠️ 发版时需与 package.json 的 version 字段手动保持同步
    description="AI00 厂商云端服务 — 持有飞书凭证，代理 OAuth 和 API 调用",
    docs_url="/docs",
    lifespan=lifespan,
)


# ── 全局未捕获异常处理 ────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    _log.error(
        "未捕获异常 %s %s → %s\n%s",
        request.method,
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {type(exc).__name__}"},
    )


# ── HTML 文件 no-cache middleware（防止浏览器缓存旧版本）────────────────────
@app.middleware("http")
async def html_no_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith('.html') or path.endswith('/') or path.endswith('.js') or path.endswith('.css'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ── 请求访问日志 middleware ───────────────────────────────────────────────────
@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    import sys as _sys
    _sys.stdout.write(f"[MW] {request.method} {request.url.path}\n")
    _sys.stdout.flush()
    start = time.time()
    req_id = (request.headers.get("x-request-id", "") or "")[:16] or "-"
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        _log.error("❌ [%s] %s %s → 500 %dms | %s", req_id, request.method, request.url.path, duration_ms, exc)
        raise
    duration_ms = int((time.time() - start) * 1000)
    level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
    _log.log(level, "[%s] %s %s → %d %dms", req_id, request.method, request.url.path, response.status_code, duration_ms)
    if duration_ms > _SLOW_MS:
        _log.warning("🐢 SLOW [%s] %s %s → %d %dms", req_id, request.method, request.url.path, response.status_code, duration_ms)
    response.headers["X-Request-ID"] = req_id
    return response


# 允许客户端跨域（桌面客户端通过本地 HTTP 调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         # 桌面客户端无固定 Origin，放开
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-New-Token"],   # 允许客户端读取 token 刷新头
)

# ── 自动注册 Router ───────────────────────────────────────────────────────────
# Phase 5：先用 PluginLoader 加载插件路由，再 auto-scan 核心路由（跳过插件已接管的模块）

from backend.plugin_loader import PluginLoader as _PluginLoader

_plugin_loader = _PluginLoader()
_plugin_loader.discover()

# 收集所有插件声明的 OWNED_MODULES（这些模块由插件管理，不走 auto-scan）
_plugin_owned: set[str] = set()
for _plugin in _plugin_loader._plugins:
    _mod_path = _plugin.get("backend", {}).get("routers_module")
    if not _mod_path:
        continue
    try:
        _mod = importlib.import_module(_mod_path)
        if hasattr(_mod, "OWNED_MODULES"):
            _plugin_owned.update(_mod.OWNED_MODULES)
    except Exception as _e:
        _log.warning(f"Plugin module 预加载失败 [{_mod_path}]: {_e}")

# 加载插件路由
for _router in _plugin_loader.get_routers():
    app.include_router(_router)

# auto-scan backend/routers/*.py（跳过插件已接管的模块）
_routers_dir = Path(__file__).parent / "routers"
for _finder, _mod_name, _is_pkg in pkgutil.iter_modules([str(_routers_dir)]):
    if _is_pkg or _mod_name in _plugin_owned:
        continue
    try:
        _mod = importlib.import_module(f"backend.routers.{_mod_name}")
        if hasattr(_mod, "router"):
            app.include_router(_mod.router)
    except Exception as _e:
        _log.warning(f"Router 加载跳过 [backend.routers.{_mod_name}]: {_e}")
_log.info(f"✅ Router 自动注册完成（插件路由: {len(_plugin_loader.get_routers())} 个，跳过模块: {_plugin_owned}）")

# 静态文件：附件上传目录
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

_start_time = time.time()
_SLOW_MS = 2000  # 慢请求阈值（毫秒）

# ── 网页版：服务 Vite 构建产物 dist/ ──────────────────────────────────────────
_DIST_DIR = Path(__file__).parent.parent / "dist"
if _DIST_DIR.exists():
    # assets/ 子目录（JS/CSS bundle，带内容哈希，可长期缓存）
    _assets_dir = _DIST_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="dist_assets")

    # web/ 子目录（原始路径结构，页面内相对路径引用）
    _web_dist_dir = _DIST_DIR / "web"
    if _web_dist_dir.exists():
        app.mount("/web", StaticFiles(directory=str(_web_dist_dir), html=True), name="dist_web")

    # packages/ 子目录（插件页面）
    _pkg_dist_dir = _DIST_DIR / "packages"
    if _pkg_dist_dir.exists():
        app.mount("/packages", StaticFiles(directory=str(_pkg_dist_dir)), name="dist_packages")

    # SPA catch-all：把所有非 API 路径都指向主页 HTML
    _SPA_INDEX = _DIST_DIR / "web" / "index.html"

    @app.get("/config", tags=["system"], include_in_schema=False)
    def get_frontend_config():
        """前端获取自身配置（后端 URL、版本号等）。"""
        from backend.config import get_settings as _gs
        s = _gs()
        return {"backendUrl": getattr(s, "public_url", "") or ""}

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        # 已有路由优先，这里只处理未匹配的路径
        _skip = ("api/", "auth/", "static/", "assets/", "feishu/", "share/",
                 "bop/", "config", "health", "docs", "redoc", "openapi.json")
        if any(path.startswith(s) for s in _skip):
            raise HTTPException(status_code=404, detail="Not found")
        if _SPA_INDEX.exists():
            return FileResponse(str(_SPA_INDEX))
        raise HTTPException(status_code=404, detail="Frontend not built. Run: npm run build:web")


# ── 角色同步中间件 ─────────────────────────────────────────────────────────────
# 每次已认证请求完成后，比较 JWT 内的 system_role 与 DB 中的值。
# 若不一致（超管刚改了该用户角色），则重新签发 JWT 并附在 X-New-Token 响应头。
# Electron 主进程拦截此头并自动更新客户端 token，实现近实时权限刷新。

@app.middleware("http")
async def role_sync_middleware(request: Request, call_next):
    response = await call_next(request)

    token = request.headers.get("x-ai00-token") or request.headers.get("X-AI00-Token")
    if not token:
        return response

    try:
        from backend.services import jwt_service, user_service
        payload  = jwt_service.decode_unverified(token)
        jwt_role = payload.get("system_role")
        user_gid = payload.get("sub")
        if not user_gid or not jwt_role:
            return response

        user = await asyncio.get_event_loop().run_in_executor(
            None, user_service.get_by_gid, user_gid
        )
        if user and user["is_active"] and user["system_role"] != jwt_role:
            new_token = jwt_service.sign(
                user_gid=user["gid"],
                system_role=user["system_role"],
                org_role=user.get("org_role"),
                external_subtype=user.get("external_subtype"),
                team_id=user.get("team_id"),
                name=user.get("name", ""),
                email=user.get("email", ""),
                avatar_url=user.get("avatar_url", ""),
            )
            response.headers["X-New-Token"] = new_token
    except Exception:
        pass  # 不因刷新失败而影响正常响应

    return response
