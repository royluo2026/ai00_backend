CREATE TABLE IF NOT EXISTS workmanship_base_capability_change_proposals (
  proposal_gid BIGINT NOT NULL,
  proposal_batch_gid BIGINT NULL,
  capability_version_gid BIGINT NOT NULL,
  base_snapshot_gid BIGINT NOT NULL,
  proposed_descriptor_hash VARCHAR(71) NOT NULL,
  change_type VARCHAR(64) NOT NULL,
  risk_level VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  submitted_by_gid BIGINT NOT NULL,
  submitted_at DATETIME(6) NOT NULL,
  stale_at DATETIME(6) NULL,
  summary VARCHAR(2000) NOT NULL,
  change_json LONGTEXT NOT NULL,
  row_version BIGINT NOT NULL DEFAULT 1,
  PRIMARY KEY (proposal_gid),
  KEY ix_capability_proposal_version (capability_version_gid),
  KEY ix_capability_proposal_status (status),
  KEY ix_capability_proposal_stale (stale_at),
  CONSTRAINT fk_capability_proposal_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid),
  CONSTRAINT fk_capability_proposal_snapshot FOREIGN KEY (base_snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_reviews (
  review_gid BIGINT NOT NULL,
  proposal_gid BIGINT NOT NULL,
  review_stage VARCHAR(64) NOT NULL,
  decision VARCHAR(32) NOT NULL,
  reviewer_gid BIGINT NOT NULL,
  decision_reason VARCHAR(2000) NOT NULL,
  evidence_snapshot_gid BIGINT NOT NULL,
  decided_at DATETIME(6) NOT NULL,
  PRIMARY KEY (review_gid),
  UNIQUE KEY uq_capability_review_stage (proposal_gid, review_stage),
  KEY ix_capability_review_decision (decision),
  CONSTRAINT fk_capability_review_proposal FOREIGN KEY (proposal_gid)
    REFERENCES workmanship_base_capability_change_proposals (proposal_gid),
  CONSTRAINT fk_capability_review_snapshot FOREIGN KEY (evidence_snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_waivers (
  waiver_gid BIGINT NOT NULL,
  finding_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  scope VARCHAR(256) NOT NULL,
  reason VARCHAR(2000) NOT NULL,
  granted_by_gid BIGINT NOT NULL,
  starts_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  revoked_at DATETIME(6) NULL,
  status VARCHAR(32) NOT NULL,
  row_version BIGINT NOT NULL DEFAULT 1,
  PRIMARY KEY (waiver_gid),
  KEY ix_capability_waiver_version (capability_version_gid),
  KEY ix_capability_waiver_expiry (expires_at),
  KEY ix_capability_waiver_status (status),
  CONSTRAINT fk_capability_waiver_finding FOREIGN KEY (finding_gid)
    REFERENCES workmanship_base_capability_findings (finding_gid),
  CONSTRAINT fk_capability_waiver_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_release_reports (
  release_report_gid BIGINT NOT NULL,
  code_revision VARCHAR(128) NOT NULL,
  product_catalog_release_id VARCHAR(128) NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  test_run_gid BIGINT NOT NULL,
  conclusion VARCHAR(32) NOT NULL,
  blockers_json LONGTEXT NOT NULL,
  report_hash VARCHAR(71) NOT NULL,
  signing_key_id VARCHAR(128) NOT NULL,
  signature VARCHAR(1024) NOT NULL,
  evaluated_by_gid BIGINT NOT NULL,
  evaluated_at DATETIME(6) NOT NULL,
  expired_at DATETIME(6) NULL,
  PRIMARY KEY (release_report_gid),
  UNIQUE KEY uq_capability_release_report_hash (report_hash),
  KEY ix_capability_release_snapshot (snapshot_gid),
  KEY ix_capability_release_test_run (test_run_gid),
  KEY ix_capability_release_conclusion (conclusion),
  CONSTRAINT fk_capability_release_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid),
  CONSTRAINT fk_capability_release_test_run FOREIGN KEY (test_run_gid)
    REFERENCES workmanship_base_capability_test_runs (test_run_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_audit_events (
  audit_event_gid BIGINT NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  entity_type VARCHAR(64) NOT NULL,
  entity_gid BIGINT NOT NULL,
  actor_type VARCHAR(32) NOT NULL,
  actor_gid BIGINT NULL,
  request_gid BIGINT NULL,
  before_hash VARCHAR(71) NULL,
  after_hash VARCHAR(71) NULL,
  redacted_detail_json LONGTEXT NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  PRIMARY KEY (audit_event_gid),
  KEY ix_capability_audit_entity (entity_type, entity_gid),
  KEY ix_capability_audit_event_time (occurred_at),
  KEY ix_capability_audit_event_type (event_type)
);
