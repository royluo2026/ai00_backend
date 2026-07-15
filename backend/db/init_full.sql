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
    project_gid  TEXT NOT NULL,  -- FK 补在 proj.projects 建表后（见下方 ALTER TABLE）
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

-- 补上 auth.section_owners.project_gid 的 FK（此时 proj.projects 已建）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_section_owners_project'
          AND conrelid = 'auth.section_owners'::regclass
    ) THEN
        ALTER TABLE auth.section_owners ADD CONSTRAINT fk_section_owners_project
            FOREIGN KEY (project_gid) REFERENCES proj.projects(gid) ON DELETE CASCADE
            NOT VALID;
    END IF;
END $$;

-- Migration: vehicle_models 新增 vehicle_type 字段
ALTER TABLE proj.vehicle_models ADD COLUMN vehicle_type TEXT DEFAULT '';
-- 可选值：纯电MPV / 纯电SUV / 增程SUV / 纯电轿车 / 增程轿车 / 增程MPV

-- Migration: projects 新增目标工厂 FK（factory.factories 在本文件后段建表，此处先加列，FK 约束见后方）
ALTER TABLE proj.projects ADD COLUMN factory_gid TEXT;

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

-- 补上 proj.projects.factory_gid 的 FK（此时 factory.factories 已建）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_projects_factory'
          AND conrelid = 'proj.projects'::regclass
    ) THEN
        ALTER TABLE proj.projects ADD CONSTRAINT fk_projects_factory
            FOREIGN KEY (factory_gid) REFERENCES factory.factories(gid) ON DELETE SET NULL
            NOT VALID;
    END IF;
END $$;

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
    entries     JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE work.task_templates ADD COLUMN entries JSONB NOT NULL DEFAULT '[]';

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
-- template.gbop 表不存在，此行已移除

-- BOP entries 字段由 bop_schema_v2.sql 段统一处理，此处移除重复语句

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
ALTER TABLE knowledge.knowledge_entries ADD COLUMN scheduled_date DATE DEFAULT NULL;

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
ALTER TABLE knowledge.craft_rules ADD COLUMN scheduled_date   DATE DEFAULT NULL;
ALTER TABLE knowledge.craft_rules ADD COLUMN owner_user_gid   TEXT DEFAULT NULL;

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

-- bop.bop_entries 相关字段由 bop_schema_v2.sql 段统一处理，此处移除（前向引用）

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

