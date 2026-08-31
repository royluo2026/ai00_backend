-- Durable, tenant-scoped Agent canvas execution control.
ALTER TABLE workmanship_app_skills
  ADD COLUMN IF NOT EXISTS revision BIGINT UNSIGNED NOT NULL DEFAULT 1 AFTER status;

CREATE TABLE IF NOT EXISTS workmanship_agent_canvas_runs (
  run_id VARCHAR(128) PRIMARY KEY,
  run_token_hash CHAR(64) NOT NULL,
  actor_gid VARCHAR(191) NOT NULL,
  team_gid VARCHAR(191) NOT NULL,
  skill_gid VARCHAR(191) NOT NULL,
  skill_revision BIGINT UNSIGNED NOT NULL,
  status VARCHAR(32) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  pause_token_hash CHAR(64) NULL,
  checkpoint_json JSON NULL,
  result_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_agent_canvas_run_token (run_token_hash),
  INDEX idx_agent_canvas_run_principal (team_gid, actor_gid, status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_agent_canvas_invocations (
  invocation_id VARCHAR(128) PRIMARY KEY,
  run_id VARCHAR(128) NOT NULL,
  actor_gid VARCHAR(191) NOT NULL,
  team_gid VARCHAR(191) NOT NULL,
  capability_id VARCHAR(255) NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL,
  payload_hash CHAR(64) NOT NULL,
  target_state VARCHAR(32) NOT NULL,
  request_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  lease_owner VARCHAR(191) NULL,
  lease_token VARCHAR(255) NULL,
  lease_expires_at DATETIME(6) NULL,
  attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
  target_dispatched_at DATETIME(6) NULL,
  next_attempt_at DATETIME(6) NULL,
  result_json JSON NOT NULL,
  error_code VARCHAR(128) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_agent_canvas_invocation_idempotency
    (actor_gid, team_gid, capability_id, idempotency_key),
  INDEX idx_agent_canvas_invocation_claim
    (status, next_attempt_at, lease_expires_at, created_at),
  CONSTRAINT fk_agent_canvas_invocation_run FOREIGN KEY (run_id)
    REFERENCES workmanship_agent_canvas_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_agent_canvas_audit_events (
  event_id VARCHAR(128) PRIMARY KEY,
  invocation_id VARCHAR(128) NOT NULL,
  run_id VARCHAR(128) NOT NULL,
  actor_gid VARCHAR(191) NOT NULL,
  team_gid VARCHAR(191) NOT NULL,
  status VARCHAR(32) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  error_code VARCHAR(128) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_agent_canvas_audit_invocation (invocation_id, created_at),
  CONSTRAINT fk_agent_canvas_audit_invocation FOREIGN KEY (invocation_id)
    REFERENCES workmanship_agent_canvas_invocations(invocation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workmanship_agent_canvas_runtime_results (
  invocation_id VARCHAR(128) PRIMARY KEY,
  run_id VARCHAR(128) NOT NULL,
  actor_gid VARCHAR(191) NOT NULL,
  team_gid VARCHAR(191) NOT NULL,
  status VARCHAR(32) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  result_json JSON NOT NULL,
  completed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_agent_canvas_runtime_result_principal
    (team_gid, actor_gid, completed_at),
  CONSTRAINT fk_agent_canvas_runtime_result_invocation FOREIGN KEY (invocation_id)
    REFERENCES workmanship_agent_canvas_invocations(invocation_id),
  CONSTRAINT fk_agent_canvas_runtime_result_run FOREIGN KEY (run_id)
    REFERENCES workmanship_agent_canvas_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
