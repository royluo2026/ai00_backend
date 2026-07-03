-- ============================================================
-- AI00 本地开发数据库初始化脚本
-- 数据库：ai00_dev（合并 users + collab，本地开发用）
--
-- 使用方法：
--   psql -U postgres -c "CREATE DATABASE ai00_dev;"
--   psql -U postgres -d ai00_dev -f backend/db/init_dev_db.sql
-- ============================================================


-- ── 团队表 ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS teams (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 全局系统配置 ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS system_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 用户与权限表 ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
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
    team_id          TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_feishu_id ON users (feishu_open_id);
CREATE INDEX IF NOT EXISTS idx_users_email     ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_role      ON users (system_role);
CREATE INDEX IF NOT EXISTS idx_users_team      ON users (team_id);

CREATE TABLE IF NOT EXISTS project_members (
    gid          TEXT PRIMARY KEY,
    project_gid  TEXT NOT NULL,
    user_gid     TEXT NOT NULL REFERENCES users(gid) ON DELETE CASCADE,
    project_role TEXT NOT NULL DEFAULT 'member',  -- project_owner / section_lead / member
    section_gid  TEXT DEFAULT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_gid, user_gid)
);

CREATE INDEX IF NOT EXISTS idx_pm_project ON project_members (project_gid);
CREATE INDEX IF NOT EXISTS idx_pm_user    ON project_members (user_gid);


-- ── OAuth 登录轮询表 ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS auth_pending (
    state       TEXT PRIMARY KEY,
    jwt         TEXT DEFAULT NULL,
    error       TEXT DEFAULT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '10 minutes'
);

-- 自动清理过期 pending 记录（可选，生产环境建议用 pg_cron）
-- DELETE FROM auth_pending WHERE expires_at < NOW();


-- ── 自动更新 updated_at 触发器 ────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── 存量数据迁移（已存在旧库时执行）─────────────────────────────

-- 若旧库缺少 team_id 列，补加
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='users' AND column_name='team_id'
    ) THEN
        ALTER TABLE users ADD COLUMN team_id TEXT REFERENCES teams(gid) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS idx_users_team ON users (team_id);
    END IF;
END $$;

-- 旧用户默认角色 member → 保持不动（不强制降为 external）
-- 只把仍是旧值 'template_admin' 的角色合并为 'knowledge_admin'
UPDATE users SET system_role = 'knowledge_admin'
WHERE system_role = 'template_admin';


-- ══════════════════════════════════════════════════════════════
-- 云端业务数据表
-- ══════════════════════════════════════════════════════════════

