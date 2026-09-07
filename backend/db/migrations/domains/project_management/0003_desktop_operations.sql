CREATE TABLE IF NOT EXISTS workmanship_proj_desktop_operations (
  actor_gid VARCHAR(128) NOT NULL,
  team_gid VARCHAR(128) NOT NULL,
  capability_id VARCHAR(128) NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL,
  payload_hash CHAR(64) NOT NULL,
  result_text TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  completed_at DATETIME(6) NULL,
  PRIMARY KEY (actor_gid, team_gid, capability_id, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
