CREATE TABLE IF NOT EXISTS workmanship_base_capability_approvals (
  approval_id VARCHAR(64) NOT NULL,
  token_hash CHAR(64) NOT NULL,
  capability_id VARCHAR(128) NOT NULL,
  major_version INT NOT NULL,
  consumer_fingerprint VARCHAR(80) NOT NULL,
  resource_refs_json JSON NOT NULL,
  policy_version VARCHAR(128) NOT NULL,
  confirmation_policy VARCHAR(16) NOT NULL,
  payload_hash VARCHAR(72) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  consumed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (approval_id),
  UNIQUE KEY uq_base_capability_approval_token_hash (token_hash),
  KEY ix_base_capability_approval_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_capability_outcomes (
  operation_id VARCHAR(64) NOT NULL,
  request_id VARCHAR(256) NOT NULL,
  idempotency_scope VARCHAR(80) NOT NULL,
  payload_hash VARCHAR(72) NOT NULL,
  capability_id VARCHAR(128) NOT NULL,
  major_version INT NOT NULL,
  tenant_id VARCHAR(256) NOT NULL,
  consumer_scope VARCHAR(80) NOT NULL,
  actor_id VARCHAR(256) NOT NULL,
  consumer_type VARCHAR(32) NOT NULL,
  consumer_id VARCHAR(256) NOT NULL,
  consumer_instance_id VARCHAR(256) NULL,
  policy_version VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  result_json JSON NULL,
  started_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6) NULL,
  PRIMARY KEY (operation_id),
  UNIQUE KEY uq_base_capability_outcome_idempotency (idempotency_scope),
  KEY ix_base_capability_outcome_request (request_id),
  KEY ix_base_capability_outcome_status (status, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_capability_audit_outbox (
  event_id VARCHAR(80) NOT NULL,
  operation_id VARCHAR(64) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  payload_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  delivered_at DATETIME(6) NULL,
  attempt_count INT NOT NULL DEFAULT 0,
  last_error_code VARCHAR(128) NULL,
  PRIMARY KEY (event_id),
  UNIQUE KEY uq_base_capability_audit_operation (operation_id),
  KEY ix_base_capability_audit_pending (delivered_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_capability_audit_ledger (
  event_id VARCHAR(80) NOT NULL,
  operation_id VARCHAR(64) NOT NULL,
  capability_id VARCHAR(128) NOT NULL,
  major_version INT NOT NULL,
  request_id VARCHAR(256) NOT NULL,
  tenant_id VARCHAR(256) NOT NULL,
  actor_id VARCHAR(256) NOT NULL,
  consumer_type VARCHAR(32) NOT NULL,
  consumer_id VARCHAR(256) NOT NULL,
  consumer_instance_id VARCHAR(256) NULL,
  policy_version VARCHAR(128) NOT NULL,
  payload_hash VARCHAR(72) NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (event_id),
  KEY ix_base_capability_audit_actor (actor_id, created_at),
  KEY ix_base_capability_audit_capability (capability_id, created_at),
  KEY ix_base_capability_audit_tenant (tenant_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_capability_rate_windows (
  scope_hash CHAR(64) NOT NULL,
  window_started_at DATETIME(6) NOT NULL,
  cost_used INT NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  PRIMARY KEY (scope_hash, window_started_at),
  KEY ix_base_capability_rate_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
