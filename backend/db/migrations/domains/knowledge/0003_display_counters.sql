CREATE TABLE IF NOT EXISTS workmanship_know_display_counters (
  seq_name VARCHAR(128) PRIMARY KEY,
  val BIGINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_know_item_history (
  gid VARCHAR(64) PRIMARY KEY,
  id VARCHAR(64) NOT NULL UNIQUE,
  item_gid VARCHAR(64) NOT NULL,
  author_name VARCHAR(255) NOT NULL DEFAULT '',
  author_gid VARCHAR(64) NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_know_item_history_item_created (item_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
