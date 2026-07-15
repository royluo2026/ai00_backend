-- ═══════════════════════════════════════════════════════════════════════════════
-- AI00 数据库 Schema 迁移脚本 V1
-- 在 DBeaver 中对 ai00_dev 数据库执行一次
-- 执行前请确认已备份：docs/database/ai00_backup_20260512.sql
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 1：建 schema
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS proj;
CREATE SCHEMA IF NOT EXISTS bop;
CREATE SCHEMA IF NOT EXISTS factory;
CREATE SCHEMA IF NOT EXISTS template;
CREATE SCHEMA IF NOT EXISTS work;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS app;

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 2：移表（SET SCHEMA，保留数据和索引）
-- ─────────────────────────────────────────────────────────────────────────────

-- auth schema
ALTER TABLE IF EXISTS public.teams              SET SCHEMA auth;
ALTER TABLE IF EXISTS public.users              SET SCHEMA auth;
ALTER TABLE IF EXISTS public.project_members    SET SCHEMA auth;
ALTER TABLE IF EXISTS public.auth_pending       SET SCHEMA auth;
ALTER TABLE IF EXISTS public.bid_sections       SET SCHEMA auth;
ALTER TABLE IF EXISTS public.project_roles      SET SCHEMA auth;

-- proj schema
ALTER TABLE IF EXISTS public.projects           SET SCHEMA proj;
ALTER TABLE IF EXISTS public.vehicle_models     SET SCHEMA proj;
ALTER TABLE IF EXISTS public.collab_sessions    SET SCHEMA proj;
ALTER TABLE IF EXISTS public.approval_orders    SET SCHEMA proj;
ALTER TABLE IF EXISTS public.tasks              SET SCHEMA proj;
ALTER TABLE IF EXISTS public.issues             SET SCHEMA proj;
ALTER TABLE IF EXISTS public.task_templates     SET SCHEMA proj;
ALTER TABLE IF EXISTS public.task_template_items SET SCHEMA proj;

-- bop schema
ALTER TABLE IF EXISTS public.bop_versions           SET SCHEMA bop;
ALTER TABLE IF EXISTS public.bop_entries            SET SCHEMA bop;
ALTER TABLE IF EXISTS public.bop_entry_links        SET SCHEMA bop;
ALTER TABLE IF EXISTS public.asm_line_processes     SET SCHEMA bop;
ALTER TABLE IF EXISTS public.asm_station_processes  SET SCHEMA bop;
ALTER TABLE IF EXISTS public.asm_operator_processes SET SCHEMA bop;
ALTER TABLE IF EXISTS public.asm_operations         SET SCHEMA bop;
ALTER TABLE IF EXISTS public.project_equipment      SET SCHEMA bop;
ALTER TABLE IF EXISTS public.project_tooling        SET SCHEMA bop;
ALTER TABLE IF EXISTS public.project_tools          SET SCHEMA bop;
ALTER TABLE IF EXISTS public.project_floor_heights  SET SCHEMA bop;
ALTER TABLE IF EXISTS public.project_control_plans  SET SCHEMA bop;
ALTER TABLE IF EXISTS public.project_process_charts SET SCHEMA bop;
ALTER TABLE IF EXISTS public.project_jack_pos       SET SCHEMA bop;
ALTER TABLE IF EXISTS public.bom_snapshots          SET SCHEMA bop;
ALTER TABLE IF EXISTS public.part_entries           SET SCHEMA bop;
ALTER TABLE IF EXISTS public.part_model_instances   SET SCHEMA bop;

-- factory schema
ALTER TABLE IF EXISTS public.factories                SET SCHEMA factory;
ALTER TABLE IF EXISTS public.factory_sections         SET SCHEMA factory;
ALTER TABLE IF EXISTS public.factory_stations         SET SCHEMA factory;
ALTER TABLE IF EXISTS public.factory_layout_templates SET SCHEMA factory;
ALTER TABLE IF EXISTS public.physical_tools           SET SCHEMA factory;
ALTER TABLE IF EXISTS public.physical_equipments      SET SCHEMA factory;
ALTER TABLE IF EXISTS public.physical_fixtures        SET SCHEMA factory;