CREATE TABLE IF NOT EXISTS proj.issues (
    gid                      TEXT PRIMARY KEY,
    display_id               TEXT NOT NULL DEFAULT '',
    title                    TEXT NOT NULL DEFAULT '',
    description              TEXT DEFAULT NULL,
    severity                 TEXT NOT NULL DEFAULT 'normal',    -- low|normal|high|critical
    status                   TEXT NOT NULL DEFAULT 'open',      -- open|in_progress|resolved|closed
    owner_gid                TEXT NOT NULL DEFAULT '',
    owner_user_gid           TEXT REFERENCES auth.users(gid) ON DELETE SET NULL,
    assignee_team_gid        TEXT DEFAULT NULL,
    project_gid              TEXT REFERENCES proj.projects(gid) ON DELETE SET NULL,
    tracking_refs            JSONB NOT NULL DEFAULT '[]',
    occurrence_root_cause    TEXT DEFAULT NULL,
    escape_root_cause        TEXT DEFAULT NULL,
    interim_action           TEXT DEFAULT NULL,
    permanent_action         TEXT DEFAULT NULL,
    source_ref               JSONB NOT NULL DEFAULT '{}',
    related_task_gid         TEXT DEFAULT NULL,
    related_knowledge_gid    TEXT DEFAULT NULL,
    approval_order_gid       TEXT DEFAULT NULL,
    bop_entry_gid            TEXT DEFAULT NULL,
    share_scope              TEXT NOT NULL DEFAULT 'project',
    list_gid                 TEXT DEFAULT NULL,
    attachments              JSONB NOT NULL DEFAULT '[]',
    -- 软删除
    is_deleted               BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at               TIMESTAMPTZ DEFAULT NULL,
    -- 计划日
    scheduled_date           DATE DEFAULT NULL,
    -- 飞书字段
    feishu_assignee_open_id  TEXT DEFAULT NULL,
    feishu_assignee_name     TEXT DEFAULT NULL,
    feishu_group_chat_id     TEXT DEFAULT NULL,
    feishu_group_name        TEXT DEFAULT NULL,
    feishu_groups            JSONB NOT NULL DEFAULT '[]',
    feishu_docs              JSONB NOT NULL DEFAULT '[]',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proj_issues_owner   ON proj.issues (owner_user_gid);
CREATE INDEX IF NOT EXISTS idx_proj_issues_project ON proj.issues (project_gid);
CREATE INDEX IF NOT EXISTS idx_proj_issues_list    ON proj.issues (list_gid);
CREATE INDEX IF NOT EXISTS idx_proj_issues_status  ON proj.issues (status);
CREATE INDEX IF NOT EXISTS idx_proj_issues_deleted ON proj.issues (deleted_at) WHERE deleted_at IS NOT NULL;

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
    -- 飞书字段
    feishu_assignee_open_id  TEXT DEFAULT NULL,
    feishu_assignee_name     TEXT DEFAULT NULL,
    feishu_group_chat_id     TEXT DEFAULT NULL,
    feishu_group_name        TEXT DEFAULT NULL,
    feishu_groups            JSONB NOT NULL DEFAULT '[]',
    feishu_docs              JSONB NOT NULL DEFAULT '[]',
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

-- ── 飞书字段（tasks + issues）────────────────────────────────────────────────
ALTER TABLE proj.tasks  ADD COLUMN feishu_assignee_open_id TEXT DEFAULT NULL;
ALTER TABLE proj.tasks  ADD COLUMN feishu_assignee_name     TEXT DEFAULT NULL;
ALTER TABLE proj.tasks  ADD COLUMN feishu_group_chat_id     TEXT DEFAULT NULL;
ALTER TABLE proj.tasks  ADD COLUMN feishu_group_name        TEXT DEFAULT NULL;
ALTER TABLE proj.tasks  ADD COLUMN feishu_groups JSONB NOT NULL DEFAULT '[]';
ALTER TABLE proj.tasks  ADD COLUMN feishu_docs   JSONB NOT NULL DEFAULT '[]';
ALTER TABLE proj.issues ADD COLUMN feishu_assignee_open_id TEXT DEFAULT NULL;
ALTER TABLE proj.issues ADD COLUMN feishu_assignee_name     TEXT DEFAULT NULL;
ALTER TABLE proj.issues ADD COLUMN feishu_group_chat_id     TEXT DEFAULT NULL;
ALTER TABLE proj.issues ADD COLUMN feishu_group_name        TEXT DEFAULT NULL;
ALTER TABLE proj.issues ADD COLUMN feishu_groups JSONB NOT NULL DEFAULT '[]';
ALTER TABLE proj.issues ADD COLUMN feishu_docs   JSONB NOT NULL DEFAULT '[]';
ALTER TABLE proj.issues ADD COLUMN scheduled_date DATE DEFAULT NULL;

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
ALTER TABLE bop.bop_versions ADD COLUMN version_no       TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN base_version_gid TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN description      TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN created_by       TEXT;
UPDATE bop.bop_versions SET version_no = version_tag WHERE version_no IS NULL;

-- proj.projects：追加项目类型（取值: 'active'|'gbop'|'history'）
ALTER TABLE proj.projects
  ADD COLUMN project_type TEXT NOT NULL DEFAULT 'active';

-- work.tasks/work.issues：附件字段（幂等）
ALTER TABLE work.tasks  ADD COLUMN attachments JSONB DEFAULT '[]';
ALTER TABLE work.issues ADD COLUMN attachments JSONB DEFAULT '[]';


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
ALTER TABLE bop.bop_entries ADD COLUMN title              TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN bom_row_owner      TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN parent_bop_label   TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN ai00_level         SMALLINT;
-- bom_row_id 语义变更：旧值存的是 meta.code（零件号），新语义同；保留数据，无需迁移
-- 删除字段（已有库需手动执行，新库 CREATE TABLE 不含这些列）
-- ALTER TABLE bop.bop_entries DROP COLUMN IF EXISTS bom_row_ver;
-- ALTER TABLE bop.bop_entries DROP COLUMN IF EXISTS meta;
-- （meta 建议在数据确认迁移完成后再删，暂时保留）
ALTER TABLE bop.bop_entries ADD COLUMN meta JSONB NOT NULL DEFAULT '{}';
ALTER TABLE bop.bop_entries ADD COLUMN scheduled_date      DATE DEFAULT NULL;
ALTER TABLE bop.bop_entries ADD COLUMN assignee_user_gid   TEXT DEFAULT NULL;

-- 版本入口索引（bop_version_gid 未重命名时才建；V3-4 patch 会 DROP 并用 version_gid 重建）
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='bop_version_gid') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_ent_version ON bop.bop_entries(bop_version_gid) WHERE deleted_at IS NULL';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_ent_version_level ON bop.bop_entries(bop_version_gid, level) WHERE deleted_at IS NULL';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_ent_version_type ON bop.bop_entries(bop_version_gid, node_type) WHERE deleted_at IS NULL';
    END IF;
