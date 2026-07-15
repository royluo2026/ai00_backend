-- bop_nav_patch.sql
-- 为 gbop_match_staging 添加 extra_entry_gids（多操作匹配支持）
-- 在 DBeaver 手动执行

ALTER TABLE bop.gbop_match_staging
    ADD COLUMN extra_entry_gids JSONB NOT NULL DEFAULT '[]';

COMMENT ON COLUMN bop.gbop_match_staging.extra_entry_gids IS
    '额外关联的 GBOP entry gid 列表；主操作用 gbop_entry_gid，附加操作存此处';
