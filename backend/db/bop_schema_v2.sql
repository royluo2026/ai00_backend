-- ═══════════════════════════════════════════════════════════════════
-- 工艺规划域 BOP V2 建表脚本（PostgreSQL）
-- 文件：backend/db/bop_schema_v2.sql
--
-- 执行方式：在 DBeaver 对 ai00_dev 数据库执行，部署时在 schema.sql 之后执行
--
-- 本脚本做三件事：
--   A. DROP 被新设计取代的旧表（bop_posts/operations/steps 等）
--   B. 新建工艺规划域所有新表
--   C. 新建知识库和规则的云端 PG 表（原来只有本地 SQLite）
-- ═══════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema 声明（新建数据库时自动创建，已有数据库用 migration_schema_v1.sql 迁移）
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS proj;
CREATE SCHEMA IF NOT EXISTS bop;
CREATE SCHEMA IF NOT EXISTS factory;
CREATE SCHEMA IF NOT EXISTS template;
CREATE SCHEMA IF NOT EXISTS work;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS app;

-- ───────────────────────────────────────────────────────────────────
-- A. 清理被新设计取代的旧表
-- ───────────────────────────────────────────────────────────────────
-- CASCADE 会同时移除引用这些表的外键约束（不会删除引用方的表本身）

-- 旧版工步资源绑定（由 bop_entries 中的 tool_req/tooling_req/equipment_req 节点取代）
DROP TABLE IF EXISTS step_resources CASCADE;

-- 旧版工序资源绑定（同上）
DROP TABLE IF EXISTS operation_resources CASCADE;

-- 旧版工步（由 bop_entries + asm_steps 取代）
DROP TABLE IF EXISTS bop_steps CASCADE;

-- 旧版工序（由 bop_entries + asm_operations 取代）
DROP TABLE IF EXISTS bop_operations CASCADE;

-- 旧版岗位（由 bop_entries 中的 role_req/role_ref 节点取代）
DROP TABLE IF EXISTS bop_posts CASCADE;

-- 更旧的工艺规划表（work_plans 三层结构，由 bop_versions + bop_entries 取代）
-- 注意：collab_sessions.section_gid 的 FK 约束会被 CASCADE 自动移除，
--       collab_sessions 表本身不受影响，section_gid 列变为普通字段。
DROP TABLE IF EXISTS operation_flat CASCADE;
DROP TABLE IF EXISTS sections CASCADE;
DROP TABLE IF EXISTS work_plans CASCADE;


-- ───────────────────────────────────────────────────────────────────
-- B-0. 基础表：bop.bop_versions（首次部署时建表；已有则追加缺失字段）
-- ───────────────────────────────────────────────────────────────────
--
-- factory_gid 存工厂资源库 gid（TEXT，无 FK，工厂资源域独立建表）
-- 本表是整个 BOP 树的版本锚点，所有 bop_entries 行都挂在某个版本下。

CREATE TABLE IF NOT EXISTS bop.bop_versions (
  gid               TEXT        PRIMARY KEY,
  project_gid       TEXT        REFERENCES proj.projects(gid) ON DELETE SET NULL,
  factory_gid       TEXT,                          -- 工厂资源域 gid（跨域引用，无 FK）
  vehicle_model_gid TEXT        REFERENCES proj.vehicle_models(gid) ON DELETE SET NULL,
  version_tag       TEXT        NOT NULL DEFAULT '',
  version_no        TEXT,                          -- 人读版本号，如 'V01'
  base_version_gid  TEXT,                          -- fork 来源版本 gid（自引用，无 FK）
  maturity          TEXT        NOT NULL DEFAULT 'concept',  -- concept|pre_series|production
  takt_time         REAL        NOT NULL DEFAULT 60,
  status            TEXT        NOT NULL DEFAULT 'active',   -- active|baseline|M|archived
  description       TEXT,
  created_by        TEXT,
  meta              JSONB       NOT NULL DEFAULT '{}',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bop_versions_project ON bop.bop_versions(project_gid);

-- 若 bop.bop_versions 已存在（旧库升级），幂等追加新字段
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS version_no       TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS base_version_gid TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS description      TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS created_by       TEXT;
UPDATE bop.bop_versions SET version_no = version_tag WHERE version_no IS NULL;

-- proj.projects：追加项目类型（取值: 'active'|'gbop'|'history'）
ALTER TABLE proj.projects
  ADD COLUMN IF NOT EXISTS project_type TEXT NOT NULL DEFAULT 'active';

-- work.tasks/work.issues：附件字段（幂等）
ALTER TABLE work.tasks  ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]';
ALTER TABLE work.issues ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]';


-- ───────────────────────────────────────────────────────────────────
-- B-1. BOP 条目骨架树（全新核心表）
-- ───────────────────────────────────────────────────────────────────
--
-- 每一行 = BOP 树上的一个节点。node_type 决定含义，ref_gid 指向详情表。
-- 支持任意层级深度，所有节点类型（工位工艺/工序/工步/零件/设备/工装等）统一在此表。
--
-- node_type 合法值（对照 docs/bop/db csv ui.xlsx，AI00_Level 分级）：
--   factory_bop      L0  总装工厂BOP
--   line_process     L1  总装线体工艺
--   station_process  L2  总装工位工艺
--   operator_process L3  总装岗位工艺
--   man              L4  人
--   station_factory  L4  工位
--   process          L4  总装工序
--   equipment_factory L5 设备（现有）
--   tool_factory     L5  工具（现有）
--   equipment_need   L5  设备（需求）
--   fixture_factory  L5  工装（现有）
--   operation        L5  总装操作（Product）
--   issue            L5  问题
--   standard_task    L5  标准任务
--   non_standard_task L5 非标任务
--   contral_plan     L5  控制计划
--   process_chart    L5  工艺卡
--   knowledge        L5  知识（level NULL）
--   rule             L5  规则（level NULL）
--   part             L6  零部件
--   non_standard_part L6 非标件
--   standard_part    L6  标准件
--   support_material L6  辅料
--   tool_need        L6  工具（需求）
--   fixture_need     L6  工装（需求）

