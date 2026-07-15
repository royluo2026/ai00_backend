-- entry_cascade_delete_patch.sql
-- 为 bop_entry_links 及各实体表添加 deleted_at，支持软删除级联
-- 在 DBeaver 中手动执行

ALTER TABLE bop.bop_entry_links ADD COLUMN deleted_at TIMESTAMPTZ;

ALTER TABLE bop.bop_line        ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_station     ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_process     ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_steps       ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE bop.bop_operator    ADD COLUMN deleted_at TIMESTAMPTZ;
