-- AI00 云端用户数据库（users_db）
-- 独立 PostgreSQL 实例，只存用户身份与角色
-- 飞书 App Secret 永远不入库

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

-- 团队表（逻辑隔离，同一 PostgreSQL 实例，用 team_id 列区分）
CREATE TABLE IF NOT EXISTS auth.teams (
    gid               TEXT PRIMARY KEY,
    name              TEXT NOT NULL DEFAULT '',
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    config            JSONB NOT NULL DEFAULT '{}',
    feishu_dept_id    TEXT,
    parent_team_gid   TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Migration: 为已有 teams 表补充 config 列
ALTER TABLE auth.teams ADD COLUMN config JSONB NOT NULL DEFAULT '{}';
-- Migration: 飞书部门 ID（用于 org 自动同步，NULL = 手动创建的团队）
ALTER TABLE auth.teams ADD COLUMN feishu_dept_id TEXT;
ALTER TABLE auth.teams ADD COLUMN parent_team_gid TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_teams_feishu_dept ON auth.teams (feishu_dept_id) WHERE feishu_dept_id IS NOT NULL;

-- 全局系统配置表（飞书凭证、DB 连接串等，热重载）
CREATE TABLE IF NOT EXISTS app.system_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth.users (
    gid              TEXT PRIMARY KEY,
    feishu_open_id   TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL DEFAULT '',
    email            TEXT NOT NULL DEFAULT '',
    avatar_url       TEXT NOT NULL DEFAULT '',
    -- 系统角色：super_admin / team_admin / project_admin /
    --           rule_admin / knowledge_admin / member / external
    system_role      TEXT NOT NULL DEFAULT 'external',
    -- 外部子类型：outsource / rd / factory / supplier
    external_subtype TEXT DEFAULT NULL,
    team_id          TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    notification_prefs JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_feishu_id ON auth.users (feishu_open_id);
CREATE INDEX IF NOT EXISTS idx_users_role      ON auth.users (system_role);
CREATE INDEX IF NOT EXISTS idx_users_team      ON auth.users (team_id);

CREATE TABLE IF NOT EXISTS auth.project_members (
    gid          TEXT PRIMARY KEY,
    project_gid  TEXT NOT NULL,
    user_gid     TEXT NOT NULL REFERENCES auth.users(gid) ON DELETE CASCADE,
    -- role: project_manager | section_owner | se_owner | bid_owner
    role         TEXT NOT NULL DEFAULT 'project_manager',
    -- scope_type: project | section | bid_section
    scope_type   TEXT NOT NULL DEFAULT 'project',
    -- scope_gid: NULL for project_manager; factory_sections.gid or bid_sections.gid otherwise
    scope_gid    TEXT DEFAULT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 同角色同范围只能有一人：
--   项目经理（scope_gid IS NULL）：(project_gid, role) 唯一
--   工段/标段负责人（scope_gid IS NOT NULL）：(project_gid, role, scope_gid) 唯一
CREATE UNIQUE INDEX IF NOT EXISTS idx_pm_unique_global
    ON auth.project_members (project_gid, role)
    WHERE scope_gid IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_pm_unique_scoped
    ON auth.project_members (project_gid, role, scope_gid)
    WHERE scope_gid IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pm_project    ON auth.project_members (project_gid);
CREATE INDEX IF NOT EXISTS idx_pm_user       ON auth.project_members (user_gid);
CREATE INDEX IF NOT EXISTS idx_pm_scope      ON auth.project_members (scope_type, scope_gid);

-- 标段表（项目经理手动维护，对应一个采购标的）
CREATE TABLE IF NOT EXISTS auth.bid_sections (
    gid          TEXT PRIMARY KEY,
    project_gid  TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bid_sections_project ON auth.bid_sections (project_gid);

-- ── Migration: project_members 结构升级 ──────────────────────────────────────
-- 将旧列重命名为新列名（幂等：若已迁移则跳过）
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='auth' AND table_name='project_members' AND column_name='project_role'
    ) THEN
        ALTER TABLE auth.project_members RENAME COLUMN project_role TO role;
    END IF;
END $$;

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='auth' AND table_name='project_members' AND column_name='section_gid'
    ) THEN
        ALTER TABLE auth.project_members RENAME COLUMN section_gid TO scope_gid;
    END IF;
END $$;

ALTER TABLE auth.project_members ADD COLUMN scope_type TEXT NOT NULL DEFAULT 'project';

-- 删除旧的 UNIQUE(project_gid, user_gid) 约束（允许一人在同项目多角色）
ALTER TABLE auth.project_members DROP CONSTRAINT IF EXISTS project_members_project_gid_user_gid_key;

-- 登录状态轮询表（OAuth 回调后写入，客户端轮询读取）
CREATE TABLE IF NOT EXISTS auth.auth_pending (
    state       TEXT PRIMARY KEY,          -- OAuth state 参数
    jwt         TEXT DEFAULT NULL,         -- 登录成功后写入
    error       TEXT DEFAULT NULL,         -- 失败原因
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '10 minutes'
);

-- 项目成员角色（auth.section_owners）
-- 注意：此表存储项目级角色分配（project_manager/section_owner 等），非 BOP 岗位需求
CREATE TABLE IF NOT EXISTS auth.section_owners (
    gid          TEXT PRIMARY KEY,
    project_gid  TEXT NOT NULL REFERENCES proj.projects(gid) ON DELETE CASCADE,
    user_gid     TEXT NOT NULL REFERENCES auth.users(gid) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'section_owner',
    section_gid  TEXT DEFAULT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_section_owners_project ON auth.section_owners (project_gid);
CREATE INDEX IF NOT EXISTS idx_section_owners_user    ON auth.section_owners (user_gid);


-- ══════════════════════════════════════════════════════════════
-- 云端业务数据表（project / craft / eBOM / collab / approval /
--               std_op / craft_lib / factory_resource）
-- ══════════════════════════════════════════════════════════════

-- ── 项目 BC ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS proj.vehicle_models (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    brand       TEXT NOT NULL DEFAULT '',
    platform    TEXT NOT NULL DEFAULT '',
    team_id     TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    meta        JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS proj.projects (
    gid          TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    project_code TEXT NOT NULL DEFAULT '',               -- 项目代号（如 X11、P72）
    model_year   INTEGER,                               -- 车型年款，如 2025
    suffix       TEXT NOT NULL DEFAULT '',              -- 后缀（如 A、SOP、PRE）
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'preparing',    -- preparing/in_progress/completed/archived
    vehicle_model_gid TEXT REFERENCES proj.vehicle_models(gid) ON DELETE SET NULL,
    team_id      TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    owner_gid    TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    share_scope  TEXT NOT NULL DEFAULT 'team',
    jph          REAL,                                 -- Jobs Per Hour（产线节拍）
    is_deleted   BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at   TIMESTAMPTZ,
    archived_at  TIMESTAMPTZ,
    meta         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_team   ON proj.projects (team_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON proj.projects (status);

-- Migration: vehicle_models 新增 vehicle_type 字段
ALTER TABLE proj.vehicle_models ADD COLUMN vehicle_type TEXT DEFAULT '';
-- 可选值：纯电MPV / 纯电SUV / 增程SUV / 纯电轿车 / 增程轿车 / 增程MPV

-- Migration: projects 新增目标工厂 FK
ALTER TABLE proj.projects ADD COLUMN factory_gid TEXT REFERENCES factory.factories(gid) ON DELETE SET NULL;

-- ── eBOM BC ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bop.pbom_versions (
    gid          TEXT PRIMARY KEY,
    project_gid  TEXT NOT NULL REFERENCES proj.projects(gid) ON DELETE CASCADE,
    version_tag  TEXT NOT NULL DEFAULT '',
    source_type  TEXT NOT NULL DEFAULT 'manual',   -- manual/import/sync
    status       TEXT NOT NULL DEFAULT 'draft',    -- draft/released
    meta         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bom_snapshots_project ON bop.pbom_versions (project_gid);

CREATE TABLE IF NOT EXISTS bop.pbom (
    gid             TEXT PRIMARY KEY,
    snapshot_gid    TEXT NOT NULL REFERENCES bop.pbom_versions(gid) ON DELETE CASCADE,
    part_no         TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    quantity        REAL NOT NULL DEFAULT 1,
    unit            TEXT NOT NULL DEFAULT 'pcs',
    material        TEXT DEFAULT NULL,
    parent_gid      TEXT DEFAULT NULL,
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_part_entries_snapshot ON bop.pbom (snapshot_gid);

-- vpps：零件号升版时不变的稳定壳标识（工程师指定，来自外部零件管理系统）
ALTER TABLE bop.pbom ADD COLUMN vpps TEXT;
CREATE INDEX IF NOT EXISTS idx_part_entries_vpps ON bop.pbom(vpps) WHERE vpps IS NOT NULL;

-- PBOM 扩展列（对齐 TC/PLM 导出 Excel 19列）
ALTER TABLE bop.pbom ADD COLUMN vpps_desc TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN parent_vpps TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN parent_vpps_name TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN bom_row TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN bom_row_label TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN component_id TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN component_type TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN component_version_status TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN purchase_status TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN variable_formula TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN torque TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN torque_importance TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN ownership_user TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN level INTEGER DEFAULT NULL;
ALTER TABLE bop.pbom ADD COLUMN home TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN configuration TEXT DEFAULT '';
ALTER TABLE bop.pbom ADD COLUMN parent_bom_row TEXT DEFAULT '';  -- 父级BOM行标识
-- PBOM 扩展列：CATIA 实例数据 + 变换矩阵 + 限定框 + ECN/FNA
ALTER TABLE bop.pbom ADD COLUMN catia_occurrence_name TEXT DEFAULT '';  -- catiaOccurrenceName
ALTER TABLE bop.pbom ADD COLUMN catia_file_name TEXT DEFAULT '';        -- catiaFileName
ALTER TABLE bop.pbom ADD COLUMN catia_uuid TEXT DEFAULT '';             -- catiaUUID
ALTER TABLE bop.pbom ADD COLUMN default_matrix TEXT DEFAULT '';         -- 默认变换矩阵
ALTER TABLE bop.pbom ADD COLUMN abs_matrix TEXT DEFAULT '';             -- 绝对变换矩阵
ALTER TABLE bop.pbom ADD COLUMN rel_matrix TEXT DEFAULT '';             -- 相对变换矩阵
ALTER TABLE bop.pbom ADD COLUMN local_bbox TEXT DEFAULT '';             -- 限定框
ALTER TABLE bop.pbom ADD COLUMN ecn TEXT DEFAULT '';                    -- ECN编码
ALTER TABLE bop.pbom ADD COLUMN fna TEXT DEFAULT '';                    -- FNA
-- PBOM 分析结果列（紧固件主件识别）
ALTER TABLE bop.pbom ADD COLUMN geo_main_part TEXT DEFAULT '';          -- 几何推测主件
ALTER TABLE bop.pbom ADD COLUMN ref_main_vpps_desc TEXT DEFAULT '';     -- 参考主件VPPS描述
ALTER TABLE bop.pbom ADD COLUMN ref_main_vpps TEXT DEFAULT '';          -- 参考主件vpps
ALTER TABLE bop.pbom ADD COLUMN main_part_consistency TEXT DEFAULT '';  -- 主件一致性状态
ALTER TABLE bop.pbom ADD COLUMN geo_evidence TEXT DEFAULT '';           -- 推测主件几何依据
ALTER TABLE bop.pbom ADD COLUMN lr_side TEXT DEFAULT '';                -- 零件左右侧
-- pbom_versions 扩展：版本名称独立字段（不复用 version_tag）
ALTER TABLE bop.pbom_versions ADD COLUMN name TEXT DEFAULT '';
-- Migration: project_gid 改为可选（PBOM 版本不一定绑定项目）
ALTER TABLE bop.pbom_versions ALTER COLUMN project_gid DROP NOT NULL;
ALTER TABLE bop.pbom_versions ALTER COLUMN project_gid SET DEFAULT NULL;

CREATE TABLE IF NOT EXISTS bop.cad_model_instances (
    gid             TEXT PRIMARY KEY,
    part_entry_gid  TEXT NOT NULL REFERENCES bop.pbom(gid) ON DELETE CASCADE,
    model_file_path TEXT NOT NULL DEFAULT '',
    transform       JSONB NOT NULL DEFAULT '{}',
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 协同 BC ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS proj.collab_sessions (
    gid          TEXT PRIMARY KEY,
    section_gid  TEXT NOT NULL,
    owner_gid    TEXT NOT NULL REFERENCES auth.users(gid) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'active',   -- active/ended
    participants JSONB NOT NULL DEFAULT '[]',
    meta         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at     TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_collab_sessions_section ON proj.collab_sessions (section_gid);

-- ── 审批 BC ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS proj.approval_orders (
    gid            TEXT PRIMARY KEY,
    project_gid    TEXT REFERENCES proj.projects(gid) ON DELETE SET NULL,
    order_type     TEXT NOT NULL DEFAULT 'general',   -- general/craft_change/deviation/scope_upgrade
    title          TEXT NOT NULL DEFAULT '',
    applicant_gid  TEXT NOT NULL REFERENCES auth.users(gid) ON DELETE CASCADE,
    reviewer_gid   TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    status         TEXT NOT NULL DEFAULT 'pending',   -- pending/in_review/approved/rejected/withdrawn
    source_ref     TEXT DEFAULT NULL,
    content        JSONB NOT NULL DEFAULT '{}',
    opinions       JSONB NOT NULL DEFAULT '[]',
    share_scope    TEXT NOT NULL DEFAULT 'project',   -- local|project|team|global
    meta           JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approval_orders_project    ON proj.approval_orders (project_gid);
CREATE INDEX IF NOT EXISTS idx_approval_orders_applicant  ON proj.approval_orders (applicant_gid);
CREATE INDEX IF NOT EXISTS idx_approval_orders_status     ON proj.approval_orders (status);

-- ── GBOP 标准工序库 V2（树形结构） ─────────────────────────────────

-- GBOP 版本管理
CREATE TABLE IF NOT EXISTS template.gbop_versions (
    gid                TEXT PRIMARY KEY,
    name               TEXT NOT NULL DEFAULT '',
    version_family_gid TEXT NOT NULL,                   -- 族ID，首版=gid
    status             TEXT NOT NULL DEFAULT 'draft',   -- draft/active/frozen
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
    level              SMALLINT NOT NULL DEFAULT 0,       -- 0-5
    node_type          TEXT NOT NULL DEFAULT 'process',   -- version/system/device/part/process/operation
    seq_no             REAL NOT NULL DEFAULT 0,
    -- 通用字段
    vpps               TEXT,
    vpps_desc          TEXT NOT NULL DEFAULT '',
    vpps_attr          TEXT NOT NULL DEFAULT '',          -- VPPS属性
    importance         TEXT NOT NULL DEFAULT '',
    torque_importance  TEXT NOT NULL DEFAULT '',
    vehicle_model      TEXT NOT NULL DEFAULT '',
    parent_vpps        TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'active',
    sort_order         REAL NOT NULL DEFAULT 0,
    child_vpps         JSONB NOT NULL DEFAULT '[]',       -- 缓存直接子级的 vpps 列表 [{vpps,node_type,title}]
    -- 审计
    meta               JSONB NOT NULL DEFAULT '{}',
    team_id            TEXT,
    created_by         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gbop_entries_version ON template.gbop_entries(version_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_entries_parent  ON template.gbop_entries(parent_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_entries_vpps    ON template.gbop_entries(vpps) WHERE vpps IS NOT NULL;
ALTER TABLE template.gbop_entries ADD COLUMN vpps_part TEXT    NOT NULL DEFAULT '';
ALTER TABLE template.gbop_entries ADD COLUMN part_feed BOOLEAN NOT NULL DEFAULT FALSE;

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
ALTER TABLE template.gbop_processes ADD COLUMN vpps_part TEXT    NOT NULL DEFAULT '';
ALTER TABLE template.gbop_processes ADD COLUMN part_feed BOOLEAN NOT NULL DEFAULT FALSE;

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
ALTER TABLE template.gbop_operations ADD COLUMN vpps_part TEXT    NOT NULL DEFAULT '';
ALTER TABLE template.gbop_operations ADD COLUMN part_feed BOOLEAN NOT NULL DEFAULT FALSE;

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

-- ── 工艺元素库 BC ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS template.vpps_tools (
    gid                TEXT PRIMARY KEY,
    vpps               TEXT,
    name               TEXT NOT NULL DEFAULT '',
    gun_model          TEXT NOT NULL DEFAULT '',
    matou_part_no      TEXT NOT NULL DEFAULT '',
    importance         TEXT NOT NULL DEFAULT '',
    gun_type           TEXT NOT NULL DEFAULT '',
    wireless           TEXT NOT NULL DEFAULT '',
    output_square      TEXT NOT NULL DEFAULT '',
    torque_min         TEXT NOT NULL DEFAULT '',
    torque_recommended TEXT NOT NULL DEFAULT '',
    cad_model_no       TEXT NOT NULL DEFAULT '',
    socket_model       TEXT NOT NULL DEFAULT '',
    fastener_type      TEXT NOT NULL DEFAULT '',
    fastener_params    TEXT NOT NULL DEFAULT '',
    extension_model    TEXT NOT NULL DEFAULT '',
    socket_cad_no      TEXT NOT NULL DEFAULT '',
    extension_cad_no   TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    spec       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vpps_tools_vpps ON template.vpps_tools(vpps) WHERE vpps IS NOT NULL;

CREATE TABLE IF NOT EXISTS template.vpps_equipments (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    spec       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS template.vpps_fixtures (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    spec       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS template.fastener_spec (
    gid              TEXT PRIMARY KEY,
    fastener_type    TEXT NOT NULL DEFAULT '',
    part_no          TEXT NOT NULL DEFAULT '',
    name             TEXT NOT NULL DEFAULT '',
    thread_spec      TEXT NOT NULL DEFAULT '',
    model            TEXT NOT NULL DEFAULT '',
    shank_length     TEXT NOT NULL DEFAULT '',
    guide_type       TEXT NOT NULL DEFAULT '',
    guide_length     TEXT NOT NULL DEFAULT '',
    has_adhesive     TEXT NOT NULL DEFAULT '',
    drive_size       TEXT NOT NULL DEFAULT '',
    flange_diameter  TEXT NOT NULL DEFAULT '',
    first_vehicle    TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    meta       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS template.vpps_parts (
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
    team_id          TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vpps_parts_vpps ON template.vpps_parts(vpps) WHERE vpps IS NOT NULL;

ALTER TABLE template.vpps_parts ADD COLUMN flex_type             TEXT NOT NULL DEFAULT '待定';
ALTER TABLE template.vpps_parts ADD COLUMN ref_main_vpps         TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN ref_main_vpps_desc    TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN ref_install_direction TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN ref_static_clearance  TEXT NOT NULL DEFAULT '';
ALTER TABLE template.vpps_parts ADD COLUMN ref_install_clearance TEXT NOT NULL DEFAULT '';

-- ── 工厂资源 BC ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS factory.factory_tools (
    gid           TEXT PRIMARY KEY,
    asset_no      TEXT NOT NULL UNIQUE,
    template_gid  TEXT REFERENCES template.vpps_tools(gid) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'in_use',   -- in_use/maintenance/scrapped
    team_id       TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS factory.factory_equipments (
    gid           TEXT PRIMARY KEY,
    asset_no      TEXT NOT NULL UNIQUE,
    template_gid  TEXT REFERENCES template.vpps_equipments(gid) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'in_use',
    team_id       TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS factory.factory_fixtures (
    gid           TEXT PRIMARY KEY,
    asset_no      TEXT NOT NULL UNIQUE,
    template_gid  TEXT REFERENCES template.vpps_fixtures(gid) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'in_use',
    team_id       TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── 关注 BC ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS work.follows (
    gid        TEXT PRIMARY KEY,
    user_gid   TEXT NOT NULL REFERENCES auth.users(gid) ON DELETE CASCADE,
    item_type  TEXT NOT NULL,   -- task|issue|project|knowledge|rule|std_op|work_plan
    item_gid   TEXT NOT NULL,
    item_title TEXT NOT NULL DEFAULT '',
    notify_on  TEXT NOT NULL DEFAULT 'key_changes',  -- all|key_changes|none
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_gid, item_type, item_gid)
);

CREATE INDEX IF NOT EXISTS idx_follows_user      ON work.follows (user_gid);
CREATE INDEX IF NOT EXISTS idx_follows_item      ON work.follows (item_type, item_gid);


-- ── 通知 BC ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS work.notifications (
    gid        TEXT PRIMARY KEY,
    user_gid   TEXT NOT NULL REFERENCES auth.users(gid) ON DELETE CASCADE,
    type       TEXT NOT NULL,   -- scope_approved|scope_rejected|item_status|new_follower
    item_type  TEXT DEFAULT NULL,
    item_gid   TEXT DEFAULT NULL,
    title      TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    is_read    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_user_unread ON work.notifications (user_gid, is_read);


-- ══════════════════════════════════════════════════════════════
-- BOP 画布新增表（工厂布局 + BOP 五层结构）
-- ══════════════════════════════════════════════════════════════

-- ── 物理工厂 ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS factory.factories (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    team_id    TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    meta       JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 工段（物理区域）
CREATE TABLE IF NOT EXISTS factory.factory_sections (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    factory_gid TEXT NOT NULL REFERENCES factory.factories(gid) ON DELETE CASCADE,
    sort_order  INT  NOT NULL DEFAULT 0,
    color       TEXT NOT NULL DEFAULT '#7287fd',
    canvas_x    REAL NOT NULL DEFAULT 0,
    canvas_y    REAL NOT NULL DEFAULT 0,
    canvas_w    REAL NOT NULL DEFAULT 400,
    canvas_h    REAL NOT NULL DEFAULT 300,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 工位（物理站位，每条记录独立：TB01L / TB01R 等）
CREATE TABLE IF NOT EXISTS factory.factory_stations (
    gid                 TEXT PRIMARY KEY,
    code                TEXT NOT NULL DEFAULT '',
    name                TEXT NOT NULL DEFAULT '',
    factory_section_gid TEXT NOT NULL REFERENCES factory.factory_sections(gid) ON DELETE CASCADE,
    canvas_x            REAL NOT NULL DEFAULT 0,
    canvas_y            REAL NOT NULL DEFAULT 0,
    takt_time           REAL NOT NULL DEFAULT 60,
    height_mm           INT  NOT NULL DEFAULT 1200,
    meta                JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_factory_stations_section ON factory.factory_stations (factory_section_gid);

-- ── BOP 版本 ──────────────────────────────────────────────────

-- BOP 版本（对应一个项目+车型+工厂的组合）
CREATE TABLE IF NOT EXISTS bop.bop_versions (
    gid               TEXT PRIMARY KEY,
    project_gid       TEXT REFERENCES proj.projects(gid) ON DELETE CASCADE,
    factory_gid       TEXT REFERENCES factory.factories(gid) ON DELETE SET NULL,
    vehicle_model_gid TEXT REFERENCES proj.vehicle_models(gid) ON DELETE SET NULL,
    version_tag       TEXT NOT NULL DEFAULT '',
    maturity          TEXT NOT NULL DEFAULT 'concept',  -- concept/pre_series/production
    takt_time         REAL NOT NULL DEFAULT 60,
    status            TEXT NOT NULL DEFAULT 'draft',    -- draft/locked/released
    meta              JSONB NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at        TIMESTAMPTZ DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_bop_versions_project ON bop.bop_versions (project_gid);
CREATE INDEX IF NOT EXISTS idx_bop_versions_factory ON bop.bop_versions (factory_gid);

-- 工厂布局模板（产线积木库：可保存一组工位的相对坐标）
CREATE TABLE IF NOT EXISTS factory.factory_layout_templates (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    factory_gid TEXT REFERENCES factory.factories(gid) ON DELETE CASCADE,
    team_id     TEXT REFERENCES auth.teams(gid) ON DELETE SET NULL,
    -- [{code, name, rel_x, rel_y, takt_time, height_mm}]
    stations    JSONB NOT NULL DEFAULT '[]',
    meta        JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_layout_tpl_factory ON factory.factory_layout_templates (factory_gid);

-- ── 用户自定义视图配置 ──────────────────────────────────────────
-- 通用视图：字段显隐/顺序、筛选条件、排序，可保存/复制/重命名
-- list_gid NOT NULL 时为清单子视图；NULL 时为模块全局视图
CREATE TABLE IF NOT EXISTS app.view_configs (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '未命名视图',
    module     TEXT NOT NULL DEFAULT '',  -- 模块标识 e.g. 'task_list', 'issue_list'
    list_gid   TEXT DEFAULT NULL,         -- 所属清单 gid；NULL = 全局模块视图
    owner_gid  TEXT NOT NULL DEFAULT '',  -- 用户 gid（空 = 本地/匿名）
    is_shared  BOOLEAN NOT NULL DEFAULT FALSE,
    -- {columns:[{key,visible,order,width}], filters:[{id,field,op,value}], sorts:[{field,dir}]}
    config     JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_view_configs_owner    ON app.view_configs (owner_gid);
CREATE INDEX IF NOT EXISTS idx_view_configs_module   ON app.view_configs (module);
CREATE INDEX IF NOT EXISTS idx_view_configs_list_gid ON app.view_configs (list_gid);
-- 已有实例需执行：
ALTER TABLE app.view_configs ADD COLUMN list_gid TEXT DEFAULT NULL;

-- ── 导出模板配置表 ──────────────────────────────────────────────
-- 存储各模块的 Excel 导出样式模板（JSON 配置，CSS 模拟预览）
CREATE TABLE IF NOT EXISTS app.export_templates (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    module     TEXT NOT NULL DEFAULT '',   -- 'factory_resource' | 'craft_table' | 'issue' | '*'（通用）
    owner_gid  TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    is_shared  BOOLEAN NOT NULL DEFAULT FALSE,
    -- {columns:[{key,label,width,include}], styles:{headerBg,headerFg,altRowBg,borderStyle,fontSize}}
    config     JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_export_templates_module ON app.export_templates (module);
CREATE INDEX IF NOT EXISTS idx_export_templates_owner  ON app.export_templates (owner_gid);


-- ══════════════════════════════════════════════════════════════
-- 任务 & 问题表（本地⇄云端提升引擎）
-- 本地 SQLite 表结构镜像，额外新增 owner_user_gid（提升者飞书 gid）
-- ══════════════════════════════════════════════════════════════

-- display_id 序列（人类可读 ID：T-00000001 / I-00000001 / S-00000001）
CREATE SEQUENCE IF NOT EXISTS work.tasks_display_seq      START 1;
CREATE SEQUENCE IF NOT EXISTS work.issues_display_seq     START 1;
-- template.std_op_display_seq 已废弃（GBOP V2 不使用序列）
-- 以下序列在 bop_schema_v2.sql 中也有，但 rules 表在 schema.sql 中使用，故此处同步创建
CREATE SEQUENCE IF NOT EXISTS knowledge.rules_display_seq START 1;

CREATE TABLE IF NOT EXISTS work.lists (
    gid           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    color         TEXT NOT NULL DEFAULT '#5b8dee',
    storage_scope TEXT NOT NULL DEFAULT 'cloud',
    owner_type    TEXT NOT NULL DEFAULT 'user',    -- user | team
    owner_gid     TEXT NOT NULL DEFAULT '',
    creator_gid   TEXT NOT NULL DEFAULT '',
    item_type     TEXT NOT NULL DEFAULT 'task',    -- task | issue | knowledge | rule
    sort_order    INTEGER NOT NULL DEFAULT 0,
    visibility    TEXT NOT NULL DEFAULT 'team',    -- private | team | public
    deleted_at    TIMESTAMPTZ DEFAULT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lists_owner ON work.lists (owner_type, owner_gid);
CREATE INDEX IF NOT EXISTS idx_lists_item_type ON work.lists (item_type);

-- 为已有 lists 表补列（新环境 CREATE TABLE 已含这些列，旧 DB 需手动执行）
ALTER TABLE work.lists ADD COLUMN item_type     TEXT NOT NULL DEFAULT 'task';
ALTER TABLE work.lists ADD COLUMN creator_gid   TEXT NOT NULL DEFAULT '';
ALTER TABLE work.lists ADD COLUMN deleted_at    TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE work.lists ADD COLUMN visibility    TEXT NOT NULL DEFAULT 'team'; -- private | project | team | public
ALTER TABLE work.lists ADD COLUMN storage_scope TEXT NOT NULL DEFAULT 'cloud';
ALTER TABLE work.lists ADD COLUMN project_gid   TEXT DEFAULT NULL;
ALTER TABLE work.lists ADD COLUMN read_scope    TEXT DEFAULT NULL;
ALTER TABLE work.lists ADD COLUMN write_scope   TEXT DEFAULT NULL;

CREATE TABLE IF NOT EXISTS work.tasks (
    gid                 TEXT PRIMARY KEY,
    display_id          TEXT NOT NULL DEFAULT '',       -- 人类可读 ID，如 T-00000001
    title               TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    owner_gid           TEXT NOT NULL DEFAULT '',       -- 本地 owner 标识（保留原始值）
    owner_user_gid      TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,  -- 提升者飞书 gid
    assignee_team_gid   TEXT DEFAULT NULL,
    project_gid         TEXT REFERENCES proj.projects(gid) ON DELETE SET NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    priority            TEXT NOT NULL DEFAULT 'normal',
    source_ref          JSONB NOT NULL DEFAULT '{}',
    review_date         TEXT DEFAULT NULL,
    meeting_level       TEXT NOT NULL DEFAULT 'none',
    meeting_doc_link    TEXT DEFAULT NULL,
    progress_logs       JSONB NOT NULL DEFAULT '[]',
    due_date            TEXT DEFAULT NULL,
    plan_start          TEXT DEFAULT NULL,
    plan_end            TEXT DEFAULT NULL,
    actual_start        TEXT DEFAULT NULL,
    actual_end          TEXT DEFAULT NULL,
    share_scope         TEXT NOT NULL DEFAULT 'project',  -- project|team|global
    list_gid            TEXT DEFAULT NULL REFERENCES work.lists(gid) ON DELETE SET NULL,
    attachments         JSONB NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_owner      ON work.tasks (owner_user_gid);
CREATE INDEX IF NOT EXISTS idx_tasks_project    ON work.tasks (project_gid);
CREATE INDEX IF NOT EXISTS idx_tasks_status     ON work.tasks (status);


CREATE TABLE IF NOT EXISTS work.issues (
    gid                   TEXT PRIMARY KEY,
    display_id            TEXT NOT NULL DEFAULT '',       -- 人类可读 ID，如 I-00000001
    title                 TEXT NOT NULL DEFAULT '',
    description           TEXT NOT NULL DEFAULT '',
    severity              TEXT NOT NULL DEFAULT 'low',
    status                TEXT NOT NULL DEFAULT 'open',
    owner_gid             TEXT NOT NULL DEFAULT '',
    owner_user_gid        TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    assignee_team_gid     TEXT DEFAULT NULL,
    project_gid           TEXT REFERENCES proj.projects(gid) ON DELETE SET NULL,
    tracking_refs         JSONB NOT NULL DEFAULT '[]',
    occurrence_root_cause TEXT DEFAULT NULL,
    escape_root_cause     TEXT DEFAULT NULL,
    interim_action        TEXT DEFAULT NULL,
    permanent_action      TEXT DEFAULT NULL,
    source_ref            JSONB NOT NULL DEFAULT '{}',
    related_task_gid      TEXT DEFAULT NULL,
    related_knowledge_gid TEXT DEFAULT NULL,
    approval_order_gid    TEXT DEFAULT NULL,
    bop_entry_gid         TEXT DEFAULT NULL,
    share_scope           TEXT NOT NULL DEFAULT 'project',
    list_gid              TEXT DEFAULT NULL REFERENCES work.lists(gid) ON DELETE SET NULL,
    attachments           JSONB NOT NULL DEFAULT '[]',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issues_owner   ON work.issues (owner_user_gid);
CREATE INDEX IF NOT EXISTS idx_issues_project ON work.issues (project_gid);
CREATE INDEX IF NOT EXISTS idx_issues_status  ON work.issues (status);


-- ══════════════════════════════════════════════════════════════
-- follows.notify_on 迁移（TEXT → JSONB 数组）
-- ⚠️ 已有 follows 表需手动执行以下迁移语句：
--   ALTER TABLE work.follows ALTER COLUMN notify_on TYPE JSONB
--     USING CASE
--       WHEN notify_on ~ '^\\[' THEN notify_on::JSONB
--       ELSE jsonb_build_array(notify_on)
--     END;
-- ══════════════════════════════════════════════════════════════

-- ── 任务模板（项目标准内容清单实例化） ──────────────────────────

CREATE TABLE IF NOT EXISTS work.task_templates (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    scope       TEXT NOT NULL DEFAULT 'system',   -- system|team|personal
    owner_gid   TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS work.task_template_items (
    gid              TEXT PRIMARY KEY,
    template_gid     TEXT NOT NULL REFERENCES work.task_templates(gid) ON DELETE CASCADE,
    title_pattern    TEXT NOT NULL,          -- 支持 {{project_name}} {{project_code}} 变量
    description      TEXT NOT NULL DEFAULT '',
    priority         TEXT NOT NULL DEFAULT 'normal',
    assignee_role    TEXT DEFAULT NULL,      -- 角色占位，实例化时映射到具体人
    due_offset_days  INTEGER DEFAULT NULL,   -- 相对项目开始日的偏移天数，NULL=无截止日
    share_scope      TEXT NOT NULL DEFAULT 'team',
    sort_order       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tti_template ON work.task_template_items (template_gid);

-- ── 多工作台配置表 ───────────────────────────────────────────────

-- 工作台配置（个人 or 团队，每个 owner 最多 3 个）
CREATE TABLE IF NOT EXISTS app.workbench_configs (
    gid         TEXT PRIMARY KEY,
    owner_type  TEXT NOT NULL DEFAULT 'user',   -- 'user' | 'team'
    owner_gid   TEXT NOT NULL,                  -- user_gid or team_gid
    name        TEXT NOT NULL DEFAULT '工作台',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    widgets     JSONB NOT NULL DEFAULT '[]',    -- [{id, type, config}]
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wb_configs_owner ON app.workbench_configs (owner_type, owner_gid);

-- 团队工作台的成员个性化覆盖
CREATE TABLE IF NOT EXISTS app.workbench_member_overrides (
    gid             TEXT PRIMARY KEY,
    workbench_gid   TEXT NOT NULL REFERENCES app.workbench_configs(gid) ON DELETE CASCADE,
    user_gid        TEXT NOT NULL REFERENCES auth.users(gid) ON DELETE CASCADE,
    widgets         JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workbench_gid, user_gid)
);
CREATE INDEX IF NOT EXISTS idx_wb_overrides_wb   ON app.workbench_member_overrides (workbench_gid);
CREATE INDEX IF NOT EXISTS idx_wb_overrides_user ON app.workbench_member_overrides (user_gid);

-- 为 work.tasks / work.issues 添加 list_gid 列（已有数据库执行以下迁移）
ALTER TABLE work.tasks  ADD COLUMN list_gid TEXT DEFAULT NULL;
ALTER TABLE work.issues ADD COLUMN list_gid TEXT DEFAULT NULL;

-- display_id 迁移（已有数据库）
ALTER TABLE work.tasks           ADD COLUMN display_id TEXT NOT NULL DEFAULT '';
ALTER TABLE work.issues          ADD COLUMN display_id TEXT NOT NULL DEFAULT '';
ALTER TABLE template.gbop        ADD COLUMN display_id TEXT NOT NULL DEFAULT '';

-- BOP entries：字段重构（与 bop_schema_v2.sql 保持同步，幂等）
ALTER TABLE bop.bop_entries ADD COLUMN ai00_level       SMALLINT;
ALTER TABLE bop.bop_entries ADD COLUMN title            TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN bom_row_owner    TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN parent_bop_label TEXT;

-- ══════════════════════════════════════════════════════════════
-- 流程引擎（Flow Engine）— flows + flow_runs
-- ══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS app.flows (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    flowdef     TEXT NOT NULL DEFAULT '',   -- YAML 字符串
    status      TEXT NOT NULL DEFAULT 'draft',  -- draft|active|archived
    last_run_at TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flows_status ON app.flows (status);

CREATE TABLE IF NOT EXISTS app.flow_runs (
    gid             TEXT PRIMARY KEY,
    flow_gid        TEXT NOT NULL REFERENCES app.flows(gid) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|running|paused|completed|failed
    mode            TEXT NOT NULL DEFAULT 'auto',      -- auto|step
    current_node_id TEXT,
    context_data    JSONB NOT NULL DEFAULT '{}',
    error_msg       TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_flow_runs_flow ON app.flow_runs (flow_gid);

-- ── 工作台标注数据（wb_annotations）─────────────────────────────────────────
-- key 格式：wb:ann:{gid}（与前端 localStorage key 相同）

CREATE TABLE IF NOT EXISTS app.wb_annotations (
    key        TEXT PRIMARY KEY,
    data       TEXT NOT NULL DEFAULT '{}',   -- JSON 字符串
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 开发看板归档（bug_tracker_snapshots）─────────────────────────────────────
-- dev/sync_tracker_to_pg.py 每天同步 dev/bug_tracker.json → 此表

CREATE TABLE IF NOT EXISTS app.bug_tracker_snapshots (
    id           TEXT PRIMARY KEY,                    -- 0000037 等
    title        TEXT NOT NULL DEFAULT '',
    type         TEXT NOT NULL DEFAULT 'bug',
    priority     TEXT NOT NULL DEFAULT 'P1-高',
    status       TEXT NOT NULL DEFAULT '待处理',
    ai_status    TEXT NOT NULL DEFAULT '待处理',
    user_confirm TEXT NOT NULL DEFAULT '待确认',
    module       TEXT NOT NULL DEFAULT '',
    ui_id        TEXT NOT NULL DEFAULT '',
    page         TEXT NOT NULL DEFAULT '',
    files        TEXT NOT NULL DEFAULT '',
    seq          INT,
    detail       TEXT NOT NULL DEFAULT '',
    comment      TEXT NOT NULL DEFAULT '',
    ai_question  TEXT NOT NULL DEFAULT '',
    commit       TEXT NOT NULL DEFAULT '',
    links        JSONB NOT NULL DEFAULT '[]',
    history      TEXT NOT NULL DEFAULT '',
    entries      JSONB NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    synced_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ══════════════════════════════════════════════════════════════════════════════
-- item_entries：条目沟通历史表（独立于清单表，按 (item_type, item_gid) 绑定）
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS work.item_entries (
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
);
CREATE INDEX IF NOT EXISTS idx_item_entries_item ON work.item_entries (item_type, item_gid);
CREATE INDEX IF NOT EXISTS idx_item_entries_parent ON work.item_entries (parent_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- knowledge_entries：知识条目表（云端 PG）
-- ══════════════════════════════════════════════════════════════════════════════
CREATE SEQUENCE IF NOT EXISTS knowledge.knowledge_display_seq START 1;

CREATE TABLE IF NOT EXISTS knowledge.knowledge_entries (
    gid                    TEXT PRIMARY KEY,
    display_id             TEXT NOT NULL DEFAULT '',
    title                  TEXT NOT NULL DEFAULT '',
    entry_type             TEXT NOT NULL DEFAULT 'guide',       -- guide|rule_basis|sim_spec|lesson_learned
    status                 TEXT NOT NULL DEFAULT 'draft',       -- draft|published|archived
    share_scope            TEXT NOT NULL DEFAULT 'team',
    list_gid               TEXT DEFAULT NULL,
    source_gid             TEXT DEFAULT NULL,
    source_label           TEXT DEFAULT '',
    maintainer_gid         TEXT DEFAULT '',
    contributors           JSONB NOT NULL DEFAULT '[]',
    attachments            JSONB NOT NULL DEFAULT '[]',
    tags                   JSONB NOT NULL DEFAULT '[]',
    content_ref            JSONB NOT NULL DEFAULT '{}',
    related_part_nos       JSONB NOT NULL DEFAULT '[]',
    related_operation_gids JSONB NOT NULL DEFAULT '[]',
    creator_gid            TEXT DEFAULT '',
    source_project_gid     TEXT DEFAULT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_list ON knowledge.knowledge_entries (list_gid);
CREATE INDEX IF NOT EXISTS idx_knowledge_entries_type ON knowledge.knowledge_entries (entry_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_entries_status ON knowledge.knowledge_entries (status);

-- ══════════════════════════════════════════════════════════════════════════════
-- 知识库模块（knowledge_hub）— 公共/团队知识库（云端 PG）
-- ══════════════════════════════════════════════════════════════════════════════

-- 知识库文件夹
CREATE TABLE IF NOT EXISTS knowledge.knowledge_folders (
  gid         TEXT PRIMARY KEY,
  parent_gid  TEXT DEFAULT NULL,
  scope_type  TEXT NOT NULL DEFAULT 'personal',   -- public|team|personal
  team_gid    TEXT DEFAULT NULL,
  name        TEXT NOT NULL DEFAULT '',
  sort_order  INTEGER NOT NULL DEFAULT 0,
  creator_gid TEXT DEFAULT '',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 知识条目（文件）
CREATE TABLE IF NOT EXISTS knowledge.knowledge_items (
  gid          TEXT PRIMARY KEY,
  folder_gid   TEXT DEFAULT NULL,
  scope_type   TEXT NOT NULL DEFAULT 'personal',  -- public|team|personal
  team_gid     TEXT DEFAULT NULL,
  item_type    TEXT NOT NULL DEFAULT 'richtext',   -- richtext|markdown|pdf|weblink|site_page|spreadsheet|image
  title        TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL DEFAULT 'draft',      -- draft|published|archived
  content_body JSONB DEFAULT NULL,                 -- TipTap JSON
  content_md   TEXT DEFAULT '',
  file_path    TEXT DEFAULT '',
  url          TEXT DEFAULT '',
  site_ref     JSONB DEFAULT NULL,
  tags         JSONB DEFAULT '[]',
  is_system    BOOLEAN NOT NULL DEFAULT FALSE,     -- 系统内置条目，非超管不可删
  creator_gid  TEXT DEFAULT '',
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- knowledge_items 新增置顶 / 隐藏字段
ALTER TABLE knowledge.knowledge_items ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE knowledge.knowledge_items ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE;

-- 收藏
CREATE TABLE IF NOT EXISTS knowledge.knowledge_favorites (
  user_gid   TEXT NOT NULL,
  item_gid   TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_gid, item_gid)
);

-- 最近访问
CREATE TABLE IF NOT EXISTS knowledge.knowledge_recent (
  user_gid    TEXT NOT NULL,
  item_gid    TEXT NOT NULL,
  accessed_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_gid, item_gid)
);

-- 规则条目（云端 PG）
CREATE TABLE IF NOT EXISTS knowledge.craft_rules (
    gid                  TEXT PRIMARY KEY,
    display_id           TEXT NOT NULL DEFAULT '',
    code                 TEXT NOT NULL DEFAULT '',
    name                 TEXT NOT NULL DEFAULT '',
    rule_type            TEXT NOT NULL DEFAULT 'other',
    enforcement_level    TEXT NOT NULL DEFAULT 'advisory',
    rule_definition      JSONB NOT NULL DEFAULT '{}',
    applicable_scope     JSONB NOT NULL DEFAULT '{}',
    status               TEXT NOT NULL DEFAULT 'draft',
    knowledge_source_gid TEXT DEFAULT NULL,
    share_scope          TEXT NOT NULL DEFAULT 'team',
    list_gid             TEXT DEFAULT NULL,
    attachments          JSONB NOT NULL DEFAULT '[]',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_craft_rules_status ON knowledge.craft_rules (status);
CREATE INDEX IF NOT EXISTS idx_craft_rules_scope  ON knowledge.craft_rules (share_scope);
CREATE INDEX IF NOT EXISTS idx_craft_rules_list   ON knowledge.craft_rules (list_gid) WHERE list_gid IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kfolders_scope ON knowledge.knowledge_folders (scope_type, team_gid);
CREATE INDEX IF NOT EXISTS idx_kitems_folder  ON knowledge.knowledge_items (folder_gid);
CREATE INDEX IF NOT EXISTS idx_kitems_scope   ON knowledge.knowledge_items (scope_type);

-- ── 系统内置条目 seed（幂等 INSERT）────────────────────────────────────────────
-- "项目信息"页面：公共知识库根目录，置顶，仅超管可删
INSERT INTO knowledge.knowledge_items (
    gid, folder_gid, scope_type, team_gid, item_type, title, status,
    site_ref, is_system, creator_gid, created_at, updated_at
) VALUES (
    'system-project-info',
    NULL, 'public', NULL, 'site_page', '项目信息', 'published',
    '{"path": "knowledge_hub/pages/project_info.html", "label": "项目信息"}'::jsonb,
    TRUE, 'system', NOW(), NOW()
) ON CONFLICT (gid) DO NOTHING;

-- ── vpps_part + part_feed（工序/操作所针对的零件 + 是否涉及上料）──────────────
ALTER TABLE bop.bop_entries ADD COLUMN vpps_part TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_entries ADD COLUMN part_feed BOOLEAN NOT NULL DEFAULT FALSE;

-- ── catia_occurrence_name + parent_vpps_name（TC CSV 扩展列）──────────────────
-- catia_occurrence_name：零件节点专用，来自 CATIA 装配树实例名称
ALTER TABLE bop.bop_entries ADD COLUMN catia_occurrence_name TEXT NOT NULL DEFAULT '';
-- parent_vpps_name：父级 VPPS 描述名称（CSV "父级VPPS名称" 列）
ALTER TABLE bop.bop_entries ADD COLUMN parent_vpps_name TEXT NOT NULL DEFAULT '';

-- ── 现有数据库新字段迁移（已有 DB 手动或重建时执行）──────────────────────────
-- proj.projects 表新增字段：
ALTER TABLE proj.projects ADD COLUMN project_code TEXT NOT NULL DEFAULT '';
ALTER TABLE proj.projects ADD COLUMN model_year   INTEGER;
ALTER TABLE proj.projects ADD COLUMN suffix       TEXT NOT NULL DEFAULT '';
ALTER TABLE proj.projects ADD COLUMN jph          REAL;
ALTER TABLE proj.projects ADD COLUMN is_deleted   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE proj.projects ADD COLUMN is_archived  BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE proj.projects ADD COLUMN deleted_at   TIMESTAMPTZ;
ALTER TABLE proj.projects ADD COLUMN archived_at  TIMESTAMPTZ;

-- knowledge.knowledge_items 表新增 is_system 字段：
ALTER TABLE knowledge.knowledge_items ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT FALSE;
-- 补插系统条目（若 ALTER 之前 INSERT 未执行）：
INSERT INTO knowledge.knowledge_items (
    gid, folder_gid, scope_type, team_gid, item_type, title, status,
    site_ref, is_system, creator_gid, created_at, updated_at
) VALUES (
    'system-project-info',
    NULL, 'public', NULL, 'site_page', '项目信息', 'published',
    '{"path": "knowledge_hub/pages/project_info.html", "label": "项目信息"}'::jsonb,
    TRUE, 'system', NOW(), NOW()
) ON CONFLICT (gid) DO NOTHING;

-- ── AI 工具调用审计日志（云端 PG，供超管回滚查询）──────────────────────────────
CREATE TABLE IF NOT EXISTS app.ai_audit_logs (
    id            BIGSERIAL PRIMARY KEY,
    gid           TEXT UNIQUE NOT NULL,
    session_gid   TEXT NOT NULL,
    user_gid      TEXT DEFAULT '',
    tool_name     TEXT NOT NULL,
    is_write      BOOLEAN DEFAULT FALSE,
    is_confirmed  BOOLEAN DEFAULT FALSE,
    inputs_json   TEXT DEFAULT '{}',
    result_json   TEXT DEFAULT '{}',
    resource_gid  TEXT DEFAULT '',
    resource_type TEXT DEFAULT '',
    status        TEXT DEFAULT 'ok',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_audit_logs_session ON app.ai_audit_logs (session_gid);
CREATE INDEX IF NOT EXISTS idx_ai_audit_logs_user    ON app.ai_audit_logs (user_gid);
CREATE INDEX IF NOT EXISTS idx_ai_audit_logs_created ON app.ai_audit_logs (created_at DESC);

-- ── pgvector 向量语义搜索（需手动在 DBeaver 执行）──────────────────────────────
-- 前提：目标 PostgreSQL 实例已安装 pgvector 扩展（CREATE EXTENSION vector）
--
-- Step 1：启用扩展
-- CREATE EXTENSION IF NOT EXISTS vector;
--
-- Step 2：knowledge_entries 表追加 embedding 列（维度与 embed_model 匹配，默认 768）
-- ALTER TABLE knowledge.knowledge_entries ADD COLUMN embedding vector(768);
--
-- Step 3：创建 IVFFlat 近似索引（先写入足够数据再执行，空表建索引无意义）
-- CREATE INDEX IF NOT EXISTS idx_ke_embedding
--   ON knowledge.knowledge_entries
--   USING ivfflat (embedding vector_cosine_ops)
--   WITH (lists = 100);
--
-- 写入方式：在知识条目创建/更新后，通过 embedding_service.compute_embedding() 计算向量，
-- 再 PATCH /api/knowledge_entries/{gid} 更新 embedding 字段（或后端直接 UPDATE）。
-- POST /api/knowledge_entries/vector-search 端点已实现云端向量搜索（见 backend/routers/knowledge.py）。

-- ── tasks / issues（任务与问题，现役表，schema = proj）────────────────────────
-- work.tasks / work.issues 为旧表，已废弃，此处以 proj schema 为准

-- display_id 序列（T-C00000001 格式）
CREATE SEQUENCE IF NOT EXISTS proj.tasks_display_seq  START 1;
CREATE SEQUENCE IF NOT EXISTS proj.issues_display_seq START 1;

CREATE TABLE IF NOT EXISTS proj.tasks (
    gid                  TEXT PRIMARY KEY,
    display_id           TEXT NOT NULL DEFAULT '',
    title                TEXT NOT NULL DEFAULT '',
    description          TEXT NOT NULL DEFAULT '',
    owner_gid            TEXT NOT NULL DEFAULT '',
    owner_user_gid       TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    assignee_team_gid    TEXT DEFAULT NULL,
    project_gid          TEXT REFERENCES proj.projects(gid) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT 'pending',
    priority             TEXT NOT NULL DEFAULT 'normal',
    source_ref           JSONB NOT NULL DEFAULT '{}',
    review_date          TEXT DEFAULT NULL,
    meeting_level        TEXT NOT NULL DEFAULT 'none',
    meeting_doc_link     TEXT DEFAULT NULL,
    progress_logs        JSONB NOT NULL DEFAULT '[]',
    due_date             TEXT DEFAULT NULL,
    plan_start           TEXT DEFAULT NULL,
    plan_end             TEXT DEFAULT NULL,
    actual_start         TEXT DEFAULT NULL,
    actual_end           TEXT DEFAULT NULL,
    share_scope          TEXT NOT NULL DEFAULT 'project',
    list_gid             TEXT DEFAULT NULL,
    attachments          JSONB NOT NULL DEFAULT '[]',
    -- 软删除
    is_deleted           BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at           TIMESTAMPTZ DEFAULT NULL,
    -- 时间线
    scheduled_date       DATE DEFAULT NULL,
    scheduled_start_time TIME DEFAULT NULL,
    time_estimate        INTEGER DEFAULT NULL,
    -- 画布视图
    parent_task_gid      TEXT DEFAULT NULL,
    canvas_x             REAL DEFAULT NULL,
    canvas_y             REAL DEFAULT NULL,
    completion           INTEGER NOT NULL DEFAULT 0,
    node_type            TEXT NOT NULL DEFAULT 'normal',
    canvas_icon          TEXT NOT NULL DEFAULT 'star',
    canvas_row_gid       TEXT DEFAULT NULL,
    canvas_col_gid       TEXT DEFAULT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proj_tasks_owner   ON proj.tasks (owner_user_gid);
CREATE INDEX IF NOT EXISTS idx_proj_tasks_project ON proj.tasks (project_gid);
CREATE INDEX IF NOT EXISTS idx_proj_tasks_list    ON proj.tasks (list_gid);
CREATE INDEX IF NOT EXISTS idx_proj_tasks_status  ON proj.tasks (status);
CREATE INDEX IF NOT EXISTS idx_proj_tasks_deleted ON proj.tasks (deleted_at) WHERE deleted_at IS NOT NULL;

-- ── tasks 补字段（2026-05-25）⚠️ 已有数据库需手动在 DBeaver 执行 ──────────────
-- 基础字段（旧表可能缺失）
ALTER TABLE proj.tasks ADD COLUMN list_gid      TEXT DEFAULT NULL;
-- 软删除
ALTER TABLE proj.tasks ADD COLUMN is_deleted   BOOLEAN     NOT NULL DEFAULT FALSE;
ALTER TABLE proj.tasks ADD COLUMN deleted_at   TIMESTAMPTZ DEFAULT NULL;
-- 时间线
ALTER TABLE proj.tasks ADD COLUMN scheduled_date       DATE    DEFAULT NULL;
ALTER TABLE proj.tasks ADD COLUMN scheduled_start_time TIME    DEFAULT NULL;
ALTER TABLE proj.tasks ADD COLUMN time_estimate        INTEGER DEFAULT NULL;

-- ── 任务画布视图字段补充（2026-05-24）──────────────────────────────────────────
-- ⚠️ 已有数据库需手动在 DBeaver 执行
ALTER TABLE proj.tasks ADD COLUMN parent_task_gid TEXT DEFAULT NULL;
ALTER TABLE proj.tasks ADD COLUMN canvas_x        REAL DEFAULT NULL;
ALTER TABLE proj.tasks ADD COLUMN canvas_y        REAL DEFAULT NULL;
ALTER TABLE proj.tasks ADD COLUMN completion      INTEGER NOT NULL DEFAULT 0;
ALTER TABLE proj.tasks ADD COLUMN node_type       TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE proj.tasks ADD COLUMN canvas_icon     TEXT NOT NULL DEFAULT 'star';
ALTER TABLE proj.tasks ADD COLUMN canvas_row_gid  TEXT DEFAULT NULL;
ALTER TABLE proj.tasks ADD COLUMN canvas_col_gid  TEXT DEFAULT NULL;

-- ── 任务依赖关系表（用于任务画布连线）────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS proj.task_dependencies (
    gid           TEXT PRIMARY KEY,
    source_gid    TEXT NOT NULL,   -- 前置任务 gid
    target_gid    TEXT NOT NULL,   -- 后置任务 gid
    edge_type     TEXT NOT NULL DEFAULT 'prerequisite',   -- prerequisite/sequence
    dep_condition TEXT NOT NULL DEFAULT 'done',           -- done/started/completion>=50
    dep_group     TEXT DEFAULT NULL,                      -- OR 逻辑分组
    label         TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_task_deps_source ON proj.task_dependencies(source_gid);
CREATE INDEX IF NOT EXISTS idx_task_deps_target ON proj.task_dependencies(target_gid);


-- ── Skill 库（2026-05-28）─────────────────────────────────────────────────────
-- ⚠️ 已有数据库需手动在 DBeaver 执行
CREATE TABLE IF NOT EXISTS app.skills (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    skill_type  TEXT NOT NULL,             -- 'prompt' | 'tool' | 'flow'
    scope       TEXT NOT NULL DEFAULT 'private',  -- 'private' | 'team' | 'global'
    status      TEXT NOT NULL DEFAULT 'draft',    -- 'draft' | 'active' | 'archived'
    owner_gid   TEXT NOT NULL DEFAULT '',
    is_system   BOOLEAN NOT NULL DEFAULT FALSE,
    content     JSONB NOT NULL DEFAULT '{}',
    icon        TEXT NOT NULL DEFAULT '',
    tags        JSONB NOT NULL DEFAULT '[]',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_pinned   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ DEFAULT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_name ON app.skills(name) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_skills_owner ON app.skills(owner_gid);
CREATE INDEX IF NOT EXISTS idx_skills_scope ON app.skills(scope, status);


-- ── 本体编辑器（2026-06-11）──────────────────────────────────────────────────
-- ⚠️ 已有数据库需手动在 DBeaver 执行
CREATE TABLE IF NOT EXISTS knowledge.onto_classes (
    gid              TEXT PRIMARY KEY,
    name             TEXT NOT NULL DEFAULT '',
    label_zh         TEXT NOT NULL DEFAULT '',
    label_en         TEXT NOT NULL DEFAULT '',
    parent_gid       TEXT REFERENCES knowledge.onto_classes(gid) ON DELETE SET NULL,
    node_type_binding TEXT DEFAULT NULL,
    is_abstract      BOOLEAN NOT NULL DEFAULT FALSE,
    color            TEXT DEFAULT NULL,
    icon             TEXT DEFAULT NULL,
    description      TEXT NOT NULL DEFAULT '',
    sort_order       INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_onto_classes_parent  ON knowledge.onto_classes(parent_gid);
CREATE INDEX IF NOT EXISTS idx_onto_classes_binding ON knowledge.onto_classes(node_type_binding);

CREATE TABLE IF NOT EXISTS knowledge.onto_properties (
    gid             TEXT PRIMARY KEY,
    class_gid       TEXT NOT NULL REFERENCES knowledge.onto_classes(gid) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    label_zh        TEXT NOT NULL DEFAULT '',
    prop_kind       TEXT NOT NULL DEFAULT 'data',  -- 'data' | 'object' | 'annotation'
    data_type       TEXT DEFAULT NULL,             -- string/integer/float/boolean/date/enum
    range_class_gid TEXT REFERENCES knowledge.onto_classes(gid) ON DELETE SET NULL,
    enum_values     JSONB NOT NULL DEFAULT '[]',
    required        BOOLEAN NOT NULL DEFAULT FALSE,
    min_val         FLOAT DEFAULT NULL,
    max_val         FLOAT DEFAULT NULL,
    description     TEXT NOT NULL DEFAULT '',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_onto_props_class ON knowledge.onto_properties(class_gid);

CREATE TABLE IF NOT EXISTS knowledge.onto_relations (
    gid              TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    label_zh         TEXT NOT NULL DEFAULT '',
    domain_class_gid TEXT REFERENCES knowledge.onto_classes(gid) ON DELETE CASCADE,
    range_class_gid  TEXT REFERENCES knowledge.onto_classes(gid) ON DELETE SET NULL,
    is_functional    BOOLEAN NOT NULL DEFAULT FALSE,
    inverse_of_gid   TEXT REFERENCES knowledge.onto_relations(gid) ON DELETE SET NULL,
    description      TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge.onto_axioms (
    gid         TEXT PRIMARY KEY,
    class_gid   TEXT NOT NULL REFERENCES knowledge.onto_classes(gid) ON DELETE CASCADE,
    axiom_type  TEXT NOT NULL,  -- 'disjointWith' | 'minCardinality' | 'hasValue'
    target_gid  TEXT DEFAULT NULL,
    expression  TEXT DEFAULT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- craft_rules 扩展：CEL 表达式 + 绑定类
ALTER TABLE knowledge.craft_rules ADD COLUMN expression         TEXT DEFAULT NULL;
ALTER TABLE knowledge.craft_rules ADD COLUMN context_class_gid TEXT DEFAULT NULL;

-- ── 外部数据源集成 ────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS integration;

CREATE TABLE IF NOT EXISTS integration.ext_datasources (
    gid            TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    db_type        TEXT NOT NULL,
    host           TEXT NOT NULL,
    port           INTEGER NOT NULL,
    database       TEXT NOT NULL,
    username       TEXT NOT NULL,
    password_enc   TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'untested',
    last_tested_at TIMESTAMPTZ,
    last_error     TEXT,
    created_by     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS integration.ext_mappings (
    gid               TEXT PRIMARY KEY,
    datasource_gid    TEXT NOT NULL REFERENCES integration.ext_datasources(gid) ON DELETE CASCADE,
    ext_table         TEXT NOT NULL,
    onto_class_gid    TEXT NOT NULL REFERENCES knowledge.onto_classes(gid),
    filter_sql        TEXT,
    unique_key_col    TEXT,
    last_import_at    TIMESTAMPTZ,
    last_import_count INTEGER,
    created_by        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ext_mappings_ds ON integration.ext_mappings(datasource_gid);

CREATE TABLE IF NOT EXISTS integration.ext_field_mappings (
    gid               TEXT PRIMARY KEY,
    mapping_gid       TEXT NOT NULL REFERENCES integration.ext_mappings(gid) ON DELETE CASCADE,
    ext_column        TEXT NOT NULL,
    target_type       TEXT NOT NULL DEFAULT 'property',
    onto_property_gid TEXT REFERENCES knowledge.onto_properties(gid),
    bop_field         TEXT,
    transform_expr    TEXT,
    is_ignored        BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 本体驱动存储重构（2026-06-15）────────────────────────────────────────────
-- onto_classes 加实体表字段，消除 _ENTITY_TABLE_MAP 硬编码
ALTER TABLE knowledge.onto_classes
    ADD COLUMN entity_table TEXT DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_onto_classes_entity_table
    ON knowledge.onto_classes(entity_table) WHERE entity_table IS NOT NULL;

-- onto_properties 加 storage_hint（seed 代码已在读写此字段）
ALTER TABLE knowledge.onto_properties
    ADD COLUMN storage_hint TEXT NOT NULL DEFAULT 'meta';

-- onto_relations 加 link_type_binding（seed 代码已在读写此字段）
ALTER TABLE knowledge.onto_relations
    ADD COLUMN link_type_binding TEXT DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_ext_field_mappings_m ON integration.ext_field_mappings(mapping_gid);

-- ══════════════════════════════════════════════════════════════════════════════
-- 本体层升级 Phase 1：onto_* 表字段完整化
-- 执行时间：2026-06-17
-- ══════════════════════════════════════════════════════════════════════════════

-- ── onto_classes 扩展 ────────────────────────────────────────────────────────
ALTER TABLE knowledge.onto_classes
  ADD COLUMN abbr TEXT DEFAULT NULL;

ALTER TABLE knowledge.onto_classes
  ADD COLUMN ai00_level INTEGER DEFAULT NULL;

-- 布局画布层次分组：'inner' | 'middle' | 'outer' | 'station' | 'hidden' | NULL
ALTER TABLE knowledge.onto_classes
  ADD COLUMN display_layer TEXT DEFAULT NULL;

ALTER TABLE knowledge.onto_classes
  ADD COLUMN stats_priority INTEGER DEFAULT 99;

ALTER TABLE knowledge.onto_classes
  ADD COLUMN is_hidden_in_layout BOOLEAN NOT NULL DEFAULT FALSE;

-- 创建子节点时的默认推荐子类型（UI 提示，不约束实际父子关系）
ALTER TABLE knowledge.onto_classes
  ADD COLUMN suggested_child_type TEXT DEFAULT NULL;

-- ── onto_properties 扩展 ─────────────────────────────────────────────────────
-- 'text' | 'number' | 'select' | 'pics' | 'checkbox' | 'textarea'
ALTER TABLE knowledge.onto_properties
  ADD COLUMN field_widget TEXT NOT NULL DEFAULT 'text';

ALTER TABLE knowledge.onto_properties
  ADD COLUMN field_config JSONB NOT NULL DEFAULT '{}';

ALTER TABLE knowledge.onto_properties
  ADD COLUMN show_in_create_dialog BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE knowledge.onto_properties
  ADD COLUMN dialog_order INTEGER NOT NULL DEFAULT 99;

-- ── onto_relations 扩展 ──────────────────────────────────────────────────────
ALTER TABLE knowledge.onto_relations
  ADD COLUMN deep_copy_on_fork BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE knowledge.onto_relations
  ADD COLUMN shared_on_fork BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE knowledge.onto_relations
  ADD COLUMN skip_on_fork BOOLEAN NOT NULL DEFAULT FALSE;

-- snapshot 目标表从 range_class_gid → onto_classes.entity_table 推导，不单独存
ALTER TABLE knowledge.onto_relations
  ADD COLUMN snapshot_on_freeze BOOLEAN NOT NULL DEFAULT FALSE;

-- ── onto_axioms 扩展 ─────────────────────────────────────────────────────────
ALTER TABLE knowledge.onto_axioms
  ADD COLUMN property_gid TEXT DEFAULT NULL;

-- ── 知识/规则 语义索引 ───────────────────────────────────────────────────────
ALTER TABLE knowledge.knowledge_entries
  ADD COLUMN onto_class_gid    TEXT DEFAULT NULL,
  ADD COLUMN onto_property_gid TEXT DEFAULT NULL;

-- ── 索引 ─────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_know_onto_class ON knowledge.knowledge_entries(onto_class_gid)
  WHERE onto_class_gid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_craft_rules_class ON knowledge.craft_rules(context_class_gid)
  WHERE context_class_gid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_onto_classes_node_type ON knowledge.onto_classes(node_type_binding)
  WHERE node_type_binding IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_onto_classes_entity_table ON knowledge.onto_classes(entity_table)
  WHERE entity_table IS NOT NULL;

-- ── knowledge_entries 本体绑定列补 FK（ON DELETE SET NULL，删类时自动解绑）───
ALTER TABLE knowledge.knowledge_entries
  DROP CONSTRAINT IF EXISTS fk_know_onto_class,
  ADD CONSTRAINT fk_know_onto_class
    FOREIGN KEY (onto_class_gid) REFERENCES knowledge.onto_classes(gid) ON DELETE SET NULL;

ALTER TABLE knowledge.knowledge_entries
  DROP CONSTRAINT IF EXISTS fk_know_onto_prop,
  ADD CONSTRAINT fk_know_onto_prop
    FOREIGN KEY (onto_property_gid) REFERENCES knowledge.onto_properties(gid) ON DELETE SET NULL;

-- onto_relations 补 sort_order（关系排序，对应属性已有 sort_order）
ALTER TABLE knowledge.onto_relations
  ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;

-- onto_properties 补 show_in_detail / detail_order
-- show_in_detail: 是否在工艺流程图详情面板中显示
-- detail_order:   详情面板中的显示顺序
ALTER TABLE knowledge.onto_properties
  ADD COLUMN show_in_detail BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE knowledge.onto_properties
  ADD COLUMN detail_order   INTEGER NOT NULL DEFAULT 99;