END $$;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='parent_bop_gid') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_ent_parent ON bop.bop_entries(parent_bop_gid) WHERE deleted_at IS NULL';
    END IF;
END $$;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='gbop_source_gid') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_ent_gbop_source ON bop.bop_entries(gbop_source_gid) WHERE gbop_source_gid IS NOT NULL';
    END IF;
END $$;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='bom_row_id') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_ent_bom_row_id ON bop.bop_entries(bom_row_id) WHERE bom_row_id IS NOT NULL';
    END IF;
END $$;


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
-- bop_entry_gid / ref_gid 已被 V3-4 patch 重命名，用 DO 块保护
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='bop_entry_gid') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_links_entry ON bop.bop_entry_links(bop_entry_gid)';
    END IF;
END $$;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='ref_gid') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_links_ref ON bop.bop_entry_links(ref_gid, link_type)';
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_bop_links_type    ON bop.bop_entry_links(link_type);

-- 现有表幂等追加（已有 bop_entry_links 的库）——必须在 WHERE is_primary 索引之前执行
ALTER TABLE bop.bop_entry_links ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT FALSE;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='bop_entry_gid') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_links_primary ON bop.bop_entry_links(bop_entry_gid) WHERE is_primary = TRUE';
    END IF;
END $$;
-- idx_bop_links_version 在 bop_schema_v3v4_patch 中追加 version_gid 列后统一建立，此处跳过

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
ALTER TABLE knowledge.knowledge_entries ADD COLUMN display_id TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge.craft_rules        ADD COLUMN display_id TEXT NOT NULL DEFAULT '';


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
ALTER TABLE bop.bop_steps ADD COLUMN vd_time             REAL;
ALTER TABLE bop.bop_steps ADD COLUMN total_time          REAL;
ALTER TABLE bop.bop_steps ADD COLUMN floor_height_need   INTEGER;
ALTER TABLE bop.bop_steps ADD COLUMN process_flow_pic    JSONB;
ALTER TABLE bop.bop_steps ADD COLUMN process_chart_pic   JSONB;

-- process_flow_pic 同时存在 bop_entries 上（直接写入，无需走 bop_steps 中间表）
ALTER TABLE bop.bop_entries ADD COLUMN process_flow_pic  JSONB;


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
ALTER TABLE bop.bop_entries  ADD COLUMN vpps_part TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_entries  ADD COLUMN part_feed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bop.bop_steps    ADD COLUMN vpps_part TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_steps    ADD COLUMN part_feed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bop.bop_process  ADD COLUMN vpps_part TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_process  ADD COLUMN part_feed BOOLEAN NOT NULL DEFAULT FALSE;