CREATE TABLE IF NOT EXISTS bop.bop_entries (
  gid                TEXT        PRIMARY KEY,
  bop_version_gid    TEXT        NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
  seq_no             REAL        NOT NULL DEFAULT 0,    -- 同父级下显示排序（REAL 允许浮点差值实现拖拽插入）

  level              SMALLINT    NOT NULL,              -- CSV 原始树深度
  ai00_level         SMALLINT,                          -- AI00 逻辑分级（由 node_type 对照表决定）
  node_type          TEXT        NOT NULL,

  -- 节点主字段
  title              TEXT,                              -- 零组件名称（CSV col4）
  bom_row_id         TEXT,                              -- 零组件ID，如 "AS-000477735"（CSV col3）
  bom_row_label      TEXT,                              -- 完整BOM行，如 "AS-000477735/01;1-X11-BOP (视图)"（CSV col1）
  bom_row_owner      TEXT,                              -- 零组件版本所有权用户（CSV col6）

  -- VPPS（工程师指定的跨版本稳定壳标识）
  vpps               TEXT,                              -- VPPS 壳
  vpps_desc          TEXT,                              -- VPPS 描述

  -- 树结构
  parent_bop_gid     TEXT        REFERENCES bop.bop_entries(gid) ON DELETE SET NULL,
  parent_bop_label   TEXT,                              -- 父级BOM行原文（CSV col5），用于溯源/展示

  -- 外部实体关联统一走 bop_entry_links（is_primary=true 标识身份实体，无需在此存 ref_gid）

  -- 溯源（跨项目 DiffManager 对比的稳定锚点）
  gbop_source_gid    TEXT,       -- GBOP 项目的 bop_entries.gid
  history_source_gid TEXT,       -- 历史项目的 bop_entries.gid

  owner_gid          TEXT,       -- 负责人 user gid（系统内）

  deleted_at         TIMESTAMPTZ,
  archived_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by         TEXT
);