-- template schema
ALTER TABLE IF EXISTS public.std_operations       SET SCHEMA template;
ALTER TABLE IF EXISTS public.tool_templates       SET SCHEMA template;
ALTER TABLE IF EXISTS public.equipment_templates  SET SCHEMA template;
ALTER TABLE IF EXISTS public.fixture_templates    SET SCHEMA template;
ALTER TABLE IF EXISTS public.standard_fasteners   SET SCHEMA template;
ALTER TABLE IF EXISTS public.standard_part_names  SET SCHEMA template;

-- work schema
ALTER TABLE IF EXISTS public.lists                SET SCHEMA work;
ALTER TABLE IF EXISTS public.item_entries         SET SCHEMA work;
ALTER TABLE IF EXISTS public.follows              SET SCHEMA work;
ALTER TABLE IF EXISTS public.notifications        SET SCHEMA work;

-- knowledge schema
ALTER TABLE IF EXISTS public.knowledge_entries    SET SCHEMA knowledge;
ALTER TABLE IF EXISTS public.knowledge_folders    SET SCHEMA knowledge;
ALTER TABLE IF EXISTS public.knowledge_items      SET SCHEMA knowledge;
ALTER TABLE IF EXISTS public.knowledge_favorites  SET SCHEMA knowledge;
ALTER TABLE IF EXISTS public.knowledge_recent     SET SCHEMA knowledge;

-- app schema
ALTER TABLE IF EXISTS public.view_configs                SET SCHEMA app;
ALTER TABLE IF EXISTS public.export_templates            SET SCHEMA app;
ALTER TABLE IF EXISTS public.workbench_configs           SET SCHEMA app;
ALTER TABLE IF EXISTS public.workbench_member_overrides  SET SCHEMA app;
ALTER TABLE IF EXISTS public.system_config               SET SCHEMA app;
ALTER TABLE IF EXISTS public.flows                       SET SCHEMA app;
ALTER TABLE IF EXISTS public.flow_runs                   SET SCHEMA app;
ALTER TABLE IF EXISTS public.wb_annotations              SET SCHEMA app;
ALTER TABLE IF EXISTS public.bug_tracker_snapshots       SET SCHEMA app;

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 3：重命名（已移入目标 schema，在此执行 RENAME）
-- ─────────────────────────────────────────────────────────────────────────────

-- auth
ALTER TABLE IF EXISTS auth.project_roles            RENAME TO section_owners;

-- bop
ALTER TABLE IF EXISTS bop.asm_line_processes        RENAME TO bop_line;
ALTER TABLE IF EXISTS bop.asm_station_processes     RENAME TO bop_station;
ALTER TABLE IF EXISTS bop.asm_operator_processes    RENAME TO bop_operator;
ALTER TABLE IF EXISTS bop.asm_operations            RENAME TO bop_steps;
ALTER TABLE IF EXISTS bop.project_equipment         RENAME TO bop_equipments;
ALTER TABLE IF EXISTS bop.project_tooling           RENAME TO bop_fixtures;
ALTER TABLE IF EXISTS bop.project_tools             RENAME TO bop_tools;
ALTER TABLE IF EXISTS bop.project_floor_heights     RENAME TO bop_floor_height;
ALTER TABLE IF EXISTS bop.project_control_plans     RENAME TO bop_control_plan;
ALTER TABLE IF EXISTS bop.project_process_charts    RENAME TO bop_process_charts;
ALTER TABLE IF EXISTS bop.project_jack_pos          RENAME TO bop_jack_pos;
ALTER TABLE IF EXISTS bop.bom_snapshots             RENAME TO pbom_versions;
ALTER TABLE IF EXISTS bop.part_entries              RENAME TO pbom;
ALTER TABLE IF EXISTS bop.part_model_instances      RENAME TO cad_model_instances;

-- factory
ALTER TABLE IF EXISTS factory.physical_tools        RENAME TO factory_tools;
ALTER TABLE IF EXISTS factory.physical_equipments   RENAME TO factory_equipments;
ALTER TABLE IF EXISTS factory.physical_fixtures     RENAME TO factory_fixtures;