-- ── catia_occurrence_name + parent_vpps_name（TC CSV 扩展列，从 schema.sql 移至此处）
ALTER TABLE bop.bop_entries ADD COLUMN catia_occurrence_name TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_entries ADD COLUMN parent_vpps_name      TEXT NOT NULL DEFAULT '';


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
ALTER TABLE bop.bop_entries ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_entries ADD COLUMN vpps_desc TEXT;
CREATE INDEX IF NOT EXISTS idx_bop_ent_vpps ON bop.bop_entries(vpps) WHERE vpps IS NOT NULL;
-- 版本条目主查询过滤索引（WHERE version_gid = %s AND is_deleted = FALSE）
-- 列名此时为 bop_version_gid（bop_schema_v3v4_patch 会 RENAME 为 version_gid 并重建此索引）
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='bop_version_gid') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_bop_ent_version ON bop.bop_entries(bop_version_gid) WHERE deleted_at IS NULL';
    END IF;
END $$;

-- ── 工艺过程实体 ─────────────────────────────────────────────────────
-- bop.bop_steps 已有 vpps TEXT + vpps_desc TEXT ✓
ALTER TABLE bop.bop_line     ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_station  ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_operator ADD COLUMN vpps TEXT;
ALTER TABLE bop.asm_steps    ADD COLUMN vpps TEXT;

-- ── 项目资源实体 ─────────────────────────────────────────────────────
ALTER TABLE bop.bop_equipments    ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_fixtures      ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_tools         ADD COLUMN vpps TEXT;
ALTER TABLE bop.project_roles     ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_control_plan  ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_process_charts ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_floor_height  ADD COLUMN vpps TEXT;
ALTER TABLE bop.bop_jack_pos      ADD COLUMN vpps TEXT;

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

ALTER TABLE bop.bop_versions ADD COLUMN version_family_gid TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN bop_name           TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_versions ADD COLUMN frozen_at          TIMESTAMPTZ;
ALTER TABLE bop.bop_versions ADD COLUMN archived_at        TIMESTAMPTZ;

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
ALTER TABLE factory.factory_stations ADD COLUMN factory_line_gid TEXT;
CREATE INDEX IF NOT EXISTS idx_factory_sta_line ON factory.factory_stations(factory_line_gid)
  WHERE factory_line_gid IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
-- G-2. BOP 版本血缘（Git-lite：parent_version_gid + change_note）
-- ───────────────────────────────────────────────────────────────────
--
-- parent_version_gid: fork/branch 的直接来源版本 gid（自引用，无 FK）
-- change_note:        本次版本变更说明（类比 git commit message）

ALTER TABLE bop.bop_versions ADD COLUMN parent_version_gid TEXT;
ALTER TABLE bop.bop_versions ADD COLUMN change_note        TEXT;

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
ALTER TABLE bop.bop_versions ADD COLUMN published_at TIMESTAMPTZ;

-- I-1b. 修改 status 默认值（旧库可能还是 'draft'）
ALTER TABLE bop.bop_versions ALTER COLUMN status SET DEFAULT 'active';

-- I-2. status 值迁移：draft→active, frozen→baseline, released→M
UPDATE bop.bop_versions SET status='active'   WHERE status='draft';
UPDATE bop.bop_versions SET status='baseline' WHERE status='frozen';
UPDATE bop.bop_versions SET status='M'        WHERE status='released';

