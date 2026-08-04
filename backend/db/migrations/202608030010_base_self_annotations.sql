CREATE TABLE IF NOT EXISTS workmanship_base_self_annotations (
    item_gid VARCHAR(128) NOT NULL,
    user_gid VARCHAR(128) NOT NULL,
    module VARCHAR(128) NOT NULL DEFAULT '',
    item_title VARCHAR(512) NOT NULL DEFAULT '',
    self_status VARCHAR(64) NOT NULL DEFAULT '',
    self_schedule VARCHAR(128) NOT NULL DEFAULT '',
    self_note TEXT NULL,
    self_attachments JSON NOT NULL DEFAULT (JSON_ARRAY()),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (item_gid, user_gid),
    INDEX idx_self_annotations_user (user_gid, updated_at),
    INDEX idx_self_annotations_module (user_gid, module, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
