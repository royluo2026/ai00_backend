-- ═══════════════════════════════════════════════════════════════════
-- 工艺规划域 BOP V3 + V4 合并迁移脚本（PostgreSQL）
-- 文件：backend/db/bop_schema_v3v4.sql
--
-- 在 bop_schema_v2.sql 执行后运行。幂等设计：可重复执行。
--
-- 变更概要（V3）：
--   1a. asm_steps 合并到 bop_steps（工步即操作）
--   1b. project_roles 合并到 bop_operator（岗位统一管理）
--   1c. 所有实体表 name → title
--   1d. bop_entries 字段整理（删冗余、重命名、新增 child_vpps）
--       bop_version_gid → version_gid
--       parent_bop_gid  → parent_gid
--       seq_no          → sort_order
--       parent_bop_label → parent_bop_title
--   1e. bop_process 删除 vpps_part / part_feed
--   1f. 全表新增软删除 / 归档字段（is_deleted, is_archived）
--   1g. bop_entry_links 字段整理
--       bop_entry_gid → entry_gid
--       ref_gid       → entity_gid
--       新增 version_gid（冗余，供跨表过滤加速）
--
-- 变更概要（V4）：
--   2a. bop_versions 新增 version_type / pbom_version_gid / owner_gid
--   2b. pbom_versions.status 值迁移（draft→raw / released→ready）
--   2c. pbom 新增 vpps_source / vpps_reported_at
--   2d. bop_steps 移除 step_code（v3 错误添加），确认 operation_code 存在
--   2e. bop_operator 补全 operator_code
--   2f. 新建 gbop_match_staging 中间表
--   2g. bop_versions 新索引
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

-- ═══════════════════════════════════════════════════════════════════
-- ▌V3 ▐
-- ═══════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 阶段一：实体表 name → title（先于数据迁移）
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_line            RENAME COLUMN name TO title;
ALTER TABLE bop.bop_station         RENAME COLUMN name TO title;
ALTER TABLE bop.bop_process         RENAME COLUMN name TO title;
ALTER TABLE bop.bop_steps           RENAME COLUMN name TO title;
ALTER TABLE bop.bop_operator        RENAME COLUMN name TO title;
ALTER TABLE bop.bop_equipments      RENAME COLUMN name TO title;
ALTER TABLE bop.bop_fixtures        RENAME COLUMN name TO title;
ALTER TABLE bop.bop_tools           RENAME COLUMN name TO title;
ALTER TABLE bop.bop_control_plan    RENAME COLUMN name TO title;
ALTER TABLE bop.bop_process_charts  RENAME COLUMN name TO title;
ALTER TABLE bop.bop_floor_height    RENAME COLUMN name TO title;
ALTER TABLE bop.bop_jack_pos        RENAME COLUMN name TO title;
-- bop_staging 已有 title 字段，无需改名


-- ─────────────────────────────────────────────────────────────────────────────
-- 阶段二：bop_entries 列重命名
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_entries RENAME COLUMN bop_version_gid  TO version_gid;
ALTER TABLE bop.bop_entries RENAME COLUMN parent_bop_gid   TO parent_gid;
ALTER TABLE bop.bop_entries RENAME COLUMN seq_no           TO sort_order;
ALTER TABLE bop.bop_entries RENAME COLUMN parent_bop_label TO parent_bop_title;


-- ─────────────────────────────────────────────────────────────────────────────
-- 阶段三：bop_entry_links 列重命名 + 新增 version_gid
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_entry_links RENAME COLUMN bop_entry_gid TO entry_gid;
ALTER TABLE bop.bop_entry_links RENAME COLUMN ref_gid        TO entity_gid;
ALTER TABLE bop.bop_entry_links ADD COLUMN IF NOT EXISTS version_gid TEXT;

-- 回填 version_gid（从关联的 bop_entries 中取）
UPDATE bop.bop_entry_links l
   SET version_gid = e.version_gid
  FROM bop.bop_entries e
 WHERE l.entry_gid = e.gid
   AND l.version_gid IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- 1a. 合并 asm_steps → bop_steps（工步即操作）