-- I-3. bop_entry_links 追加快照字段（冻结时写入关联实体的关键字段快照）
ALTER TABLE bop.bop_entry_links ADD COLUMN snapshot_data JSONB;
-- ═══════════════════════════════════════════════════════════════════
-- BOP V3+V4 补丁脚本（针对当前数据库实际状态）
-- 文件：backend/db/bop_schema_v3v4_patch.sql
--
-- 与 bop_schema_v3v4.sql 的区别：
--   1. asm_steps / project_roles 已不存在，跳过数据迁移部分
--   2. pbom / pbom_versions 在 bop schema 下（非独立 pbom schema）
--   3. 所有 RENAME COLUMN 用 DO 块保护，幂等安全
-- ═══════════════════════════════════════════════════════════════════

-- BEGIN; （已移除显式事务，每条 DDL 自动提交，避免单条失败连累整块）

-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-1 实体表 name → title
-- ═══════════════════════════════════════════════════════════════════

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_line' AND column_name='name') THEN
    ALTER TABLE bop.bop_line RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_station' AND column_name='name') THEN
    ALTER TABLE bop.bop_station RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_process' AND column_name='name') THEN
    ALTER TABLE bop.bop_process RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_steps' AND column_name='name') THEN
    ALTER TABLE bop.bop_steps RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_operator' AND column_name='name') THEN
    ALTER TABLE bop.bop_operator RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_equipments' AND column_name='name') THEN
    ALTER TABLE bop.bop_equipments RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_fixtures' AND column_name='name') THEN
    ALTER TABLE bop.bop_fixtures RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_tools' AND column_name='name') THEN
    ALTER TABLE bop.bop_tools RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_control_plan' AND column_name='name') THEN
    ALTER TABLE bop.bop_control_plan RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_process_charts' AND column_name='name') THEN
    ALTER TABLE bop.bop_process_charts RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_floor_height' AND column_name='name') THEN
    ALTER TABLE bop.bop_floor_height RENAME COLUMN name TO title;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_jack_pos' AND column_name='name') THEN
    ALTER TABLE bop.bop_jack_pos RENAME COLUMN name TO title;
  END IF;
END $$;

-- pbom 表也有 name 列
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='pbom' AND column_name='name') THEN
    ALTER TABLE bop.pbom RENAME COLUMN name TO title;
  END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-2 bop_entries 列重命名
-- ═══════════════════════════════════════════════════════════════════

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='bop_version_gid')
 AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='version_gid') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN bop_version_gid TO version_gid;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='parent_bop_gid')
 AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='parent_gid') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN parent_bop_gid TO parent_gid;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='seq_no')
 AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='sort_order') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN seq_no TO sort_order;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='parent_bop_label')
 AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='parent_bop_title') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN parent_bop_label TO parent_bop_title;
  END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-3 bop_entry_links 列重命名 + 新增 version_gid
-- ═══════════════════════════════════════════════════════════════════

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='bop_entry_gid')
 AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='entry_gid') THEN
    ALTER TABLE bop.bop_entry_links RENAME COLUMN bop_entry_gid TO entry_gid;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='ref_gid')
 AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='entity_gid') THEN
    ALTER TABLE bop.bop_entry_links RENAME COLUMN ref_gid TO entity_gid;
  END IF;
END $$;

ALTER TABLE bop.bop_entry_links ADD COLUMN version_gid TEXT;

-- 回填 version_gid
UPDATE bop.bop_entry_links l
   SET version_gid = e.version_gid
  FROM bop.bop_entries e
 WHERE l.entry_gid = e.gid
   AND l.version_gid IS NULL;


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-4 bop_entries 删除冗余字段 + 新增 child_vpps
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE bop.bop_entries
    DROP COLUMN IF EXISTS bom_row_id,
    DROP COLUMN IF EXISTS bom_row_label,
    DROP COLUMN IF EXISTS bom_row_owner,
    DROP COLUMN IF EXISTS vpps_part,
    DROP COLUMN IF EXISTS part_feed,
    DROP COLUMN IF EXISTS process_flow_pic,
    DROP COLUMN IF EXISTS process_chart_pic,
    DROP COLUMN IF EXISTS gbop_source_gid,
    DROP COLUMN IF EXISTS history_source_gid;

