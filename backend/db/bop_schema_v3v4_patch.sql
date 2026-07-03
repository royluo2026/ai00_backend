-- ═══════════════════════════════════════════════════════════════════
-- BOP V3+V4 补丁脚本（针对当前数据库实际状态）
-- 文件：backend/db/bop_schema_v3v4_patch.sql
--
-- 与 bop_schema_v3v4.sql 的区别：
--   1. asm_steps / project_roles 已不存在，跳过数据迁移部分
--   2. pbom / pbom_versions 在 bop schema 下（非独立 pbom schema）
--   3. 所有 RENAME COLUMN 用 DO 块保护，幂等安全
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

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
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='bop_version_gid') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN bop_version_gid TO version_gid;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='parent_bop_gid') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN parent_bop_gid TO parent_gid;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='seq_no') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN seq_no TO sort_order;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entries' AND column_name='parent_bop_label') THEN
    ALTER TABLE bop.bop_entries RENAME COLUMN parent_bop_label TO parent_bop_title;
  END IF;
END $$;


-- ═══════════════════════════════════════════════════════════════════
-- ▌V3-3 bop_entry_links 列重命名 + 新增 version_gid
-- ═══════════════════════════════════════════════════════════════════

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='bop_entry_gid') THEN
    ALTER TABLE bop.bop_entry_links RENAME COLUMN bop_entry_gid TO entry_gid;
  END IF;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bop' AND table_name='bop_entry_links' AND column_name='ref_gid') THEN
    ALTER TABLE bop.bop_entry_links RENAME COLUMN ref_gid TO entity_gid;
  END IF;
END $$;

ALTER TABLE bop.bop_entry_links ADD COLUMN IF NOT EXISTS version_gid TEXT;

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
    ADD COLUMN IF NOT EXISTS child_vpps JSONB NOT NULL DEFAULT '[]';


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
    ADD COLUMN IF NOT EXISTS version_type     TEXT NOT NULL DEFAULT 'working',
    ADD COLUMN IF NOT EXISTS pbom_version_gid TEXT,
    ADD COLUMN IF NOT EXISTS owner_gid        TEXT;

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
    ADD COLUMN IF NOT EXISTS vpps_source      TEXT NOT NULL DEFAULT 'auto',
    ADD COLUMN IF NOT EXISTS vpps_reported_at TIMESTAMPTZ;

COMMENT ON COLUMN bop.pbom.vpps_source IS
    'auto = 正常；manual = 人工临时值';
COMMENT ON COLUMN bop.pbom.vpps_reported_at IS
    '提报修改的时间，vpps_source=manual 时填写';


-- ═══════════════════════════════════════════════════════════════════
-- ▌V4-4 bop_steps / bop_operator（已有字段，防御性确认）
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE bop.bop_steps    DROP COLUMN IF EXISTS step_code;
ALTER TABLE bop.bop_steps    ADD COLUMN IF NOT EXISTS operation_code TEXT NOT NULL DEFAULT '';
ALTER TABLE bop.bop_operator ADD COLUMN IF NOT EXISTS operator_code  TEXT NOT NULL DEFAULT '';


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


COMMIT;

-- ═══════════════════════════════════════════════════════════════════
-- 脚本结束
-- ═══════════════════════════════════════════════════════════════════