-- ─────────────────────────────────────────────────────────────────────────────

-- 给 bop_steps 追加 step_code（工步编码，原属 asm_steps）
-- 注：此字段在 V4 阶段会被移除，此处仅为数据迁移过渡
ALTER TABLE bop.bop_steps ADD COLUMN IF NOT EXISTS step_code TEXT NOT NULL DEFAULT '';

-- 迁移 asm_steps 存量数据
INSERT INTO bop.bop_steps (
    gid, project_gid, title, step_code,
    vpps, vpps_desc, source_type, source_ref_gid, created_by
)
SELECT
    s.gid, s.project_gid, s.title,
    COALESCE(s.step_code, ''),
    s.vpps, NULL,
    s.source_type, s.source_ref_gid, s.created_by
FROM bop.asm_steps s
ON CONFLICT (gid) DO NOTHING;

DROP TABLE IF EXISTS bop.asm_steps CASCADE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 1b. 合并 project_roles → bop_operator（岗位统一管理）
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_operator ADD COLUMN IF NOT EXISTS factory_role_ref_gid TEXT;
ALTER TABLE bop.bop_operator ADD COLUMN IF NOT EXISTS role_type             TEXT NOT NULL DEFAULT '';

UPDATE bop.bop_operator o
   SET factory_role_ref_gid = pr.factory_role_ref_gid,
       role_type             = COALESCE(pr.role_type, '')
  FROM bop.project_roles pr
 WHERE o.gid = pr.gid;

INSERT INTO bop.bop_operator (
    gid, project_gid, title, factory_role_ref_gid, role_type,
    headcount, owner_gid, created_by
)
SELECT
    r.gid, r.project_gid, r.title,
    r.factory_role_ref_gid, COALESCE(r.role_type, ''),
    r.headcount, r.owner_gid, r.created_by
FROM bop.project_roles r
ON CONFLICT (gid) DO NOTHING;

DROP TABLE IF EXISTS bop.project_roles CASCADE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 1d. bop_entries 字段整理
-- ─────────────────────────────────────────────────────────────────────────────

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
    ADD COLUMN IF NOT EXISTS child_vpps JSONB NOT NULL DEFAULT '[]';


-- ─────────────────────────────────────────────────────────────────────────────
-- 1e. bop_process 删除 vpps_part / part_feed
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_process
    DROP COLUMN IF EXISTS vpps_part,
    DROP COLUMN IF EXISTS part_feed;


-- ─────────────────────────────────────────────────────────────────────────────
-- 1f. 全表新增软删除 / 归档字段
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'bop.bop_versions',
        'bop.bop_entries',
        'bop.bop_entry_links',
        'bop.bop_line',
        'bop.bop_station',
        'bop.bop_process',
        'bop.bop_steps',
        'bop.bop_operator',
        'bop.bop_equipments',
        'bop.bop_fixtures',
        'bop.bop_tools',
        'bop.bop_control_plan',
        'bop.bop_process_charts',
        'bop.bop_floor_height',
        'bop.bop_jack_pos',
        'bop.bop_staging'
    ]
    LOOP
        EXECUTE format(
            'ALTER TABLE %s
                 ADD COLUMN IF NOT EXISTS is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
                 ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE,
                 ADD COLUMN IF NOT EXISTS deleted_at  TIMESTAMPTZ,
                 ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ',
            t
        );
    END LOOP;
END$$;

UPDATE bop.bop_entries SET is_deleted  = TRUE WHERE deleted_at  IS NOT NULL AND is_deleted  = FALSE;
UPDATE bop.bop_entries SET is_archived = TRUE WHERE archived_at IS NOT NULL AND is_archived = FALSE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 索引重建
-- ─────────────────────────────────────────────────────────────────────────────

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
-- step_code 索引在 V4 阶段随列一起删除，此处不建
DROP INDEX IF EXISTS bop.idx_proj_roles_proj;
DROP INDEX IF EXISTS bop.idx_proj_roles_vpps;


-- ─────────────────────────────────────────────────────────────────────────────
-- 存量 link_type 迁移：旧 asm_* 命名 → 统一为 bop_* 命名
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE bop.bop_entry_links SET link_type = 'bop_line'
    WHERE link_type = 'asm_line_process';