-- 若 bop.bop_entries 已存在（旧库升级），幂等追加/迁移字段
-- 新增字段
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS title              TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS bom_row_owner      TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS parent_bop_label   TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS ai00_level         SMALLINT;
-- bom_row_id 语义变更：旧值存的是 meta.code（零件号），新语义同；保留数据，无需迁移
-- 删除字段（已有库需手动执行，新库 CREATE TABLE 不含这些列）
-- ALTER TABLE bop.bop_entries DROP COLUMN IF EXISTS bom_row_ver;
-- ALTER TABLE bop.bop_entries DROP COLUMN IF EXISTS meta;
-- （meta 建议在数据确认迁移完成后再删，暂时保留）
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_bop_ent_version
  ON bop.bop_entries(bop_version_gid) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bop_ent_parent
  ON bop.bop_entries(parent_bop_gid) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bop_ent_version_level
  ON bop.bop_entries(bop_version_gid, level) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bop_ent_version_type
  ON bop.bop_entries(bop_version_gid, node_type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bop_ent_gbop_source
  ON bop.bop_entries(gbop_source_gid) WHERE gbop_source_gid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bop_ent_bom_row_id
  ON bop.bop_entries(bom_row_id) WHERE bom_row_id IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- B-2. 线体工艺详情（node_type = line_process）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_line (
  gid                  TEXT        PRIMARY KEY,
  project_gid          TEXT        NOT NULL,
  name                 TEXT        NOT NULL,
  version_no           TEXT        NOT NULL DEFAULT '01',
  factory_line_ref_gid TEXT,               -- 复制来源：工厂资源线体 gid
  owner_gid            TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by           TEXT
);
CREATE INDEX IF NOT EXISTS idx_asm_line_proc_proj ON bop.bop_line(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- B-3. 工位工艺详情（node_type = station_process）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_station (
  gid                     TEXT        PRIMARY KEY,
  project_gid             TEXT        NOT NULL,
  name                    TEXT        NOT NULL,
  version_no              TEXT        NOT NULL DEFAULT '01',
  factory_station_ref_gid TEXT,              -- 复制来源：工厂资源工位 gid
  owner_gid               TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by              TEXT
);
CREATE INDEX IF NOT EXISTS idx_asm_station_proc_proj ON bop.bop_station(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- B-2b. 工序实体（node_type = process）— 新增
-- ───────────────────────────────────────────────────────────────────
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


-- ───────────────────────────────────────────────────────────────────
-- B-4. 工序详情（node_type = operation）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_steps (
  gid              TEXT           PRIMARY KEY,
  project_gid      TEXT           NOT NULL,
  name             TEXT           NOT NULL,
  operation_code   TEXT,
  version_no       TEXT           NOT NULL DEFAULT '01',
  station_height   NUMERIC(7,2),              -- 工位高度 mm
  op_req_height    NUMERIC(7,2),              -- 操作需求高度 mm
  vpps             TEXT,
  vpps_desc        TEXT,
  params           JSONB          NOT NULL DEFAULT '{}',  -- 工序扩展属性及参数
  source_type      TEXT,          -- 'gbop'|'history_project'|'manual'|'tc_import'
  source_ref_gid   TEXT,          -- 溯源 gid
  created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
  created_by       TEXT
);
CREATE INDEX IF NOT EXISTS idx_asm_op_proj   ON bop.bop_steps(project_gid);
CREATE INDEX IF NOT EXISTS idx_asm_op_code   ON bop.bop_steps(operation_code) WHERE operation_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_asm_op_source ON bop.bop_steps(source_ref_gid)  WHERE source_ref_gid IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- B-5. 工步详情（node_type = step）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.asm_steps (
  gid              TEXT        PRIMARY KEY,
  project_gid      TEXT        NOT NULL,
  name             TEXT        NOT NULL,
  step_code        TEXT,
  version_no       TEXT        NOT NULL DEFAULT '01',
  source_type      TEXT,
  source_ref_gid   TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by       TEXT
);
CREATE INDEX IF NOT EXISTS idx_asm_step_proj   ON bop.asm_steps(project_gid);
CREATE INDEX IF NOT EXISTS idx_asm_step_source ON bop.asm_steps(source_ref_gid) WHERE source_ref_gid IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- B-6. 项目设备需求（node_type = equipment_req）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_equipments (
  gid                   TEXT        PRIMARY KEY,
  project_gid           TEXT        NOT NULL,
  name                  TEXT        NOT NULL,
  version_no            TEXT        NOT NULL DEFAULT '01',
  factory_equip_ref_gid TEXT,
  spec                  TEXT,
  quantity              INTEGER     NOT NULL DEFAULT 1,
  status                TEXT        NOT NULL DEFAULT 'pending',  -- pending|confirmed|in_use|cancelled
  owner_gid             TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by            TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_equip_proj ON bop.bop_equipments(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- B-7. 项目工装需求（node_type = tooling_req）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_fixtures (
  gid                     TEXT        PRIMARY KEY,
  project_gid             TEXT        NOT NULL,
  name                    TEXT        NOT NULL,
  version_no              TEXT        NOT NULL DEFAULT '01',
  factory_tooling_ref_gid TEXT,
  spec                    TEXT,
  quantity                INTEGER     NOT NULL DEFAULT 1,
  status                  TEXT        NOT NULL DEFAULT 'pending',
  owner_gid               TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by              TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_tooling_proj ON bop.bop_fixtures(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- B-8. 项目工具需求（node_type = tool_req）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_tools (
  gid                   TEXT        PRIMARY KEY,
  project_gid           TEXT        NOT NULL,
  name                  TEXT        NOT NULL,
  version_no            TEXT        NOT NULL DEFAULT '01',
  factory_tool_ref_gid  TEXT,
  spec                  TEXT,
  quantity              INTEGER     NOT NULL DEFAULT 1,
  status                TEXT        NOT NULL DEFAULT 'pending',
  owner_gid             TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by            TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_tools_proj ON bop.bop_tools(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- B-9. 项目岗位需求（node_type = role_req）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.project_roles (
  gid                   TEXT        PRIMARY KEY,
  project_gid           TEXT        NOT NULL,
  name                  TEXT        NOT NULL,
  version_no            TEXT        NOT NULL DEFAULT '01',
  factory_role_ref_gid  TEXT,
  role_type             TEXT,
  headcount             INTEGER     NOT NULL DEFAULT 1,
  owner_gid             TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by            TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_roles_proj ON bop.project_roles(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- B-10. BOP 条目关联（工序/工步 ↔ 任务/问题/知识/规则）— 云端版
-- ───────────────────────────────────────────────────────────────────
--
-- 存储云端可见的关联，随 BOP 版本同步，团队成员均可查看。
-- 本地私人关联（本地 tasks/issues/knowledge/rules）存在 SQLite 的 bop_local_links。
--
-- link_type 合法值：
--   'issue'           本项目云端问题（work.issues.gid）
--   'issue_history'   历史问题，来自 GBOP 继承（work.issues.gid）
--   'task_std'        标准任务，从模板实例化（work.tasks.gid）
--   'task_custom'     本项目自定义任务（work.tasks.gid）
--   'knowledge'       知识条目（knowledge.knowledge_entries.gid）
--   'rule_std'        标准规则（knowledge.craft_rules.gid，share_scope=team/global）
--   'rule_custom'     本项目专用规则（knowledge.craft_rules.gid，share_scope=project）

CREATE TABLE IF NOT EXISTS bop.bop_entry_links (
  gid             TEXT        PRIMARY KEY,
  bop_entry_gid   TEXT        NOT NULL REFERENCES bop.bop_entries(gid) ON DELETE CASCADE,
  link_type       TEXT        NOT NULL,
  ref_gid         TEXT        NOT NULL,
  is_primary      BOOLEAN     NOT NULL DEFAULT FALSE,  -- TRUE = 该实体是本节点的"身份实体"（方式一语义）
  is_inherited    BOOLEAN     NOT NULL DEFAULT FALSE,
  gbop_source_gid TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by      TEXT,
  UNIQUE (bop_entry_gid, link_type, ref_gid)
);
CREATE INDEX IF NOT EXISTS idx_bop_links_entry   ON bop.bop_entry_links(bop_entry_gid);
CREATE INDEX IF NOT EXISTS idx_bop_links_ref     ON bop.bop_entry_links(ref_gid, link_type);
CREATE INDEX IF NOT EXISTS idx_bop_links_type    ON bop.bop_entry_links(link_type);

-- 现有表幂等追加（已有 bop_entry_links 的库）——必须在 WHERE is_primary 索引之前执行
ALTER TABLE bop.bop_entry_links ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_bop_links_primary ON bop.bop_entry_links(bop_entry_gid) WHERE is_primary = TRUE;
-- CTE 聚合优化：GROUP BY entry_gid WHERE version_gid = %s
CREATE INDEX IF NOT EXISTS idx_bop_links_version ON bop.bop_entry_links(version_gid);

-- 彻底移除 bop.bop_entries 上的 ref_gid / ref_source（统一走 bop.bop_entry_links）
ALTER TABLE bop.bop_entries DROP COLUMN IF EXISTS ref_gid;
ALTER TABLE bop.bop_entries DROP COLUMN IF EXISTS ref_source;


-- ───────────────────────────────────────────────────────────────────
-- B-11. 画布多项目叠加配置
-- ───────────────────────────────────────────────────────────────────
--
-- 同一车间可叠加多个项目的 BOP 版本进行对比。
-- is_base=TRUE 的层的线体/工位作为物理布局锚点（同 canvas 唯一）。

CREATE TABLE IF NOT EXISTS bop.canvas_bop_layers (
  gid              TEXT        PRIMARY KEY,
  canvas_gid       TEXT        NOT NULL,
  bop_version_gid  TEXT        NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
  project_gid      TEXT        NOT NULL,
  layer_color      TEXT,
  display_order    INTEGER     NOT NULL DEFAULT 0,
  is_base          BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (canvas_gid, bop_version_gid)
);
CREATE INDEX IF NOT EXISTS idx_canvas_layers_canvas  ON bop.canvas_bop_layers(canvas_gid);
CREATE INDEX IF NOT EXISTS idx_canvas_layers_version ON bop.canvas_bop_layers(bop_version_gid);


-- ───────────────────────────────────────────────────────────────────
-- C-1. 知识条目 — 云端 PG 版（原只有本地 SQLite）
-- ───────────────────────────────────────────────────────────────────
-- 字段与 SQLite knowledge_entries 保持一致（local ↔ cloud 双向同步基础）

-- display_id 序列（K-00000001 / R-00000001）
CREATE SEQUENCE IF NOT EXISTS knowledge.knowledge_display_seq START 1;
CREATE SEQUENCE IF NOT EXISTS knowledge.rules_display_seq     START 1;

CREATE TABLE IF NOT EXISTS knowledge.knowledge_entries (
  gid                    TEXT        PRIMARY KEY,
  display_id             TEXT        NOT NULL DEFAULT '',  -- 人类可读 ID，如 K-00000001
  title                  TEXT        NOT NULL DEFAULT '',
  entry_type             TEXT        NOT NULL DEFAULT 'guide',
  -- rule_basis | sim_spec | lesson_learned | guide
  content_md             TEXT        NOT NULL DEFAULT '',
  content_ref            JSONB       NOT NULL DEFAULT '{}',
  related_part_nos       JSONB       NOT NULL DEFAULT '[]',
  related_operation_gids JSONB       NOT NULL DEFAULT '[]',
  tags                   JSONB       NOT NULL DEFAULT '[]',
  source_project_gid     TEXT        REFERENCES proj.projects(gid) ON DELETE SET NULL,
  creator_gid            TEXT        REFERENCES auth.users(gid) ON DELETE SET NULL,
  status                 TEXT        NOT NULL DEFAULT 'draft',   -- draft | published
  share_scope            TEXT        NOT NULL DEFAULT 'team',    -- local|project|team|global
  list_gid               TEXT        DEFAULT NULL,
  source_gid             TEXT        DEFAULT NULL,               -- 来源 task/issue gid
  source_label           TEXT        NOT NULL DEFAULT '',
  maintainer_gid         TEXT        REFERENCES auth.users(gid) ON DELETE SET NULL,
  contributors           JSONB       NOT NULL DEFAULT '[]',
  attachments            JSONB       NOT NULL DEFAULT '[]',
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_project    ON knowledge.knowledge_entries(source_project_gid);
CREATE INDEX IF NOT EXISTS idx_knowledge_status     ON knowledge.knowledge_entries(status);
CREATE INDEX IF NOT EXISTS idx_knowledge_scope      ON knowledge.knowledge_entries(share_scope);
CREATE INDEX IF NOT EXISTS idx_knowledge_list       ON knowledge.knowledge_entries(list_gid) WHERE list_gid IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- C-2. 规则条目 — 云端 PG 版（原只有本地 SQLite）
-- ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS knowledge.craft_rules (
  gid                  TEXT        PRIMARY KEY,
  display_id           TEXT        NOT NULL DEFAULT '',  -- 人类可读 ID，如 R-00000001
  code                 TEXT        NOT NULL DEFAULT '',
  name                 TEXT        NOT NULL DEFAULT '',
  rule_type            TEXT        NOT NULL DEFAULT 'other',
  -- sequence | constraint | time_limit | other
  enforcement_level    TEXT        NOT NULL DEFAULT 'advisory',  -- mandatory | advisory
  rule_definition      JSONB       NOT NULL DEFAULT '{}',
  applicable_scope     JSONB       NOT NULL DEFAULT '{}',
  status               TEXT        NOT NULL DEFAULT 'draft',
  -- draft | testing | active | suspended | obsolete
  knowledge_source_gid TEXT        DEFAULT NULL,
  share_scope          TEXT        NOT NULL DEFAULT 'team',      -- local|project|team|global
  list_gid             TEXT        DEFAULT NULL,
  attachments          JSONB       NOT NULL DEFAULT '[]',
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_craft_rules_status ON knowledge.craft_rules(status);
CREATE INDEX IF NOT EXISTS idx_craft_rules_scope  ON knowledge.craft_rules(share_scope);
CREATE INDEX IF NOT EXISTS idx_craft_rules_list   ON knowledge.craft_rules(list_gid) WHERE list_gid IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════
-- 脚本结束
--
-- 保留的旧表（不受本脚本影响）：
--   bop.bop_versions             已有，本脚本 ALTER 追加字段
--   factory.factory_stations     物理资源，不变
--   factory.factory_sections     物理资源，不变
--   factory.factories            物理资源，不变
--   factory.factory_layout_templates 工厂布局模板，不变
--   factory.factory_tools/factory_equipments/factory_fixtures  实体资源，不变
--   template.vpps_tools/vpps_equipments/vpps_fixtures  模板库，不变
--   template.fastener_spec / template.vpps_parts  标准件库，不变
--   proj.collab_sessions         section_gid FK 已由 CASCADE 移除，列保留备查
-- ═══════════════════════════════════════════════════════════════════

-- display_id 迁移（已有数据库）
ALTER TABLE knowledge.knowledge_entries ADD COLUMN IF NOT EXISTS display_id TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge.craft_rules        ADD COLUMN IF NOT EXISTS display_id TEXT NOT NULL DEFAULT '';


-- ═══════════════════════════════════════════════════════════════════
-- D. BOP 实体架构补全（V2.1）
-- 新增 5 个实体表 + 现有表追加字段
-- ═══════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────
-- D-1. 岗位工艺详情（node_type = operator_process）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_operator (
  gid                        TEXT        PRIMARY KEY,
  project_gid                TEXT        NOT NULL,
  name                       TEXT        NOT NULL,
  version_no                 TEXT        NOT NULL DEFAULT '01',
  factory_station_ref_gid    TEXT,    -- 关联 factory.factory_stations.gid（物理工位）
  operator_code              TEXT,
  headcount                  INTEGER     NOT NULL DEFAULT 1,
  owner_gid                  TEXT,
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_asm_op_proc_proj ON bop.bop_operator(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- D-2. 人机姿态（node_type = jack_pos）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_jack_pos (
  gid             TEXT        PRIMARY KEY,
  project_gid     TEXT        NOT NULL,
  name            TEXT        NOT NULL,
  version_no      TEXT        NOT NULL DEFAULT '01',
  jack_pos_type   TEXT,       -- standing/kneeling/crouching/overhead 等
  ergonomic_score INTEGER,
  posture_desc    TEXT,
  image_ref       JSONB       NOT NULL DEFAULT '{}',  -- 姿态图片附件
  params          JSONB       NOT NULL DEFAULT '{}',
  status          TEXT        NOT NULL DEFAULT 'draft',
  owner_gid       TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by      TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_jack_pos_proj ON bop.bop_jack_pos(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- D-3. 地面高度（现有）（node_type = floor_height_factory）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_floor_height (
  gid               TEXT        PRIMARY KEY,
  project_gid       TEXT        NOT NULL,
  name              TEXT        NOT NULL DEFAULT '',
  height_mm         INTEGER     NOT NULL DEFAULT 0,   -- 实测地面高度，mm
  measured_at       TIMESTAMPTZ,
  measured_by       TEXT,
  station_ref_gid   TEXT,      -- 关联 factory.factory_stations.gid
  notes             TEXT,
  status            TEXT        NOT NULL DEFAULT 'active',  -- active/obsolete
  owner_gid         TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_floor_h_proj ON bop.bop_floor_height(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- D-4. 控制计划（node_type = contral_plan）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_control_plan (
  gid               TEXT        PRIMARY KEY,
  project_gid       TEXT        NOT NULL,
  name              TEXT        NOT NULL DEFAULT '',
  display_id        TEXT        NOT NULL DEFAULT '',  -- 人类可读 ID
  version_no        TEXT        NOT NULL DEFAULT '01',
  status            TEXT        NOT NULL DEFAULT 'draft',  -- draft/review/released/obsolete
  content_ref       JSONB       NOT NULL DEFAULT '{}',    -- 文档附件引用
  applicable_scope  JSONB       NOT NULL DEFAULT '{}',
  owner_gid         TEXT,
  attachments       JSONB       NOT NULL DEFAULT '[]',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_ctrl_plan_proj ON bop.bop_control_plan(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- D-5. 工艺卡（node_type = process_chart）
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bop.bop_process_charts (
  gid               TEXT        PRIMARY KEY,
  project_gid       TEXT        NOT NULL,
  name              TEXT        NOT NULL DEFAULT '',
  display_id        TEXT        NOT NULL DEFAULT '',
  version_no        TEXT        NOT NULL DEFAULT '01',
  status            TEXT        NOT NULL DEFAULT 'draft',  -- draft/review/released/obsolete
  chart_type        TEXT,       -- 工艺卡类型（如 assembly/test/inspection）
  content_ref       JSONB       NOT NULL DEFAULT '{}',    -- 文档附件引用
  owner_gid         TEXT,
  attachments       JSONB       NOT NULL DEFAULT '[]',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_proc_chart_proj ON bop.bop_process_charts(project_gid);


-- ───────────────────────────────────────────────────────────────────
-- D-6. 现有表追加字段（幂等 ALTER TABLE）
-- ───────────────────────────────────────────────────────────────────

-- bop.bop_steps：增值工时 / 总工时 / 地面高度需求 / 工艺流程图 / 工艺卡图片
-- （原 vd_time / total_time / floor_height_need / process_flow_pic / process_chart_pic 节点降级为字段）
ALTER TABLE bop.bop_steps ADD COLUMN IF NOT EXISTS vd_time             REAL;
ALTER TABLE bop.bop_steps ADD COLUMN IF NOT EXISTS total_time          REAL;
ALTER TABLE bop.bop_steps ADD COLUMN IF NOT EXISTS floor_height_need   INTEGER;
ALTER TABLE bop.bop_steps ADD COLUMN IF NOT EXISTS process_flow_pic    JSONB;
ALTER TABLE bop.bop_steps ADD COLUMN IF NOT EXISTS process_chart_pic   JSONB;

-- process_flow_pic 同时存在 bop_entries 上（直接写入，无需走 bop_steps 中间表）
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS process_flow_pic  JSONB;


-- ───────────────────────────────────────────────────────────────────
-- D-7. bop_entry_links link_type 扩展说明（注释，不改 DDL）
-- ───────────────────────────────────────────────────────────────────
--
-- 工艺过程节点关联（process hierarchy）
--   'asm_line_process'      → bop.bop_line.gid
--   'asm_station_process'   → bop.bop_station.gid
--   'asm_operator_process'  → bop.bop_operator.gid
--   'asm_operation'         → bop.bop_steps.gid
--   'physical_station'      → factory.factory_stations.gid（物理工位关联）
--
-- 工厂实物资源关联（factory resource）
--   'physical_equipment'    → factory.factory_equipments.gid
--   'physical_tool'         → factory.factory_tools.gid
--   'physical_fixture'      → factory.factory_fixtures.gid
--
-- 资源实体关联（resource）
--   'project_equipment'     → bop.bop_equipments.gid
--   'project_tooling'       → bop.bop_fixtures.gid（工装）
--   'project_tools'         → bop.bop_tools.gid（工具）
--   'project_roles'         → bop.project_roles.gid（人员）
--   'floor_height'          → bop.bop_floor_height.gid
--   'control_plan'          → bop.bop_control_plan.gid
--   'process_chart'         → bop.bop_process_charts.gid
--   'jack_pos'              → bop.bop_jack_pos.gid
--   'pbom_part'             → bop.pbom.gid（通过 vpps 稳定链接）
--
-- 知识/规则节点关联（knowledge & rule）
--   'knowledge'             → knowledge.knowledge_entries.gid
--   'rule_std'              → knowledge.craft_rules.gid（标准规则）
--   'rule_custom'           → knowledge.craft_rules.gid（项目专用规则）


-- ═══════════════════════════════════════════════════════════════════
-- D-8. vpps_part + part_feed（工序/操作所针对的零件 + 是否涉及上料）
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE bop.bop_entries  ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_entries  ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bop.bop_steps    ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_steps    ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bop.bop_process  ADD COLUMN IF NOT EXISTS vpps_part TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_process  ADD COLUMN IF NOT EXISTS part_feed BOOLEAN NOT NULL DEFAULT FALSE;


-- ═══════════════════════════════════════════════════════════════════
-- E. vpps 字段（全域工程师指定的跨版本稳定壳标识）
-- ═══════════════════════════════════════════════════════════════════
--
-- vpps 是工程师人为规定的稳定标识符，不由系统自动生成，与 gid 职责不同：
--   gid  = 系统流水号（雪花算法，唯一，不可变，用于 DB 追踪）
--   vpps = 工程语义壳（工程师定义，跨版本不变，用于业务对比和溯源）
--
-- 规则：
--   - 实体升版（新 gid）时，vpps 保持不变
--   - BOP 版本 fork 时，bop_entries.vpps 随节点携带（不重新生成）
--   - bop_entries.vpps = 绑定实体的 vpps（由实体带入）
--   - 零件的 vpps 来自外部零件管理系统；其他实体的 vpps 由工程师手动指定
--   - 工厂资源域（factory.factory_stations / factory.*等）不在此列，
--     工厂域有自己的稳定编码体系
--
-- ── bop.bop_entries ─────────────────────────────────────────────────────
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS vpps_desc TEXT;
CREATE INDEX IF NOT EXISTS idx_bop_ent_vpps ON bop.bop_entries(vpps) WHERE vpps IS NOT NULL;
-- 版本条目主查询过滤索引（WHERE version_gid = %s AND is_deleted = FALSE）
CREATE INDEX IF NOT EXISTS idx_bop_ent_version ON bop.bop_entries(version_gid) WHERE is_deleted = FALSE;

-- ── 工艺过程实体 ─────────────────────────────────────────────────────
-- bop.bop_steps 已有 vpps TEXT + vpps_desc TEXT ✓
ALTER TABLE bop.bop_line     ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_station  ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_operator ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.asm_steps    ADD COLUMN IF NOT EXISTS vpps TEXT;

-- ── 项目资源实体 ─────────────────────────────────────────────────────
ALTER TABLE bop.bop_equipments    ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_fixtures      ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_tools         ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.project_roles     ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_control_plan  ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_process_charts ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_floor_height  ADD COLUMN IF NOT EXISTS vpps TEXT;
ALTER TABLE bop.bop_jack_pos      ADD COLUMN IF NOT EXISTS vpps TEXT;

-- ── 索引（WHERE vpps IS NOT NULL 避免稀疏索引膨胀）────────────────────
CREATE INDEX IF NOT EXISTS idx_asm_line_proc_vpps    ON bop.bop_line(vpps)           WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_asm_sta_proc_vpps     ON bop.bop_station(vpps)        WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_asm_op_proc_vpps      ON bop.bop_operator(vpps)       WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_asm_step_vpps         ON bop.asm_steps(vpps)          WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_equip_vpps       ON bop.bop_equipments(vpps)     WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_tooling_vpps     ON bop.bop_fixtures(vpps)       WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_tools_vpps       ON bop.bop_tools(vpps)          WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_roles_vpps       ON bop.project_roles(vpps)      WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_ctrl_plan_vpps   ON bop.bop_control_plan(vpps)   WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_proc_chart_vpps  ON bop.bop_process_charts(vpps) WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_floor_h_vpps     ON bop.bop_floor_height(vpps)   WHERE vpps IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_proj_jack_pos_vpps    ON bop.bop_jack_pos(vpps)       WHERE vpps IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════
-- F. BOP 版本家族（分组 + 冻结 + 归档）
-- ═══════════════════════════════════════════════════════════════════
--
-- version_family_gid: 版本族 ID（新建版本时 = 自身 gid；加入已有族时继承）
-- bop_name:           版本族的人类可读名称（如"X11总装整车BOP"），同族共享
-- frozen_at:          冻结时间戳，非 NULL 则版本只读，bop_entries.title 已快照
-- archived_at:        归档时间戳，通过 POST /api/bop/version-families/{gid}/archive 整组归档

ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS version_family_gid TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS bop_name           TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS frozen_at          TIMESTAMPTZ;
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS archived_at        TIMESTAMPTZ;

-- 已有版本：自成一家（family = 自身 gid）
UPDATE bop.bop_versions SET version_family_gid = gid WHERE version_family_gid IS NULL;

CREATE INDEX IF NOT EXISTS idx_bop_versions_family ON bop.bop_versions(version_family_gid);


-- ═══════════════════════════════════════════════════════════════════
-- G. 工厂层级 + BOP 版本血缘 + Fork 预设
-- ═══════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────
-- G-1. 物理产线（工段 = 线体，同一概念）
-- ───────────────────────────────────────────────────────────────────
--
-- 物理层级：factory.factories → factory.factory_lines → factory.factory_stations
-- 工艺层级：factory_bop → line_process → station_process → ...
-- 两层级之间无强制 FK，通过 BOP 树（parent_bop_gid）或 bop_entry_links 按需关联。

CREATE TABLE IF NOT EXISTS factory.factory_lines (
  gid             TEXT        PRIMARY KEY,
  factory_gid     TEXT        NOT NULL,               -- 所属工厂（跨域引用，无 FK）
  name            TEXT        NOT NULL,
  code            TEXT,                               -- 产线编号，如 PBS-01
  line_type       TEXT,                               -- assembly/test/inspection 等
  description     TEXT,
  sort_order      INTEGER     NOT NULL DEFAULT 0,
  meta            JSONB       NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by      TEXT
);
CREATE INDEX IF NOT EXISTS idx_factory_lines_factory ON factory.factory_lines(factory_gid);

-- 物理工位追加产线归属（仅物理层级内关联，不跨到工艺侧）
ALTER TABLE factory.factory_stations ADD COLUMN IF NOT EXISTS factory_line_gid TEXT;
CREATE INDEX IF NOT EXISTS idx_factory_sta_line ON factory.factory_stations(factory_line_gid)
  WHERE factory_line_gid IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- G-2. BOP 版本血缘（Git-lite：parent_version_gid + change_note）
-- ───────────────────────────────────────────────────────────────────
--
-- parent_version_gid: fork/branch 的直接来源版本 gid（自引用，无 FK）
-- change_note:        本次版本变更说明（类比 git commit message）

ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS parent_version_gid TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS change_note        TEXT;

CREATE INDEX IF NOT EXISTS idx_bop_ver_parent ON bop.bop_versions(parent_version_gid)
  WHERE parent_version_gid IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- G-3. 移除工艺过程表的跨层级 FK（工艺层级通过 BOP 树管理，不与物理层强制关联）
-- ───────────────────────────────────────────────────────────────────
--
-- 设计决定（2026-05-10）：
--   工艺节点（bop.bop_line/bop_station/bop_operator）和物理工厂层（factory.factory_lines/factory_stations）
--   之间不建直接 FK，关联关系完全通过 BOP 树（parent_bop_gid）或 bop_entry_links 表达。
--   好处：可在树形视图上拖拽重挂，不受物理 FK 约束。

ALTER TABLE bop.bop_line     DROP COLUMN IF EXISTS factory_line_ref_gid;
ALTER TABLE bop.bop_station  DROP COLUMN IF EXISTS factory_station_ref_gid;
ALTER TABLE bop.bop_operator DROP COLUMN IF EXISTS factory_station_ref_gid;


-- ───────────────────────────────────────────────────────────────────
-- G-4. BOP Fork 预设（团队共享，DB 持久化）
-- ───────────────────────────────────────────────────────────────────
--
-- 字段说明：
--   include_node_types: null / [] = 全部类型；有值则只 fork 指定 node_type
--   field_rules:        {"field": "inherit"|"reset", ...}
--                       未指定字段默认 inherit
--   meta_key_rules:     {"meta_key": "inherit"|"reset", ...}
--                       特殊键 "*" 表示所有未明确指定的 meta key 的默认规则
--   is_system:          系统预设（前端内置，仅注释在此，不实际插入 DB）

CREATE TABLE IF NOT EXISTS bop.bop_fork_presets (
  gid                TEXT        PRIMARY KEY,
  name               TEXT        NOT NULL,
  description        TEXT,
  include_node_types JSONB,                          -- NULL = 全部；["process","operation",...] = 指定类型
  field_rules        JSONB       NOT NULL DEFAULT '{}',
  meta_key_rules     JSONB       NOT NULL DEFAULT '{}',
  team_gid           TEXT,                           -- NULL = 所有团队可见
  created_by         TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fork_presets_team ON bop.bop_fork_presets(team_gid)
  WHERE team_gid IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- H. BOP 暂存箱（Staging）
-- ───────────────────────────────────────────────────────────────────
--
-- 版本级暂存区，用于：
--   1. 从主视图 demote 的节点（保留 original_entry_gid 以便还原）
--   2. 从关联面板拖入的实体（source_type + source_ref_gid）
--   3. 手动新建的待定节点
--
-- 暂存项通过 promote 操作进入主视图（bop_entries），或直接删除。

CREATE TABLE IF NOT EXISTS bop.bop_staging (
    gid                TEXT PRIMARY KEY,
    bop_version_gid    TEXT NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
    node_type          TEXT NOT NULL DEFAULT 'process',
    title              TEXT NOT NULL DEFAULT '',
    vpps               TEXT,
    source_type        TEXT,            -- 'bop_entry' | 'pbom' | 'issue' | 'task' | 'tool' | 'gbop' | NULL(手动)
    source_ref_gid     TEXT,            -- 来源实体 gid
    original_entry_gid TEXT,            -- 从主视图 demote 时，指向被 soft-delete 的 bop_entry gid
    child_count        INTEGER NOT NULL DEFAULT 0,
    meta               JSONB NOT NULL DEFAULT '{}',
    sort_order         REAL NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by         TEXT
);
CREATE INDEX IF NOT EXISTS idx_bop_staging_version ON bop.bop_staging(bop_version_gid);


-- ═══════════════════════════════════════════════════════════════════
-- I. BOP 版本生命周期重构（4 状态 + 快照机制）
--
-- 状态流转：active → baseline → M → archived
--   active   = 活动，可自由编辑
--   baseline = 基线（冻结+快照），内部评审用，可回退到 active
--   M        = 发布（冻结+快照+正式发布），不可回退
--   archived = 归档，终态，不可逆
-- ═══════════════════════════════════════════════════════════════════

-- I-1. 新增 published_at 字段（发布时间戳）
ALTER TABLE bop.bop_versions ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

-- I-1b. 修改 status 默认值（旧库可能还是 'draft'）
ALTER TABLE bop.bop_versions ALTER COLUMN status SET DEFAULT 'active';

-- I-2. status 值迁移：draft→active, frozen→baseline, released→M
UPDATE bop.bop_versions SET status='active'   WHERE status='draft';
UPDATE bop.bop_versions SET status='baseline' WHERE status='frozen';
UPDATE bop.bop_versions SET status='M'        WHERE status='released';

-- I-3. bop_entry_links 追加快照字段（冻结时写入关联实体的关键字段快照）
ALTER TABLE bop.bop_entry_links ADD COLUMN IF NOT EXISTS snapshot_data JSONB;

-- ── 本体驱动存储重构（2026-06-15）：各实体表加 ext JSONB ────────────────────
-- 动态本体属性（storage_hint='entity_table' 且实体表无对应固定列时）落入 ext
ALTER TABLE bop.bop_line       ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.bop_station    ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.bop_operator   ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.bop_process    ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.bop_steps      ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';

ALTER TABLE factory.factory_stations    ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE factory.factory_equipments  ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE factory.factory_tools       ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE factory.factory_fixtures    ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';

-- ── 数据迁移：bop_entries.meta → 实体表 ext（2026-06-15）─────────────────────
-- 将错误存入 bop_entries.meta 的实体属性迁移到对应实体表的 ext 字段
-- 执行前提：上方 ext 列 ALTER TABLE 已执行

-- line_process → bop.bop_line.ext
UPDATE bop.bop_line e
SET ext = ext || jsonb_strip_nulls(jsonb_build_object(
    'line_code',     be.meta->>'line_code',
    'line_type',     be.meta->>'line_type',
    'target_takt_s', (be.meta->>'target_takt_s')::float,
    'num_stations',  (be.meta->>'num_stations')::int
)), updated_at = NOW()
FROM bop.bop_entry_links l
JOIN bop.bop_entries be ON be.gid = l.entry_gid
WHERE l.entity_gid = e.gid AND l.is_primary = TRUE
  AND l.deleted_at IS NULL AND be.is_deleted = FALSE
  AND (be.meta ? 'line_code' OR be.meta ? 'line_type'
       OR be.meta ? 'target_takt_s' OR be.meta ? 'num_stations');

-- station_process → bop.bop_station.ext
UPDATE bop.bop_station e
SET ext = ext || jsonb_strip_nulls(jsonb_build_object(
    'station_code', be.meta->>'station_code',
    'station_seq',  (be.meta->>'station_seq')::int,
    'cycle_time_s', (be.meta->>'cycle_time_s')::float,
    'station_type', be.meta->>'station_type'
)), updated_at = NOW()
FROM bop.bop_entry_links l
JOIN bop.bop_entries be ON be.gid = l.entry_gid
WHERE l.entity_gid = e.gid AND l.is_primary = TRUE
  AND l.deleted_at IS NULL AND be.is_deleted = FALSE
  AND (be.meta ? 'station_code' OR be.meta ? 'station_seq'
       OR be.meta ? 'cycle_time_s' OR be.meta ? 'station_type');

-- operator_process → bop.bop_operator.ext
UPDATE bop.bop_operator e
SET ext = ext || jsonb_strip_nulls(jsonb_build_object(
    'shift',            be.meta->>'shift',
    'qualification_req', be.meta->>'qualification_req'
)), updated_at = NOW()
FROM bop.bop_entry_links l
JOIN bop.bop_entries be ON be.gid = l.entry_gid
WHERE l.entity_gid = e.gid AND l.is_primary = TRUE
  AND l.deleted_at IS NULL AND be.is_deleted = FALSE
  AND (be.meta ? 'shift' OR be.meta ? 'qualification_req');

-- process → bop.bop_process.ext（process_code/standard_time 有固定列，不迁移到 ext）
UPDATE bop.bop_process e
SET ext = ext || jsonb_strip_nulls(jsonb_build_object(
    'process_seq',    (be.meta->>'process_seq')::int,
    'cycle_time_s',   (be.meta->>'cycle_time_s')::float,
    'process_method', be.meta->>'process_method',
    'quality_level',  be.meta->>'quality_level',
    'safety_notes',   be.meta->>'safety_notes'
)), updated_at = NOW()
FROM bop.bop_entry_links l
JOIN bop.bop_entries be ON be.gid = l.entry_gid
WHERE l.entity_gid = e.gid AND l.is_primary = TRUE
  AND l.deleted_at IS NULL AND be.is_deleted = FALSE
  AND (be.meta ? 'process_seq' OR be.meta ? 'cycle_time_s' OR be.meta ? 'process_method'
       OR be.meta ? 'quality_level' OR be.meta ? 'safety_notes');

-- operation（额外属性）→ bop.bop_steps.ext
-- vd_time/total_time/floor_height_need/op_req_height 已有固定列，不迁移
UPDATE bop.bop_steps e
SET ext = ext || jsonb_strip_nulls(jsonb_build_object(
    'op_seq',            (be.meta->>'op_seq')::int,
    'op_type',           be.meta->>'op_type',
    'torque_value_nm',   (be.meta->>'torque_value_nm')::float,
    'torque_angle_deg',  (be.meta->>'torque_angle_deg')::float,
    'weld_current_a',    (be.meta->>'weld_current_a')::float,
    'adhesive_code',     be.meta->>'adhesive_code',
    'inspection_method', be.meta->>'inspection_method'
)), updated_at = NOW()
FROM bop.bop_entry_links l
JOIN bop.bop_entries be ON be.gid = l.entry_gid
WHERE l.entity_gid = e.gid AND l.is_primary = TRUE
  AND l.deleted_at IS NULL AND be.is_deleted = FALSE
  AND (be.meta ? 'op_seq' OR be.meta ? 'op_type' OR be.meta ? 'torque_value_nm'
       OR be.meta ? 'torque_angle_deg' OR be.meta ? 'weld_current_a'
       OR be.meta ? 'adhesive_code' OR be.meta ? 'inspection_method');

ALTER TABLE bop.bop_equipments  ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.bop_fixtures    ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.bop_tools       ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.project_roles   ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}';

-- ── bop_name 迁移：working 版本的族群名改为项目名（2026-06-16）──────────
-- template 类型保留原 bop_name 不动
UPDATE bop.bop_versions bv
SET bop_name = p.name, updated_at = NOW()
FROM proj.projects p
WHERE bv.project_gid = p.gid
  AND bv.version_type = 'working'
  AND bv.bop_name IS DISTINCT FROM p.name;

-- ── BOP 生命周期 ── 2 new columns + 4 new tables ─────────────────────────

-- J-1. bop_versions 追加两列
ALTER TABLE bop.bop_versions
  ADD COLUMN IF NOT EXISTS lifecycle_phase TEXT NOT NULL DEFAULT 'init',
  ADD COLUMN IF NOT EXISTS lifecycle_state JSONB NOT NULL DEFAULT '{}';
-- lifecycle_phase 取值: init | refine | publish_cycle | archived

-- J-2. 阶段时间线表
CREATE TABLE IF NOT EXISTS bop.bop_lifecycle_history (
  gid               TEXT PRIMARY KEY,
  version_gid       TEXT NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
  phase             TEXT NOT NULL,
  entered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  confirmed_at      TIMESTAMPTZ,
  confirmed_by_gid  TEXT,
  confirmed_by_name TEXT,
  note              TEXT,
  UNIQUE (version_gid, phase)
);
CREATE INDEX IF NOT EXISTS idx_bop_lc_history_ver ON bop.bop_lifecycle_history(version_gid);

-- J-3. 完善度指标表（line_gid NULL = 整体；用 expression index 避免 NULL!=NULL 问题）
CREATE TABLE IF NOT EXISTS bop.bop_lifecycle_stats (
  gid                 TEXT PRIMARY KEY,
  version_gid         TEXT NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
  line_gid            TEXT,
  stats_snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
  nok_vpps            INTEGER NOT NULL DEFAULT 0,
  nok_unbound_parts   INTEGER NOT NULL DEFAULT 0,
  nok_unbound_ops     INTEGER NOT NULL DEFAULT 0,
  tools_bound         INTEGER NOT NULL DEFAULT 0,
  tools_total         INTEGER NOT NULL DEFAULT 0,
  fixtures_bound      INTEGER NOT NULL DEFAULT 0,
  fixtures_total      INTEGER NOT NULL DEFAULT 0,
  equipment_bound     INTEGER NOT NULL DEFAULT 0,
  equipment_total     INTEGER NOT NULL DEFAULT 0,
  coverage_ok         BOOLEAN NOT NULL DEFAULT FALSE,
  balance_ok          BOOLEAN NOT NULL DEFAULT FALSE,
  tasks_done          INTEGER NOT NULL DEFAULT 0,
  tasks_total         INTEGER NOT NULL DEFAULT 0,
  issues_open         INTEGER NOT NULL DEFAULT 0,
  rules_warn          INTEGER NOT NULL DEFAULT 0,
  rules_block         INTEGER NOT NULL DEFAULT 0,
  refreshed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- expression index：COALESCE 将 NULL 统一为空字符串，使 ON CONFLICT 生效
CREATE UNIQUE INDEX IF NOT EXISTS idx_bop_lc_stats_unique
  ON bop.bop_lifecycle_stats(version_gid, COALESCE(line_gid,''), stats_snapshot_date);
CREATE INDEX IF NOT EXISTS idx_bop_lc_stats_ver  ON bop.bop_lifecycle_stats(version_gid);
CREATE INDEX IF NOT EXISTS idx_bop_lc_stats_date ON bop.bop_lifecycle_stats(stats_snapshot_date);

-- J-4. 线体快照（Checkpoint）表
CREATE TABLE IF NOT EXISTS bop.bop_line_checkpoints (
  gid             TEXT PRIMARY KEY,
  version_gid     TEXT NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
  line_gid        TEXT NOT NULL,
  label           TEXT,
  created_by      TEXT,
  created_by_name TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  snapshot        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bop_ckpt_ver_line ON bop.bop_line_checkpoints(version_gid, line_gid, created_at);

-- J-5. 线体操作日志表（简化版 A）
CREATE TABLE IF NOT EXISTS bop.bop_line_operation_log (
  gid               TEXT PRIMARY KEY,
  version_gid       TEXT NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
  line_gid          TEXT NOT NULL,
  batch_id          TEXT NOT NULL,
  op_type           TEXT NOT NULL,
  entity_gid        TEXT,
  entity_title      TEXT,
  old_state         JSONB,
  new_state         JSONB,
  op_seq            INTEGER NOT NULL DEFAULT 0,
  performed_by      TEXT,
  performed_by_name TEXT,
  performed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  rolled_back       BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_bop_oplog_ver_line ON bop.bop_line_operation_log(version_gid, line_gid, performed_at);
CREATE INDEX IF NOT EXISTS idx_bop_oplog_batch    ON bop.bop_line_operation_log(batch_id);


-- ═══════════════════════════════════════════════════════════════════════
-- 生命周期重构（族群级）
-- ═══════════════════════════════════════════════════════════════════════

-- K-1. 族群级元数据表
CREATE TABLE IF NOT EXISTS bop.bop_version_families (
  gid                TEXT PRIMARY KEY,
  bop_name           TEXT NOT NULL DEFAULT '',
  lifecycle_phase    TEXT NOT NULL DEFAULT 'init',  -- init / refine / publish_cycle / archived
  active_version_gid TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bop_families_active ON bop.bop_version_families(active_version_gid);

-- K-2. PBOM 差异工作队列
CREATE TABLE IF NOT EXISTS bop.bop_pbom_diff_queue (
  gid              TEXT PRIMARY KEY,
  family_gid       TEXT NOT NULL,
  bop_version_gid  TEXT NOT NULL REFERENCES bop.bop_versions(gid) ON DELETE CASCADE,
  pbom_base_gid    TEXT,
  pbom_target_gid  TEXT NOT NULL,
  pbom_part_gid    TEXT NOT NULL,
  diff_type        TEXT NOT NULL,           -- added / modified / removed
  vpps             TEXT,
  vpps_desc        TEXT,
  status           TEXT NOT NULL DEFAULT 'pending',  -- pending / done / ignored
  note             TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pbom_diff_ver    ON bop.bop_pbom_diff_queue(bop_version_gid, status);
CREATE INDEX IF NOT EXISTS idx_pbom_diff_family ON bop.bop_pbom_diff_queue(family_gid);

-- K-3. bop_entries 增加 fork 溯源字段
ALTER TABLE bop.bop_entries ADD COLUMN IF NOT EXISTS source_entry_gid TEXT DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_bop_entries_source ON bop.bop_entries(source_entry_gid) WHERE source_entry_gid IS NOT NULL;

-- K-4. 存量数据迁移：将现有活动版本注册到族群表（DBeaver 执行）
-- INSERT INTO bop.bop_version_families (gid, bop_name, lifecycle_phase, active_version_gid)
-- SELECT DISTINCT ON (version_family_gid)
--   version_family_gid, bop_name, lifecycle_phase, gid
-- FROM bop.bop_versions
-- WHERE status = 'active' AND archived_at IS NULL
-- ORDER BY version_family_gid, created_at DESC
-- ON CONFLICT (gid) DO NOTHING;