-- template
ALTER TABLE IF EXISTS template.std_operations       RENAME TO gbop;
ALTER TABLE IF EXISTS template.tool_templates       RENAME TO vpps_tools;
ALTER TABLE IF EXISTS template.equipment_templates  RENAME TO vpps_equipments;
ALTER TABLE IF EXISTS template.fixture_templates    RENAME TO vpps_fixtures;
ALTER TABLE IF EXISTS template.standard_fasteners   RENAME TO fastener_spec;
ALTER TABLE IF EXISTS template.standard_part_names  RENAME TO vpps_parts;

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 4：新建表 bop.bop_process（工序实体，node_type='process'）
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bop.bop_process (
    gid             TEXT        PRIMARY KEY,
    project_gid     TEXT        NOT NULL,
    bop_version_gid TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    process_code    TEXT,
    standard_time   NUMERIC(10,2),
    version_no      TEXT        NOT NULL DEFAULT '01',
    vpps            TEXT,
    vpps_desc       TEXT,
    params          JSONB       NOT NULL DEFAULT '{}',
    source_type     TEXT,
    source_ref_gid  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT
);
CREATE INDEX IF NOT EXISTS idx_bop_process_proj    ON bop.bop_process(project_gid);
CREATE INDEX IF NOT EXISTS idx_bop_process_version ON bop.bop_process(bop_version_gid);

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 5：删除 V1 废弃表（public schema 中的旧表）
-- 注意：bop_steps（V1 旧表）已在步骤 3 中被 asm_operations 重命名为 bop.bop_steps 占用，
--       此处 DROP 的是 public.bop_steps（V1 旧版工步表），IF NOT EXISTS 安全跳过。
--       以下表由 bop_schema_v2.sql 在目标 schema 中直接创建（如 bop.asm_steps、
--       factory.factory_lines、knowledge.craft_rules），public 中的旧表无数据，直接删除。
-- ─────────────────────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS public.work_plans CASCADE;
DROP TABLE IF EXISTS public.sections CASCADE;
DROP TABLE IF EXISTS public.operation_flat CASCADE;
DROP TABLE IF EXISTS public.bop_posts CASCADE;
DROP TABLE IF EXISTS public.bop_operations CASCADE;
DROP TABLE IF EXISTS public.bop_steps CASCADE;
DROP TABLE IF EXISTS public.operation_resources CASCADE;
DROP TABLE IF EXISTS public.step_resources CASCADE;
DROP TABLE IF EXISTS public.asm_steps CASCADE;
DROP TABLE IF EXISTS public.bop_fork_presets CASCADE;
DROP TABLE IF EXISTS public.canvas_bop_layers CASCADE;
DROP TABLE IF EXISTS public.factory_lines CASCADE;
DROP TABLE IF EXISTS public.craft_rules CASCADE;
DROP TABLE IF EXISTS public.rules CASCADE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 6：为 display 序列设置搜索路径（序列不会随表自动迁移 schema）
-- ─────────────────────────────────────────────────────────────────────────────

ALTER SEQUENCE IF EXISTS public.tasks_display_seq      SET SCHEMA proj;
ALTER SEQUENCE IF EXISTS public.issues_display_seq     SET SCHEMA proj;
ALTER SEQUENCE IF EXISTS public.std_op_display_seq     SET SCHEMA template;
ALTER SEQUENCE IF EXISTS public.knowledge_display_seq  SET SCHEMA knowledge;
ALTER SEQUENCE IF EXISTS public.rules_display_seq      SET SCHEMA knowledge;

-- 验证查询（执行后在结果中确认所有表已在正确 schema）：
-- SELECT schemaname, tablename
-- FROM pg_tables
-- WHERE schemaname NOT IN ('pg_catalog','information_schema')
-- ORDER BY schemaname, tablename;

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 7：为重命名后的 template 表补充新增列
-- （旧表只有基础列，schema.sql 新定义的列不会自动出现）
-- ─────────────────────────────────────────────────────────────────────────────

-- template.gbop（原 std_operations）— 已被步骤8 DROP+重建为 gbop_versions/gbop_entries，
-- 以下 ALTER 仅在步骤8执行前兼容旧表，步骤8执行后这些语句会静默跳过（表已不存在）
-- ALTER TABLE template.gbop ... （已废弃，见步骤8）