UPDATE bop.bop_entry_links SET link_type = 'bop_station'
    WHERE link_type = 'asm_station_process';
UPDATE bop.bop_entry_links SET link_type = 'bop_steps'
    WHERE link_type = 'asm_operation';
UPDATE bop.bop_entry_links SET link_type = 'bop_operator'
    WHERE link_type IN ('asm_operator_process', 'project_roles');


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4 ▐
-- ═══════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- 2a. bop_versions 新增字段
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_versions
    ADD COLUMN IF NOT EXISTS version_type     TEXT NOT NULL DEFAULT 'working',
    ADD COLUMN IF NOT EXISTS pbom_version_gid TEXT,
    ADD COLUMN IF NOT EXISTS owner_gid        TEXT;

COMMENT ON COLUMN bop.bop_versions.version_type IS
    'working = 工作版本（必须绑定 pbom_version_gid）；template = 工厂模板版本（pbom_version_gid=NULL）';
COMMENT ON COLUMN bop.bop_versions.pbom_version_gid IS
    'working 版本必填，关联 pbom.pbom_versions.gid；template 版本为 NULL';
COMMENT ON COLUMN bop.bop_versions.owner_gid IS
    'template 版本的 owner 控制 update-from 权限；working 版本 owner 可选';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2b. pbom_versions.status 值迁移（draft→raw / released→ready）
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE pbom.pbom_versions SET status = 'raw'   WHERE status = 'draft';
UPDATE pbom.pbom_versions SET status = 'ready' WHERE status = 'released';

COMMENT ON COLUMN pbom.pbom_versions.status IS
    'raw = 刚导入，vpps 未校核；ready = 预处理完成，可被 BOP 版本绑定';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2c. pbom 表新增 vpps_source / vpps_reported_at
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE pbom.pbom
    ADD COLUMN IF NOT EXISTS vpps_source      TEXT NOT NULL DEFAULT 'auto',
    ADD COLUMN IF NOT EXISTS vpps_reported_at TIMESTAMPTZ;

COMMENT ON COLUMN pbom.pbom.vpps_source IS
    'auto = 正常；manual = 人工临时值，需在所有展示场景加 ⚠ 标志';
COMMENT ON COLUMN pbom.pbom.vpps_reported_at IS
    '提报修改的时间，vpps_source=manual 时填写';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2d. bop_steps 移除 step_code（v3 过渡字段）+ 确认 operation_code 存在
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_steps DROP COLUMN IF EXISTS step_code;
ALTER TABLE bop.bop_steps ADD COLUMN IF NOT EXISTS operation_code TEXT NOT NULL DEFAULT '';
DROP INDEX IF EXISTS bop.idx_bop_steps_step_code;

COMMENT ON COLUMN bop.bop_steps.operation_code IS
    '操作编码（原 Excel 字段，由 import-tc 写入）';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2e. bop_operator.operator_code 补全
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE bop.bop_operator
    ADD COLUMN IF NOT EXISTS operator_code TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN bop.bop_operator.operator_code IS
    '岗位编码（原 Excel 字段）';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2f. 新建 gbop_match_staging 中间表
-- ─────────────────────────────────────────────────────────────────────────────

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
    '车型工序导航卡 GBOP 匹配中间表；只记录过程，不缓存实体数据';
COMMENT ON COLUMN bop.gbop_match_staging.match_status IS
    'pending / confirmed / skipped';
COMMENT ON COLUMN bop.gbop_match_staging.created_entry_gid IS
    'auto-link 写入 bop_entries 后的追溯 gid；NULL = 尚未执行 auto-link';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2g. bop_versions 新索引
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_bop_ver_type
    ON bop.bop_versions(version_type) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_bop_ver_pbom
    ON bop.bop_versions(pbom_version_gid) WHERE pbom_version_gid IS NOT NULL;


COMMIT;

-- ═══════════════════════════════════════════════════════════════════
-- 脚本结束
-- ═══════════════════════════════════════════════════════════════════