ALTER TABLE bop.bop_entries
    ADD COLUMN child_vpps JSONB NOT NULL DEFAULT '[]';


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-5 bop_process 删除 vpps_part / part_feed
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE bop.bop_process
    DROP COLUMN IF EXISTS vpps_part,
    DROP COLUMN IF EXISTS part_feed;


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-6 全表新增软删除 / 归档字段
-- ═══════════════════════════════════════════════════════════════════

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'bop.bop_versions', 'bop.bop_entries', 'bop.bop_entry_links',
        'bop.bop_line', 'bop.bop_station', 'bop.bop_process',
        'bop.bop_steps', 'bop.bop_operator', 'bop.bop_equipments',
        'bop.bop_fixtures', 'bop.bop_tools', 'bop.bop_control_plan',
        'bop.bop_process_charts', 'bop.bop_floor_height', 'bop.bop_jack_pos',
        'bop.bop_staging'
    ]
    LOOP
        EXECUTE format(
            'ALTER TABLE %s
                ADD COLUMN is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN deleted_at  TIMESTAMPTZ,
                ADD COLUMN archived_at TIMESTAMPTZ',
            t
        );
    END LOOP;
END$$;

UPDATE bop.bop_entries SET is_deleted  = TRUE WHERE deleted_at  IS NOT NULL AND is_deleted  = FALSE;
UPDATE bop.bop_entries SET is_archived = TRUE WHERE archived_at IS NOT NULL AND is_archived = FALSE;


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-7 索引重建
-- ═══════════════════════════════════════════════════════════════════

DROP INDEX IF EXISTS bop.idx_bop_ent_version;
DROP INDEX IF EXISTS bop.idx_bop_ent_parent;
DROP INDEX IF EXISTS bop.idx_bop_ent_version_level;
DROP INDEX IF EXISTS bop.idx_bop_ent_version_type;
DROP INDEX IF EXISTS bop.idx_bop_ent_gbop_source;
DROP INDEX IF EXISTS bop.idx_bop_ent_bom_row_id;
DROP INDEX IF EXISTS bop.idx_bop_ent_vpps;

CREATE INDEX IF NOT EXISTS idx_bop_ent_version
    ON bop.bop_entries(version_gid) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_bop_ent_parent
    ON bop.bop_entries(parent_gid) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_bop_ent_version_level
    ON bop.bop_entries(version_gid, level) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_bop_ent_version_type
    ON bop.bop_entries(version_gid, node_type) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_bop_ent_vpps
    ON bop.bop_entries(vpps) WHERE vpps IS NOT NULL;

DROP INDEX IF EXISTS bop.idx_bop_links_entry;
DROP INDEX IF EXISTS bop.idx_bop_links_ref;
DROP INDEX IF EXISTS bop.idx_bop_links_type;
DROP INDEX IF EXISTS bop.idx_bop_links_primary;

CREATE INDEX IF NOT EXISTS idx_bop_links_entry
    ON bop.bop_entry_links(entry_gid);
CREATE INDEX IF NOT EXISTS idx_bop_links_entity
    ON bop.bop_entry_links(entity_gid, link_type);
CREATE INDEX IF NOT EXISTS idx_bop_links_version
    ON bop.bop_entry_links(version_gid);
CREATE INDEX IF NOT EXISTS idx_bop_links_type
    ON bop.bop_entry_links(link_type);
CREATE INDEX IF NOT EXISTS idx_bop_links_primary
    ON bop.bop_entry_links(entry_gid) WHERE is_primary = TRUE;

DROP INDEX IF EXISTS bop.idx_asm_step_vpps;
DROP INDEX IF EXISTS bop.idx_bop_steps_step_code;
DROP INDEX IF EXISTS bop.idx_proj_roles_proj;
DROP INDEX IF EXISTS bop.idx_proj_roles_vpps;


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-8 存量 link_type 迁移
-- ═══════════════════════════════════════════════════════════════════