-- template.vpps_tools（原 tool_templates）
ALTER TABLE template.vpps_tools ADD COLUMN category TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE template.vpps_tools ADD COLUMN spec JSONB NOT NULL DEFAULT '{}';
ALTER TABLE template.vpps_tools ADD COLUMN team_id TEXT;
ALTER TABLE template.vpps_tools ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();

-- template.vpps_equipments（原 equipment_templates）
ALTER TABLE template.vpps_equipments ADD COLUMN category TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_equipments ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE template.vpps_equipments ADD COLUMN spec JSONB NOT NULL DEFAULT '{}';
ALTER TABLE template.vpps_equipments ADD COLUMN team_id TEXT;
ALTER TABLE template.vpps_equipments ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();

-- template.vpps_fixtures（原 fixture_templates）
ALTER TABLE template.vpps_fixtures ADD COLUMN category TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_fixtures ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE template.vpps_fixtures ADD COLUMN spec JSONB NOT NULL DEFAULT '{}';
ALTER TABLE template.vpps_fixtures ADD COLUMN team_id TEXT;
ALTER TABLE template.vpps_fixtures ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();

-- template.vpps_parts（原 standard_part_names）
ALTER TABLE template.vpps_parts ADD COLUMN standard_name TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN part_category TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN level TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN vpps_desc_cn TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN vpps TEXT;
ALTER TABLE template.vpps_parts ADD COLUMN importance TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN vehicle_model TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE template.vpps_parts ADD COLUMN meta JSONB NOT NULL DEFAULT '{}';
ALTER TABLE template.vpps_parts ADD COLUMN team_id TEXT;
ALTER TABLE template.vpps_parts ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE template.vpps_parts ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_vpps_parts_vpps ON template.vpps_parts(vpps) WHERE vpps IS NOT NULL;
-- 字段重命名：standard_name → vpps_description
ALTER TABLE template.vpps_parts RENAME COLUMN standard_name TO vpps_description;

-- ─────────────────────────────────────────────────────────────────────────────
-- template.vpps_tools 扩展列（拧紧工具详细规格）
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE template.vpps_tools ADD COLUMN vpps               TEXT;
ALTER TABLE template.vpps_tools ADD COLUMN gun_model          TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN matou_part_no      TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN importance         TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN gun_type           TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN wireless           TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN output_square      TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN torque_min         TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN torque_recommended TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN cad_model_no       TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN socket_model       TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN fastener_type      TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN fastener_params    TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN extension_model    TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN socket_cad_no      TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_tools ADD COLUMN extension_cad_no   TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_vpps_tools_vpps ON template.vpps_tools(vpps) WHERE vpps IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- template.fastener_spec 扩展列（紧固件详细规格）
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE template.fastener_spec ADD COLUMN fastener_type   TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN thread_spec     TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN model           TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN shank_length    TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN guide_type      TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN guide_length    TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN has_adhesive    TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN drive_size      TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN flange_diameter TEXT NOT NULL DEFAULT '';
ALTER TABLE template.fastener_spec ADD COLUMN first_vehicle   TEXT NOT NULL DEFAULT '';
-- 移除旧 UNIQUE 约束（part_no 不再唯一，同零件号可有不同规格）
ALTER TABLE template.fastener_spec DROP CONSTRAINT IF EXISTS fastener_spec_part_no_key;

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 8：GBOP V2 树形结构（删除旧扁平表，新建版本+条目两张表）
-- ─────────────────────────────────────────────────────────────────────────────

-- 删除旧扁平表及序列
DROP TABLE IF EXISTS template.gbop CASCADE;
DROP SEQUENCE IF EXISTS template.std_op_display_seq;

