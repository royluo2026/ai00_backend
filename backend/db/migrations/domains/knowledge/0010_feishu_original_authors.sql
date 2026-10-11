-- Attribution is separate from created_by, which remains the authenticated operator.
ALTER TABLE workmanship_know_documents ADD COLUMN IF NOT EXISTS source_author_open_id VARCHAR(128) NULL;
ALTER TABLE workmanship_know_documents ADD COLUMN IF NOT EXISTS source_author_name VARCHAR(255) NULL;
ALTER TABLE workmanship_know_feishu_snapshots ADD COLUMN IF NOT EXISTS source_author_open_id VARCHAR(128) NULL;
ALTER TABLE workmanship_know_feishu_snapshots ADD COLUMN IF NOT EXISTS source_author_name VARCHAR(255) NULL;