-- ── 项目 BC ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vehicle_models (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    brand       TEXT NOT NULL DEFAULT '',
    platform    TEXT NOT NULL DEFAULT '',
    team_id     TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    meta        JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    gid          TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'preparing',
    vehicle_model_gid TEXT REFERENCES vehicle_models(gid) ON DELETE SET NULL,
    team_id      TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    owner_gid    TEXT REFERENCES users(gid) ON DELETE SET NULL,
    share_scope  TEXT NOT NULL DEFAULT 'team',
    meta         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_team   ON projects (team_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects (status);

-- ── 工艺 BOP BC ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS work_plans (
    gid          TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    project_gid  TEXT REFERENCES projects(gid) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'draft',
    version      TEXT NOT NULL DEFAULT '1.0',
    share_scope  TEXT NOT NULL DEFAULT 'team',
    meta         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_work_plans_project ON work_plans (project_gid);

CREATE TABLE IF NOT EXISTS sections (
    gid           TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    work_plan_gid TEXT NOT NULL REFERENCES work_plans(gid) ON DELETE CASCADE,
    sort_order    INT NOT NULL DEFAULT 0,
    is_locked     BOOLEAN NOT NULL DEFAULT FALSE,
    locked_by     TEXT REFERENCES users(gid) ON DELETE SET NULL,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sections_work_plan ON sections (work_plan_gid);

CREATE TABLE IF NOT EXISTS operation_flat (
    gid             TEXT PRIMARY KEY,
    section_gid     TEXT NOT NULL REFERENCES sections(gid) ON DELETE CASCADE,
    work_plan_gid   TEXT NOT NULL REFERENCES work_plans(gid) ON DELETE CASCADE,
    workstation_gid TEXT DEFAULT NULL,
    post_gid        TEXT DEFAULT NULL,
    seq_no          INT NOT NULL DEFAULT 0,
    op_code         TEXT NOT NULL DEFAULT '',
    op_name         TEXT NOT NULL DEFAULT '',
    std_op_gid      TEXT DEFAULT NULL,
    standard_time   REAL NOT NULL DEFAULT 0,
    importance      TEXT DEFAULT NULL,
    parts           JSONB NOT NULL DEFAULT '[]',
    tools           JSONB NOT NULL DEFAULT '[]',
    parameters      JSONB NOT NULL DEFAULT '{}',
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opflat_section   ON operation_flat (section_gid);
CREATE INDEX IF NOT EXISTS idx_opflat_work_plan ON operation_flat (work_plan_gid);

-- ── eBOM BC ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bom_snapshots (
    gid          TEXT PRIMARY KEY,
    project_gid  TEXT NOT NULL REFERENCES projects(gid) ON DELETE CASCADE,
    version_tag  TEXT NOT NULL DEFAULT '',
    source_type  TEXT NOT NULL DEFAULT 'manual',
    status       TEXT NOT NULL DEFAULT 'draft',
    meta         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bom_snapshots_project ON bom_snapshots (project_gid);

CREATE TABLE IF NOT EXISTS part_entries (
    gid             TEXT PRIMARY KEY,
    snapshot_gid    TEXT NOT NULL REFERENCES bom_snapshots(gid) ON DELETE CASCADE,
    part_no         TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    quantity        REAL NOT NULL DEFAULT 1,
    unit            TEXT NOT NULL DEFAULT 'pcs',
    material        TEXT DEFAULT NULL,
    parent_gid      TEXT DEFAULT NULL,
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_part_entries_snapshot ON part_entries (snapshot_gid);

CREATE TABLE IF NOT EXISTS part_model_instances (
    gid             TEXT PRIMARY KEY,
    part_entry_gid  TEXT NOT NULL REFERENCES part_entries(gid) ON DELETE CASCADE,
    model_file_path TEXT NOT NULL DEFAULT '',
    transform       JSONB NOT NULL DEFAULT '{}',
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 协同 BC ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS collab_sessions (
    gid          TEXT PRIMARY KEY,
    section_gid  TEXT NOT NULL REFERENCES sections(gid) ON DELETE CASCADE,
    owner_gid    TEXT NOT NULL REFERENCES users(gid) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'active',
    participants JSONB NOT NULL DEFAULT '[]',
    meta         JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at     TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_collab_sessions_section ON collab_sessions (section_gid);

-- ── 审批 BC ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS approval_orders (
    gid            TEXT PRIMARY KEY,
    project_gid    TEXT REFERENCES projects(gid) ON DELETE SET NULL,
    order_type     TEXT NOT NULL DEFAULT 'general',
    title          TEXT NOT NULL DEFAULT '',
    applicant_gid  TEXT NOT NULL REFERENCES users(gid) ON DELETE CASCADE,
    reviewer_gid   TEXT REFERENCES users(gid) ON DELETE SET NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    source_ref     TEXT DEFAULT NULL,
    content        JSONB NOT NULL DEFAULT '{}',
    opinions       JSONB NOT NULL DEFAULT '[]',
    share_scope    TEXT NOT NULL DEFAULT 'project',
    meta           JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approval_orders_project   ON approval_orders (project_gid);
CREATE INDEX IF NOT EXISTS idx_approval_orders_applicant ON approval_orders (applicant_gid);
CREATE INDEX IF NOT EXISTS idx_approval_orders_status    ON approval_orders (status);

-- ── 标准工序库 BC ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS std_operations (
    gid            TEXT PRIMARY KEY,
    code           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'draft',
    standard_time  REAL NOT NULL DEFAULT 0,
    importance     TEXT DEFAULT NULL,
    description    TEXT NOT NULL DEFAULT '',
    steps          JSONB NOT NULL DEFAULT '[]',
    required_tools JSONB NOT NULL DEFAULT '[]',
    parameters     JSONB NOT NULL DEFAULT '{}',
    share_scope    TEXT NOT NULL DEFAULT 'team',
    team_id        TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    created_by     TEXT REFERENCES users(gid) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_std_operations_code   ON std_operations (code);
CREATE INDEX IF NOT EXISTS idx_std_operations_status ON std_operations (status);

-- ── 工艺元素库 BC ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tool_templates (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    spec       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS equipment_templates (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    spec       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fixture_templates (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    spec       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS standard_fasteners (
    gid        TEXT PRIMARY KEY,
    part_no    TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL DEFAULT '',
    spec       TEXT NOT NULL DEFAULT '',
    material   TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    meta       JSONB NOT NULL DEFAULT '{}',
    team_id    TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS standard_part_names (
    gid            TEXT PRIMARY KEY,
    standard_name  TEXT NOT NULL DEFAULT '',
    part_category  TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    team_id        TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 工厂资源 BC ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS physical_tools (
    gid           TEXT PRIMARY KEY,
    asset_no      TEXT NOT NULL UNIQUE,
    template_gid  TEXT REFERENCES tool_templates(gid) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'in_use',
    team_id       TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS physical_equipments (
    gid           TEXT PRIMARY KEY,
    asset_no      TEXT NOT NULL UNIQUE,
    template_gid  TEXT REFERENCES equipment_templates(gid) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'in_use',
    team_id       TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS physical_fixtures (
    gid           TEXT PRIMARY KEY,
    asset_no      TEXT NOT NULL UNIQUE,
    template_gid  TEXT REFERENCES fixture_templates(gid) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'in_use',
    team_id       TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── 关注 BC ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS follows (
    gid        TEXT PRIMARY KEY,
    user_gid   TEXT NOT NULL REFERENCES users(gid) ON DELETE CASCADE,
    item_type  TEXT NOT NULL,   -- task|issue|project|knowledge|rule|std_op|work_plan
    item_gid   TEXT NOT NULL,
    item_title TEXT NOT NULL DEFAULT '',
    notify_on  TEXT NOT NULL DEFAULT 'key_changes',  -- all|key_changes|none
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_gid, item_type, item_gid)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='follows' AND column_name='item_title') THEN
        ALTER TABLE follows ADD COLUMN item_title TEXT NOT NULL DEFAULT '';
    END IF;
END $$;

-- 通知偏好（JSONB，每个用户独立控制接收哪些类型）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='notification_prefs') THEN
        ALTER TABLE users ADD COLUMN notification_prefs JSONB NOT NULL DEFAULT '{}';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_follows_user ON follows (user_gid);
CREATE INDEX IF NOT EXISTS idx_follows_item ON follows (item_type, item_gid);


-- ── 通知 BC ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS notifications (
    gid        TEXT PRIMARY KEY,
    user_gid   TEXT NOT NULL REFERENCES users(gid) ON DELETE CASCADE,
    type       TEXT NOT NULL,   -- scope_approved|scope_rejected|item_status|new_follower
    item_type  TEXT DEFAULT NULL,
    item_gid   TEXT DEFAULT NULL,
    title      TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    is_read    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_user_unread ON notifications (user_gid, is_read);


-- ── 存量数据迁移：share_scope 列 ──────────────────────────────────

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='projects' AND column_name='share_scope') THEN
        ALTER TABLE projects ADD COLUMN share_scope TEXT NOT NULL DEFAULT 'team';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='work_plans' AND column_name='share_scope') THEN
        ALTER TABLE work_plans ADD COLUMN share_scope TEXT NOT NULL DEFAULT 'team';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='std_operations' AND column_name='share_scope') THEN
        ALTER TABLE std_operations ADD COLUMN share_scope TEXT NOT NULL DEFAULT 'team';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='approval_orders' AND column_name='share_scope') THEN
        ALTER TABLE approval_orders ADD COLUMN share_scope TEXT NOT NULL DEFAULT 'project';
    END IF;
END $$;


-- ══════════════════════════════════════════════════════════════
-- BOP 画布新增表（工厂布局 + BOP 五层结构）
-- ══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS factories (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    team_id    TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    meta       JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS factory_sections (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    factory_gid TEXT NOT NULL REFERENCES factories(gid) ON DELETE CASCADE,
    sort_order  INT  NOT NULL DEFAULT 0,
    color       TEXT NOT NULL DEFAULT '#7287fd',
    canvas_x    REAL NOT NULL DEFAULT 0,
    canvas_y    REAL NOT NULL DEFAULT 0,
    canvas_w    REAL NOT NULL DEFAULT 400,
    canvas_h    REAL NOT NULL DEFAULT 300,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS factory_stations (
    gid                 TEXT PRIMARY KEY,
    code                TEXT NOT NULL DEFAULT '',
    name                TEXT NOT NULL DEFAULT '',
    factory_section_gid TEXT NOT NULL REFERENCES factory_sections(gid) ON DELETE CASCADE,
    canvas_x            REAL NOT NULL DEFAULT 0,
    canvas_y            REAL NOT NULL DEFAULT 0,
    takt_time           REAL NOT NULL DEFAULT 60,
    height_mm           INT  NOT NULL DEFAULT 1200,
    meta                JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_factory_stations_section ON factory_stations (factory_section_gid);

CREATE TABLE IF NOT EXISTS bop_versions (
    gid               TEXT PRIMARY KEY,
    project_gid       TEXT REFERENCES projects(gid) ON DELETE CASCADE,
    factory_gid       TEXT REFERENCES factories(gid) ON DELETE SET NULL,
    vehicle_model_gid TEXT REFERENCES vehicle_models(gid) ON DELETE SET NULL,
    version_tag       TEXT NOT NULL DEFAULT '',
    maturity          TEXT NOT NULL DEFAULT 'concept',
    takt_time         REAL NOT NULL DEFAULT 60,
    status            TEXT NOT NULL DEFAULT 'draft',
    meta              JSONB NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bop_versions_project ON bop_versions (project_gid);
CREATE INDEX IF NOT EXISTS idx_bop_versions_factory ON bop_versions (factory_gid);

CREATE TABLE IF NOT EXISTS bop_posts (
    gid             TEXT PRIMARY KEY,
    bop_version_gid TEXT NOT NULL REFERENCES bop_versions(gid) ON DELETE CASCADE,
    station_gid     TEXT NOT NULL REFERENCES factory_stations(gid) ON DELETE CASCADE,
    post_code       TEXT NOT NULL DEFAULT '',
    post_name       TEXT NOT NULL DEFAULT '',
    head_count      INT  NOT NULL DEFAULT 1,
    sort_order      INT  NOT NULL DEFAULT 0,
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bop_posts_bop     ON bop_posts (bop_version_gid);
CREATE INDEX IF NOT EXISTS idx_bop_posts_station ON bop_posts (station_gid);

CREATE TABLE IF NOT EXISTS bop_operations (
    gid             TEXT PRIMARY KEY,
    post_gid        TEXT NOT NULL REFERENCES bop_posts(gid) ON DELETE CASCADE,
    bop_version_gid TEXT NOT NULL REFERENCES bop_versions(gid) ON DELETE CASCADE,
    op_code         TEXT NOT NULL DEFAULT '',
    op_name         TEXT NOT NULL DEFAULT '',
    seq_no          INT  NOT NULL DEFAULT 0,
    standard_time   REAL NOT NULL DEFAULT 0,
    std_op_gid      TEXT DEFAULT NULL,
    parts           JSONB NOT NULL DEFAULT '[]',
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bop_ops_post ON bop_operations (post_gid);
CREATE INDEX IF NOT EXISTS idx_bop_ops_bop  ON bop_operations (bop_version_gid);

CREATE TABLE IF NOT EXISTS bop_steps (
    gid           TEXT PRIMARY KEY,
    operation_gid TEXT NOT NULL REFERENCES bop_operations(gid) ON DELETE CASCADE,
    step_code     TEXT NOT NULL DEFAULT '',
    step_name     TEXT NOT NULL DEFAULT '',
    seq_no        INT  NOT NULL DEFAULT 0,
    standard_time REAL NOT NULL DEFAULT 0,
    notes         TEXT NOT NULL DEFAULT '',
    meta          JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bop_steps_op ON bop_steps (operation_gid);

CREATE TABLE IF NOT EXISTS operation_resources (
    gid           TEXT PRIMARY KEY,
    operation_gid TEXT NOT NULL REFERENCES bop_operations(gid) ON DELETE CASCADE,
    resource_type TEXT NOT NULL DEFAULT 'tool',
    spec_name     TEXT NOT NULL DEFAULT '',
    spec_params   JSONB NOT NULL DEFAULT '{}',
    qty           REAL NOT NULL DEFAULT 1,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_op_resources_op ON operation_resources (operation_gid);

CREATE TABLE IF NOT EXISTS step_resources (
    gid           TEXT PRIMARY KEY,
    step_gid      TEXT NOT NULL REFERENCES bop_steps(gid) ON DELETE CASCADE,
    resource_type TEXT NOT NULL DEFAULT 'tool',
    spec_name     TEXT NOT NULL DEFAULT '',
    spec_params   JSONB NOT NULL DEFAULT '{}',
    qty           REAL NOT NULL DEFAULT 1,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_step_resources_step ON step_resources (step_gid);

-- 工厂布局模板（产线积木库）
CREATE TABLE IF NOT EXISTS factory_layout_templates (
    gid         TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    factory_gid TEXT REFERENCES factories(gid) ON DELETE CASCADE,
    team_id     TEXT REFERENCES teams(gid) ON DELETE SET NULL,
    stations    JSONB NOT NULL DEFAULT '[]',
    meta        JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_layout_tpl_factory ON factory_layout_templates (factory_gid);


-- ── BOP 示例数据 ──────────────────────────────────────────────

-- 工厂
INSERT INTO factories (gid, name, meta) VALUES
  ('fac_demo_001', '示例总装工厂', '{"city":"上海"}')
ON CONFLICT (gid) DO NOTHING;

-- 工段
INSERT INTO factory_sections (gid, name, factory_gid, sort_order, color, canvas_x, canvas_y, canvas_w, canvas_h) VALUES
  ('fsec_demo_001', '内饰工段', 'fac_demo_001', 0, '#7287fd', 40,  40, 900, 400),
  ('fsec_demo_002', '动力工段', 'fac_demo_001', 1, '#40a02b', 40, 480, 900, 400)
ON CONFLICT (gid) DO NOTHING;

-- 工位
INSERT INTO factory_stations (gid, code, name, factory_section_gid, canvas_x, canvas_y, takt_time, height_mm) VALUES
  ('fsta_demo_001', 'TB01', '工位01', 'fsec_demo_001',  80, 120, 60, 1200),
  ('fsta_demo_002', 'TB02', '工位02', 'fsec_demo_001', 380, 120, 60, 1200),
  ('fsta_demo_003', 'TB03', '工位03', 'fsec_demo_002',  80, 560, 60, 1200),
  ('fsta_demo_004', 'TB04', '工位04', 'fsec_demo_002', 380, 560, 60, 1200)
ON CONFLICT (gid) DO NOTHING;

-- BOP 版本（不绑定具体 project / vehicle_model，开发演示用）
INSERT INTO bop_versions (gid, version_tag, maturity, takt_time, status, factory_gid) VALUES
  ('bopv_demo_001', 'V1.0-概念', 'concept', 60, 'draft', 'fac_demo_001')
ON CONFLICT (gid) DO NOTHING;

-- 岗位
INSERT INTO bop_posts (gid, bop_version_gid, station_gid, post_code, post_name, head_count, sort_order) VALUES
  ('bpost_demo_001', 'bopv_demo_001', 'fsta_demo_001', 'P01A', '内饰工位01-A岗', 1, 0),
  ('bpost_demo_002', 'bopv_demo_001', 'fsta_demo_001', 'P01B', '内饰工位01-B岗', 1, 1),
  ('bpost_demo_003', 'bopv_demo_001', 'fsta_demo_002', 'P02A', '内饰工位02-A岗', 1, 0),
  ('bpost_demo_004', 'bopv_demo_001', 'fsta_demo_003', 'P03A', '动力工位03-A岗', 1, 0),
  ('bpost_demo_005', 'bopv_demo_001', 'fsta_demo_004', 'P04A', '动力工位04-A岗', 1, 0)
ON CONFLICT (gid) DO NOTHING;

-- 工序
INSERT INTO bop_operations (gid, post_gid, bop_version_gid, op_code, op_name, seq_no, standard_time) VALUES
  ('bop_demo_001', 'bpost_demo_001', 'bopv_demo_001', 'OP001', '安装仪表板', 10, 18),
  ('bop_demo_002', 'bpost_demo_001', 'bopv_demo_001', 'OP002', '连接线束', 20, 22),
  ('bop_demo_003', 'bpost_demo_002', 'bopv_demo_001', 'OP003', '安装座椅', 10, 15),
  ('bop_demo_004', 'bpost_demo_003', 'bopv_demo_001', 'OP004', '安装门板', 10, 12),
  ('bop_demo_005', 'bpost_demo_003', 'bopv_demo_001', 'OP005', '安装密封条', 20, 8),
  ('bop_demo_006', 'bpost_demo_004', 'bopv_demo_001', 'OP006', '安装发动机', 10, 35),
  ('bop_demo_007', 'bpost_demo_005', 'bopv_demo_001', 'OP007', '连接排气管', 10, 20)
ON CONFLICT (gid) DO NOTHING;

-- 工步（OP001 示例工步）
INSERT INTO bop_steps (gid, operation_gid, step_code, step_name, seq_no, standard_time, notes) VALUES
  ('bstep_demo_001', 'bop_demo_001', 'S001-1', '取仪表板总成', 1, 3, '从物料架取件'),
  ('bstep_demo_002', 'bop_demo_001', 'S001-2', '对准安装孔', 2, 5, '注意左右对称'),
  ('bstep_demo_003', 'bop_demo_001', 'S001-3', '紧固螺栓', 3, 10, '扭矩25Nm')
ON CONFLICT (gid) DO NOTHING;


-- ── 用户自定义视图配置 ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS view_configs (
    gid        TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '未命名视图',
    module     TEXT NOT NULL DEFAULT '',
    owner_gid  TEXT NOT NULL DEFAULT '',
    is_shared  BOOLEAN NOT NULL DEFAULT FALSE,
    config     JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_view_configs_owner  ON view_configs (owner_gid);
CREATE INDEX IF NOT EXISTS idx_view_configs_module ON view_configs (module);


DO $$
BEGIN
    RAISE NOTICE '✅ ai00_dev 数据库初始化完成';
    RAISE NOTICE '   基础表：teams, system_config, users, project_members, auth_pending';
    RAISE NOTICE '   业务表：projects, work_plans, sections, operation_flat, bom_snapshots,';
    RAISE NOTICE '           part_entries, collab_sessions, approval_orders, std_operations,';
    RAISE NOTICE '           tool_templates, equipment_templates, fixture_templates,';
    RAISE NOTICE '           standard_fasteners, standard_part_names,';
    RAISE NOTICE '           physical_tools, physical_equipments, physical_fixtures,';
    RAISE NOTICE '           follows, notifications';
    RAISE NOTICE '   BOP 画布：factories, factory_sections, factory_stations,';
    RAISE NOTICE '             bop_versions, bop_posts, bop_operations, bop_steps,';
    RAISE NOTICE '             operation_resources, step_resources';
    RAISE NOTICE '   通用组件：view_configs';
END $$;