UPDATE bop.bop_entry_links SET link_type = 'bop_line'     WHERE link_type = 'asm_line_process';
UPDATE bop.bop_entry_links SET link_type = 'bop_station'  WHERE link_type = 'asm_station_process';
UPDATE bop.bop_entry_links SET link_type = 'bop_steps'    WHERE link_type = 'asm_operation';
UPDATE bop.bop_entry_links SET link_type = 'bop_operator' WHERE link_type IN ('asm_operator_process', 'project_roles');


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4-1 bop_versions 新增字段
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE bop.bop_versions
    ADD COLUMN version_type     TEXT NOT NULL DEFAULT 'working',
    ADD COLUMN pbom_version_gid TEXT,
    ADD COLUMN owner_gid        TEXT;

COMMENT ON COLUMN bop.bop_versions.version_type IS
    'working = 工作版本；template = 工厂模板版本';
COMMENT ON COLUMN bop.bop_versions.pbom_version_gid IS
    'working 版本必填，关联 bop.pbom_versions.gid；template 为 NULL';
COMMENT ON COLUMN bop.bop_versions.owner_gid IS
    'template 版本的 owner 控制 update-from 权限';


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4-2 pbom_versions.status 值迁移（bop schema 下）
-- ═══════════════════════════════════════════════════════════════════

UPDATE bop.pbom_versions SET status = 'raw'   WHERE status = 'draft';
UPDATE bop.pbom_versions SET status = 'ready' WHERE status = 'released';

COMMENT ON COLUMN bop.pbom_versions.status IS
    'raw = 刚导入；ready = 预处理完成，可被 BOP 版本绑定';


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4-3 bop.pbom 新增 vpps_source / vpps_reported_at
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE bop.pbom
    ADD COLUMN vpps_source      TEXT NOT NULL DEFAULT 'auto',
    ADD COLUMN vpps_reported_at TIMESTAMPTZ;

COMMENT ON COLUMN bop.pbom.vpps_source IS
    'auto = 正常；manual = 人工临时值';
COMMENT ON COLUMN bop.pbom.vpps_reported_at IS
    '提报修改的时间，vpps_source=manual 时填写';


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4-4 bop_steps / bop_operator（已有字段，防御性确认）
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE bop.bop_steps    DROP COLUMN IF EXISTS step_code;
ALTER TABLE bop.bop_steps    ADD COLUMN operation_code TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_operator ADD COLUMN operator_code  TEXT NOT NULL DEFAULT '';


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4-5 新建 gbop_match_staging 中间表
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS bop.gbop_match_staging (
    gid               TEXT PRIMARY KEY,
    pbom_version_gid  TEXT NOT NULL,
    bop_version_gid   TEXT,
    gbop_entry_gid    TEXT NOT NULL,
    pbom_entry_gid    TEXT NOT NULL,
    match_status      TEXT NOT NULL DEFAULT 'pending',
    created_entry_gid TEXT,
    confirmed_by      TEXT,
    confirmed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by        TEXT,
    UNIQUE (pbom_version_gid, pbom_entry_gid)
);

CREATE INDEX IF NOT EXISTS idx_gbop_staging_pbom
    ON bop.gbop_match_staging(pbom_version_gid);
CREATE INDEX IF NOT EXISTS idx_gbop_staging_bop
    ON bop.gbop_match_staging(bop_version_gid) WHERE bop_version_gid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_gbop_staging_status
    ON bop.gbop_match_staging(pbom_version_gid, match_status);

COMMENT ON TABLE bop.gbop_match_staging IS
    'GBOP 匹配中间表；只记录过程，不缓存实体数据';


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4-6 bop_versions 新索引
-- ═══════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_bop_ver_type
    ON bop.bop_versions(version_type) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_bop_ver_pbom
    ON bop.bop_versions(pbom_version_gid) WHERE pbom_version_gid IS NOT NULL;


-- COMMIT; （已移除）