-- GBOP 版本管理
CREATE TABLE IF NOT EXISTS template.gbop_versions (
    gid                TEXT PRIMARY KEY,
    name               TEXT NOT NULL DEFAULT '',
    version_family_gid TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'draft',
    frozen_at          TIMESTAMPTZ,
    archived_at        TIMESTAMPTZ,
    vehicle_model      TEXT NOT NULL DEFAULT '',
    team_id            TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    created_by         TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- GBOP 树形节点
CREATE TABLE IF NOT EXISTS template.gbop_entries (
    gid                TEXT PRIMARY KEY,
    version_gid        TEXT NOT NULL REFERENCES template.gbop_versions(gid) ON DELETE CASCADE,
    parent_gid         TEXT REFERENCES template.gbop_entries(gid) ON DELETE SET NULL,
    level              SMALLINT NOT NULL DEFAULT 0,
    node_type          TEXT NOT NULL DEFAULT 'process',
    seq_no             REAL NOT NULL DEFAULT 0,
    vpps               TEXT,
    vpps_desc          TEXT NOT NULL DEFAULT '',
    vpps_attr          TEXT NOT NULL DEFAULT '',
    importance         TEXT NOT NULL DEFAULT '',
    torque_importance  TEXT NOT NULL DEFAULT '',
    vehicle_model      TEXT NOT NULL DEFAULT '',
    parent_vpps        TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'active',
    sort_order         REAL NOT NULL DEFAULT 0,
    standard_time      REAL,
    op_code            TEXT NOT NULL DEFAULT '',
    op_name            TEXT NOT NULL DEFAULT '',
    description        TEXT NOT NULL DEFAULT '',
    steps              JSONB NOT NULL DEFAULT '[]',
    required_tools     JSONB NOT NULL DEFAULT '[]',
    parameters         JSONB NOT NULL DEFAULT '{}',
    meta               JSONB NOT NULL DEFAULT '{}',
    team_id            TEXT,
    created_by         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gbop_entries_version ON template.gbop_entries(version_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_entries_parent  ON template.gbop_entries(parent_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_entries_vpps    ON template.gbop_entries(vpps) WHERE vpps IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 步骤 9：GBOP V3 — 独立工艺/操作实体表 + entry_links
-- ─────────────────────────────────────────────────────────────────────────────

-- 从 gbop_entries 移除 L4/L5 专属字段（这些字段已移入独立实体表）
ALTER TABLE template.gbop_entries DROP COLUMN IF EXISTS standard_time;
ALTER TABLE template.gbop_entries DROP COLUMN IF EXISTS op_code;
ALTER TABLE template.gbop_entries DROP COLUMN IF EXISTS op_name;
ALTER TABLE template.gbop_entries DROP COLUMN IF EXISTS description;
ALTER TABLE template.gbop_entries DROP COLUMN IF EXISTS steps;
ALTER TABLE template.gbop_entries DROP COLUMN IF EXISTS required_tools;
ALTER TABLE template.gbop_entries DROP COLUMN IF EXISTS parameters;

-- GBOP 工艺卡片（L4 总装工艺独立实体）
CREATE TABLE IF NOT EXISTS template.gbop_processes (
    gid             TEXT PRIMARY KEY,
    version_gid     TEXT NOT NULL REFERENCES template.gbop_versions(gid) ON DELETE CASCADE,
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
);
CREATE INDEX IF NOT EXISTS idx_gbop_processes_version ON template.gbop_processes(version_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_processes_vpps ON template.gbop_processes(vpps) WHERE vpps IS NOT NULL;

-- GBOP 操作卡片（L5 总装操作独立实体）
CREATE TABLE IF NOT EXISTS template.gbop_operations (
    gid             TEXT PRIMARY KEY,
    version_gid     TEXT NOT NULL REFERENCES template.gbop_versions(gid) ON DELETE CASCADE,
    process_gid     TEXT REFERENCES template.gbop_processes(gid) ON DELETE SET NULL,
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
);
CREATE INDEX IF NOT EXISTS idx_gbop_operations_version ON template.gbop_operations(version_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_operations_process ON template.gbop_operations(process_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_operations_vpps ON template.gbop_operations(vpps) WHERE vpps IS NOT NULL;

-- GBOP 节点-实体联结表
CREATE TABLE IF NOT EXISTS template.gbop_entry_links (
    gid             TEXT PRIMARY KEY,
    entry_gid       TEXT NOT NULL REFERENCES template.gbop_entries(gid) ON DELETE CASCADE,
    link_type       TEXT NOT NULL,         -- 'gbop_process' | 'gbop_operation'
    ref_gid         TEXT NOT NULL,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    UNIQUE (entry_gid, link_type, ref_gid)
);
CREATE INDEX IF NOT EXISTS idx_gbop_entry_links_entry ON template.gbop_entry_links(entry_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_entry_links_ref ON template.gbop_entry_links(ref_gid);
