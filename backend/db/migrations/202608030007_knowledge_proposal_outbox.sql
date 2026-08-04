CREATE TABLE IF NOT EXISTS workmanship_know_proposals (
    gid VARCHAR(128) PRIMARY KEY, base_gid VARCHAR(128) NULL,
    title VARCHAR(255) NOT NULL, content_md LONGTEXT NOT NULL,
    summary TEXT NULL, tags JSON NULL, status VARCHAR(32) NOT NULL DEFAULT 'pending',
    creator_gid VARCHAR(128) NOT NULL, team_gid VARCHAR(128) NULL,
    reviewer_gid VARCHAR(128) NULL, review_note TEXT NULL, reviewed_at DATETIME NULL,
    published_gid VARCHAR(128) NULL, ois_url TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_know_proposals_creator (creator_gid), INDEX idx_know_proposals_status (status),
    INDEX idx_know_proposals_team (team_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE workmanship_know_proposals ADD COLUMN IF NOT EXISTS reviewer_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_know_proposals ADD COLUMN IF NOT EXISTS review_note TEXT NULL;
ALTER TABLE workmanship_know_proposals ADD COLUMN IF NOT EXISTS reviewed_at DATETIME NULL;
ALTER TABLE workmanship_know_proposals ADD COLUMN IF NOT EXISTS published_gid VARCHAR(128) NULL;
ALTER TABLE workmanship_know_proposals ADD COLUMN IF NOT EXISTS ois_url TEXT NULL;

CREATE TABLE IF NOT EXISTS workmanship_know_publish_outbox (
    gid VARCHAR(128) PRIMARY KEY, proposal_gid VARCHAR(128) NOT NULL,
    payload JSON NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0, next_retry_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_publish_outbox_status (status, next_retry_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