-- ═══════════════════════════════════════════════════════════════════
-- 脚本结束
-- ═══════════════════════════════════════════════════════════════════
-- bop_nav_patch.sql
-- 为 gbop_match_staging 添加 extra_entry_gids（多操作匹配支持）
-- 在 DBeaver 手动执行

ALTER TABLE bop.gbop_match_staging
    ADD COLUMN extra_entry_gids JSONB NOT NULL DEFAULT '[]';

COMMENT ON COLUMN bop.gbop_match_staging.extra_entry_gids IS
    '额外关联的 GBOP entry gid 列表；主操作用 gbop_entry_gid，附加操作存此处';
-- entry_cascade_delete_patch.sql
-- 为 bop_entry_links 及各实体表添加 deleted_at，支持软删除级联
-- 在 DBeaver 中手动执行

ALTER TABLE bop.bop_entry_links ADD COLUMN deleted_at TIMESTAMPTZ;

ALTER TABLE bop.bop_line        ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_station     ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_process     ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_steps       ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_operator    ADD COLUMN deleted_at TIMESTAMPTZ;
-- BEGIN; （已移除显式事务）

UPDATE bop.bop_entries SET node_type = 'factory_bop'
  WHERE node_type IN ('总装产品bop','总装产品BOP','总装工厂BOP','总装BOP','工厂BOP','产品BOP','BOP');

UPDATE bop.bop_entries SET node_type = 'line_process'
  WHERE node_type IN ('总装线体工艺','产线工艺');

UPDATE bop.bop_entries SET node_type = 'station_process'
  WHERE node_type IN ('总装工位工艺','工位工艺');

UPDATE bop.bop_entries SET node_type = 'operator_process'
  WHERE node_type IN ('总装岗位工艺');

UPDATE bop.bop_entries SET node_type = 'process'
  WHERE node_type IN ('总装工序','工序');

-- 操作（Product）：兼容大写/小写 P，全角/半角括号
UPDATE bop.bop_entries SET node_type = 'operation'
  WHERE LOWER(node_type) IN (
    '总装操作（product）',   -- 全角括号
    '总装操作(product)',     -- 半角括号
    '总装操作'
  );

UPDATE bop.bop_entries SET node_type = 'part'
  WHERE node_type = '零部件';

UPDATE bop.bop_entries SET node_type = 'non_standard_part'
  WHERE node_type = '非标件';

UPDATE bop.bop_entries SET node_type = 'standard_part'
  WHERE node_type = '标准件';

UPDATE bop.bop_entries SET node_type = 'tool_need'
  WHERE node_type IN ('工具','工具（需求）');

UPDATE bop.bop_entries SET node_type = 'tool_factory'
  WHERE node_type IN ('工具（现有）');

UPDATE bop.bop_entries SET node_type = 'fixture_need'
  WHERE node_type IN ('工装','工装（需求）');

UPDATE bop.bop_entries SET node_type = 'fixture_factory'
  WHERE node_type IN ('工装（现有）');

UPDATE bop.bop_entries SET node_type = 'equipment_need'
  WHERE node_type IN ('设备（需求）','设备需求');

UPDATE bop.bop_entries SET node_type = 'equipment_factory'
  WHERE node_type = '设备';

UPDATE bop.bop_entries SET node_type = 'support_material'
  WHERE node_type = '辅料';

-- ── 同步修复 bop_entry_links.link_type ──────────────────────────────────────
-- 将 operation 条目对应的 link 更新到 bop_steps
UPDATE bop.bop_entry_links el
SET link_type = 'bop_steps'
FROM bop.bop_entries e
WHERE el.entry_gid = e.gid
  AND e.node_type = 'operation'
  AND el.link_type IN ('asm_operation','bop_operation','operation');

-- 已有 asm_operation 兜底（不依赖 bop_entries node_type）
UPDATE bop.bop_entry_links SET link_type = 'bop_steps'
  WHERE link_type = 'asm_operation';

-- COMMIT; （已移除）
