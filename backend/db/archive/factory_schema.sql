-- ═══════════════════════════════════════════════════════════════════
-- 工厂资源域 + 缺失基础设施表 补建脚本（PostgreSQL）
-- 文件：backend/db/factory_schema.sql
--
-- 执行方式：在 DBeaver 对 ai00_dev 数据库执行
-- 执行顺序：本脚本 → bop_schema_v2.sql
--
-- 本脚本覆盖所有首次部署时缺失的表，全部 IF NOT EXISTS，幂等安全。
-- ═══════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────
-- 1. 工厂资源域（factory_resource BC）
-- ───────────────────────────────────────────────────────────────────

-- 工厂（物理工厂，逻辑隔离单元）
CREATE TABLE IF NOT EXISTS factories (
    gid        TEXT        PRIMARY KEY,
    name       TEXT        NOT NULL DEFAULT '',
    team_id    TEXT        REFERENCES teams(gid) ON DELETE SET NULL,
    meta       JSONB       NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_factories_team ON factories(team_id);


-- 工段（物理区域，工厂的一级分区）
CREATE TABLE IF NOT EXISTS factory_sections (
    gid         TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL DEFAULT '',
    factory_gid TEXT        NOT NULL REFERENCES factories(gid) ON DELETE CASCADE,
    sort_order  INT         NOT NULL DEFAULT 0,
    color       TEXT        NOT NULL DEFAULT '#7287fd',
    canvas_x    REAL        NOT NULL DEFAULT 0,
    canvas_y    REAL        NOT NULL DEFAULT 0,
    canvas_w    REAL        NOT NULL DEFAULT 400,
    canvas_h    REAL        NOT NULL DEFAULT 300,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_factory_sections_factory ON factory_sections(factory_gid);


-- 工位（物理站位，每条记录对应一个工位，如 TB01L / TB01R）
CREATE TABLE IF NOT EXISTS factory_stations (
    gid                 TEXT        PRIMARY KEY,
    code                TEXT        NOT NULL DEFAULT '',
    name                TEXT        NOT NULL DEFAULT '',
    factory_section_gid TEXT        NOT NULL REFERENCES factory_sections(gid) ON DELETE CASCADE,
    canvas_x            REAL        NOT NULL DEFAULT 0,
    canvas_y            REAL        NOT NULL DEFAULT 0,
    takt_time           REAL        NOT NULL DEFAULT 60,
    height_mm           INT         NOT NULL DEFAULT 1200,
    meta                JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_factory_stations_section ON factory_stations(factory_section_gid);


-- 工厂布局模板（产线积木库：保存一组工位相对坐标，方便快速铺站）
CREATE TABLE IF NOT EXISTS factory_layout_templates (
    gid         TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL DEFAULT '',
    factory_gid TEXT        REFERENCES factories(gid) ON DELETE CASCADE,
    team_id     TEXT        REFERENCES teams(gid) ON DELETE SET NULL,
    -- [{code, name, rel_x, rel_y, takt_time, height_mm}]
    stations    JSONB       NOT NULL DEFAULT '[]',
    meta        JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_layout_tpl_factory ON factory_layout_templates(factory_gid);


-- ───────────────────────────────────────────────────────────────────
-- 2. 关注 & 通知
-- ───────────────────────────────────────────────────────────────────

-- 关注（用户订阅条目变更）
-- notify_on 为 JSONB 数组，取值：
--   any_change / status_change / comment_added / resolved / assigned_to_me / mentioned
CREATE TABLE IF NOT EXISTS follows (
    gid        TEXT        PRIMARY KEY,
    user_gid   TEXT        NOT NULL REFERENCES users(gid) ON DELETE CASCADE,
    item_type  TEXT        NOT NULL,  -- task|issue|project|knowledge|rule|std_op
    item_gid   TEXT        NOT NULL,
    item_title TEXT        NOT NULL DEFAULT '',
    notify_on  JSONB       NOT NULL DEFAULT '["any_change"]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_gid, item_type, item_gid)
);
CREATE INDEX IF NOT EXISTS idx_follows_user ON follows(user_gid);
CREATE INDEX IF NOT EXISTS idx_follows_item ON follows(item_type, item_gid);


-- 通知消息
CREATE TABLE IF NOT EXISTS notifications (
    gid        TEXT        PRIMARY KEY,
    user_gid   TEXT        NOT NULL REFERENCES users(gid) ON DELETE CASCADE,
    type       TEXT        NOT NULL,  -- item_status|comment_added|resolved|assigned|mentioned
    item_type  TEXT        DEFAULT NULL,
    item_gid   TEXT        DEFAULT NULL,
    title      TEXT        NOT NULL DEFAULT '',
    body       TEXT        NOT NULL DEFAULT '',
    is_read    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_user_unread ON notifications(user_gid, is_read);


-- ───────────────────────────────────────────────────────────────────
-- 3. 导出模板
-- ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS export_templates (
    gid        TEXT        PRIMARY KEY,
    name       TEXT        NOT NULL DEFAULT '',
    module     TEXT        NOT NULL DEFAULT '',   -- 'factory_resource'|'craft_table'|'issue'|'*'
    owner_gid  TEXT        REFERENCES users(gid) ON DELETE SET NULL,
    is_shared  BOOLEAN     NOT NULL DEFAULT FALSE,
    -- {columns:[{key,label,width,include}], styles:{headerBg,headerFg,altRowBg,borderStyle,fontSize}}
    config     JSONB       NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_export_templates_module ON export_templates(module);
CREATE INDEX IF NOT EXISTS idx_export_templates_owner  ON export_templates(owner_gid);


-- ───────────────────────────────────────────────────────────────────
-- 4. 任务模板（项目标准内容清单实例化）
-- ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS task_templates (
    gid         TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL,
    description TEXT        NOT NULL DEFAULT '',
    scope       TEXT        NOT NULL DEFAULT 'system',  -- system|team|personal
    owner_gid   TEXT        REFERENCES users(gid) ON DELETE SET NULL,
    version     INTEGER     NOT NULL DEFAULT 1,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_template_items (
    gid             TEXT    PRIMARY KEY,
    template_gid    TEXT    NOT NULL REFERENCES task_templates(gid) ON DELETE CASCADE,
    title_pattern   TEXT    NOT NULL,          -- 支持 {{project_name}} {{project_code}} 变量
    description     TEXT    NOT NULL DEFAULT '',
    priority        TEXT    NOT NULL DEFAULT 'normal',
    assignee_role   TEXT    DEFAULT NULL,      -- 角色占位，实例化时映射到具体人
    due_offset_days INTEGER DEFAULT NULL,      -- 相对项目开始日的偏移天数，NULL=无截止日
    share_scope     TEXT    NOT NULL DEFAULT 'team',
    sort_order      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tti_template ON task_template_items(template_gid);


-- ───────────────────────────────────────────────────────────────────
-- 5. 流程引擎（Flow Engine）
-- ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS flows (
    gid         TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL,
    description TEXT        DEFAULT '',
    flowdef     TEXT        NOT NULL DEFAULT '',  -- YAML 字符串
    status      TEXT        NOT NULL DEFAULT 'draft',  -- draft|active|archived
    last_run_at TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_flows_status ON flows(status);

CREATE TABLE IF NOT EXISTS flow_runs (
    gid             TEXT        PRIMARY KEY,
    flow_gid        TEXT        NOT NULL REFERENCES flows(gid) ON DELETE CASCADE,
    status          TEXT        NOT NULL DEFAULT 'pending',  -- pending|running|paused|completed|failed
    mode            TEXT        NOT NULL DEFAULT 'auto',     -- auto|step
    current_node_id TEXT,
    context_data    JSONB       NOT NULL DEFAULT '{}',
    error_msg       TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_flow_runs_flow ON flow_runs(flow_gid);


-- ───────────────────────────────────────────────────────────────────
-- 6. 工作台标注数据
-- ───────────────────────────────────────────────────────────────────

-- key 格式：wb:ann:{gid}（与前端 localStorage key 相同）
CREATE TABLE IF NOT EXISTS wb_annotations (
    key        TEXT        PRIMARY KEY,
    data       TEXT        NOT NULL DEFAULT '{}',  -- JSON 字符串
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ═══════════════════════════════════════════════════════════════════
-- 脚本结束
--
-- 执行完本脚本后，继续执行 bop_schema_v2.sql（BOP 工艺规划域）
-- ═══════════════════════════════════════════════════════════════════
