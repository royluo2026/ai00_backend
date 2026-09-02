-- Normalize the Base self-annotation aggregate after legacy tables were
-- created with the server-default collation. Runtime reads keep an explicit
-- COLLATE during rolling deployment, so either migration order remains safe.
ALTER TABLE workmanship_base_self_annotations
    MODIFY COLUMN tenant_gid VARCHAR(128) COLLATE utf8mb4_unicode_ci NOT NULL,
    MODIFY COLUMN item_gid VARCHAR(128) COLLATE utf8mb4_unicode_ci NOT NULL,
    MODIFY COLUMN user_gid VARCHAR(128) COLLATE utf8mb4_unicode_ci NOT NULL;

ALTER TABLE workmanship_base_self_annotation_states
    MODIFY COLUMN tenant_gid VARCHAR(128) COLLATE utf8mb4_unicode_ci NOT NULL,
    MODIFY COLUMN item_gid VARCHAR(128) COLLATE utf8mb4_unicode_ci NOT NULL,
    MODIFY COLUMN user_gid VARCHAR(128) COLLATE utf8mb4_unicode_ci NOT NULL;
