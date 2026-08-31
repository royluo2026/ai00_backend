ALTER TABLE workmanship_proj_approval_orders
  ADD COLUMN IF NOT EXISTS team_gid CHAR(36) NULL,
  ADD COLUMN IF NOT EXISTS revision INT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS workmanship_proj_approval_rejection_operations (
  actor_gid VARCHAR(128) NOT NULL,
  team_gid VARCHAR(128) NOT NULL,
  capability_id VARCHAR(128) NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL,
  payload_hash CHAR(64) NOT NULL,
  order_gid CHAR(36) NULL,
  status VARCHAR(32) NOT NULL,
  result_json JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  completed_at DATETIME(6) NULL,
  PRIMARY KEY (actor_gid, team_gid, capability_id, idempotency_key),
  KEY idx_proj_approval_rejection_order (order_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_proj_approval_audit_events (
  gid CHAR(36) PRIMARY KEY,
  order_gid CHAR(36) NOT NULL,
  actor_gid VARCHAR(128) NOT NULL,
  team_gid VARCHAR(128) NOT NULL,
  operation VARCHAR(32) NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL,
  revision INT NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_proj_approval_audit_order (order_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_proj_notification_outbox (
  gid CHAR(36) PRIMARY KEY,
  event_type VARCHAR(128) NOT NULL,
  order_gid CHAR(36) NOT NULL,
  team_gid VARCHAR(128) NOT NULL,
  recipient_gid VARCHAR(128) NOT NULL,
  payload JSON NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY idx_proj_notification_outbox_delivery (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
