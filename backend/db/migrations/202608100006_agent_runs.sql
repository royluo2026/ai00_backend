CREATE TABLE IF NOT EXISTS workmanship_agent_runs (
  run_id VARCHAR(64) NOT NULL,
  session_gid VARCHAR(64) NOT NULL,
  tenant_gid VARCHAR(256) NOT NULL,
  requested_by_user_gid VARCHAR(256) NOT NULL,
  channel_type VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  run_input_ciphertext MEDIUMTEXT NOT NULL,
  catalog_release VARCHAR(64) NOT NULL,
  delegation_id VARCHAR(256) NOT NULL,
  delegation_ciphertext MEDIUMTEXT NOT NULL,
  selected_tools_json JSON NOT NULL,
  version BIGINT UNSIGNED NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  PRIMARY KEY (run_id),
  KEY ix_agent_runs_session (session_gid, created_at),
  KEY ix_agent_runs_requester (tenant_gid, requested_by_user_gid, created_at),
  KEY ix_agent_runs_status (status, updated_at),
  UNIQUE KEY uq_agent_runs_delegation (delegation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_agent_run_participants (
  run_id VARCHAR(64) NOT NULL,
  principal_gid VARCHAR(256) NOT NULL,
  principal_type VARCHAR(32) NOT NULL,
  participant_role VARCHAR(32) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (run_id, principal_type, principal_gid),
  KEY ix_agent_run_participant_principal (principal_type, principal_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_agent_run_approvals (
  approval_request_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  capability_id VARCHAR(255) NOT NULL,
  major_version INT UNSIGNED NOT NULL,
  request_id VARCHAR(256) NOT NULL,
  payload_hash CHAR(64) NOT NULL,
  challenge_json JSON NOT NULL,
  request_ciphertext MEDIUMTEXT NOT NULL,
  status VARCHAR(32) NOT NULL,
  decided_by VARCHAR(256) NULL,
  created_at DATETIME(6) NOT NULL,
  decided_at DATETIME(6) NULL,
  version BIGINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (approval_request_id),
  UNIQUE KEY uq_agent_run_approval_request (run_id, request_id),
  KEY ix_agent_run_approval_status (run_id, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_agent_run_tool_results (
  result_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  call_id VARCHAR(256) NOT NULL,
  capability_id VARCHAR(255) NOT NULL,
  major_version INT UNSIGNED NOT NULL,
  full_result_json JSON NOT NULL,
  projected_result_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (result_id),
  UNIQUE KEY uq_agent_run_tool_call (run_id, call_id),
  KEY ix_agent_run_tool_capability (run_id, capability_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
