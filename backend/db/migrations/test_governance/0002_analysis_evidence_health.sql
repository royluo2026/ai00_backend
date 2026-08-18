CREATE TABLE IF NOT EXISTS workmanship_base_capability_evidence (
  evidence_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  implementation_node_gid BIGINT NULL,
  evidence_type VARCHAR(32) NOT NULL,
  evidence_level VARCHAR(32) NOT NULL,
  result_status VARCHAR(32) NOT NULL,
  source_hash VARCHAR(71) NOT NULL,
  observed_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NULL,
  summary VARCHAR(1000) NOT NULL,
  detail_json LONGTEXT NOT NULL,
  PRIMARY KEY (evidence_gid),
  KEY ix_capability_evidence_snapshot (snapshot_gid),
  KEY ix_capability_evidence_version (capability_version_gid),
  KEY ix_capability_evidence_expiry (expires_at),
  CONSTRAINT fk_capability_evidence_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid),
  CONSTRAINT fk_capability_evidence_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid),
  CONSTRAINT fk_capability_evidence_node FOREIGN KEY (implementation_node_gid)
    REFERENCES workmanship_base_capability_implementation_nodes (implementation_node_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_test_runs (
  test_run_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  profile VARCHAR(64) NOT NULL,
  environment_key VARCHAR(128) NOT NULL,
  requested_by_gid BIGINT NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  summary_json LONGTEXT NOT NULL,
  PRIMARY KEY (test_run_gid),
  UNIQUE KEY uq_capability_test_idempotency (profile, environment_key, idempotency_key),
  KEY ix_capability_test_run_status (status),
  KEY ix_capability_test_run_snapshot (snapshot_gid),
  CONSTRAINT fk_capability_test_run_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_test_results (
  test_result_gid BIGINT NOT NULL,
  test_run_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  case_key VARCHAR(256) NOT NULL,
  evidence_level VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  duration_ms BIGINT NOT NULL,
  error_code VARCHAR(128) NULL,
  redacted_detail_json LONGTEXT NOT NULL,
  PRIMARY KEY (test_result_gid),
  UNIQUE KEY uq_capability_test_result (test_run_gid, capability_version_gid, case_key),
  KEY ix_capability_test_result_version (capability_version_gid),
  KEY ix_capability_test_result_status (status),
  CONSTRAINT fk_capability_test_result_run FOREIGN KEY (test_run_gid)
    REFERENCES workmanship_base_capability_test_runs (test_run_gid),
  CONSTRAINT fk_capability_test_result_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_health_rollups (
  health_rollup_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  health_status VARCHAR(32) NOT NULL,
  evidence_coverage DECIMAL(6,5) NOT NULL,
  blocking_finding_count INT NOT NULL,
  warning_finding_count INT NOT NULL,
  last_verified_at DATETIME(6) NULL,
  computed_at DATETIME(6) NOT NULL,
  PRIMARY KEY (health_rollup_gid),
  UNIQUE KEY uq_capability_health_rollup (snapshot_gid, capability_version_gid),
  KEY ix_capability_health_version (capability_version_gid),
  KEY ix_capability_health_status (health_status),
  CONSTRAINT fk_capability_health_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid),
  CONSTRAINT fk_capability_health_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_analysis_runs (
  analysis_run_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  analysis_type VARCHAR(64) NOT NULL,
  scope_type VARCHAR(64) NOT NULL,
  scope_json LONGTEXT NOT NULL,
  deterministic_status VARCHAR(32) NOT NULL,
  ai_advisory_status VARCHAR(32) NOT NULL,
  requested_by_gid BIGINT NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  model_ref VARCHAR(256) NULL,
  prompt_hash VARCHAR(71) NULL,
  result_summary_json LONGTEXT NOT NULL,
  PRIMARY KEY (analysis_run_gid),
  UNIQUE KEY uq_capability_analysis_idempotency (snapshot_gid, idempotency_key),
  KEY ix_capability_analysis_snapshot (snapshot_gid),
  KEY ix_capability_analysis_status (deterministic_status),
  CONSTRAINT fk_capability_analysis_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_findings (
  finding_gid BIGINT NOT NULL,
  analysis_run_gid BIGINT NULL,
  snapshot_gid BIGINT NOT NULL,
  finding_type VARCHAR(64) NOT NULL,
  severity VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  source_type VARCHAR(32) NOT NULL,
  confidence DECIMAL(6,5) NOT NULL,
  finding_fingerprint VARCHAR(71) NOT NULL,
  title VARCHAR(512) NOT NULL,
  summary VARCHAR(2000) NOT NULL,
  recommendation VARCHAR(2000) NOT NULL,
  confirmed_by_gid BIGINT NULL,
  confirmed_at DATETIME(6) NULL,
  row_version BIGINT NOT NULL DEFAULT 1,
  PRIMARY KEY (finding_gid),
  UNIQUE KEY uq_capability_finding_fingerprint (snapshot_gid, finding_fingerprint),
  KEY ix_capability_finding_status (status),
  KEY ix_capability_finding_snapshot (snapshot_gid),
  KEY ix_capability_finding_fingerprint (finding_fingerprint),
  CONSTRAINT fk_capability_finding_analysis FOREIGN KEY (analysis_run_gid)
    REFERENCES workmanship_base_capability_analysis_runs (analysis_run_gid),
  CONSTRAINT fk_capability_finding_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_finding_subjects (
  finding_subject_gid BIGINT NOT NULL,
  finding_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  subject_role VARCHAR(32) NOT NULL,
  evidence_gid BIGINT NULL,
  PRIMARY KEY (finding_subject_gid),
  UNIQUE KEY uq_capability_finding_subject (finding_gid, capability_version_gid, subject_role),
  KEY ix_capability_finding_subject_version (capability_version_gid),
  CONSTRAINT fk_capability_finding_subject_finding FOREIGN KEY (finding_gid)
    REFERENCES workmanship_base_capability_findings (finding_gid),
  CONSTRAINT fk_capability_finding_subject_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid),
  CONSTRAINT fk_capability_finding_subject_evidence FOREIGN KEY (evidence_gid)
    REFERENCES workmanship_base_capability_evidence (evidence_gid)
);
