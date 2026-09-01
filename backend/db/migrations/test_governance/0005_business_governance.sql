CREATE TABLE IF NOT EXISTS workmanship_base_capability_business_purposes (
  purpose_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  business_effect VARCHAR(4000) NOT NULL,
  acceptance_criteria_json LONGTEXT NOT NULL,
  evidence_snapshot_gid BIGINT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (purpose_gid),
  UNIQUE KEY uq_capability_business_purpose (capability_version_gid, definition_hash),
  CONSTRAINT fk_capability_business_purpose_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid),
  CONSTRAINT fk_capability_business_purpose_snapshot FOREIGN KEY (evidence_snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_business_rules (
  business_rule_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  rule_id VARCHAR(128) NOT NULL,
  rule_version BIGINT NOT NULL,
  statement VARCHAR(4000) NOT NULL,
  applies_when VARCHAR(4000) NOT NULL,
  enforcement_ref VARCHAR(1000) NOT NULL,
  error_code VARCHAR(255) NOT NULL,
  test_refs_json LONGTEXT NOT NULL,
  evidence_snapshot_gid BIGINT NOT NULL,
  PRIMARY KEY (business_rule_gid),
  UNIQUE KEY uq_capability_business_rule (capability_version_gid, definition_hash, rule_id, rule_version),
  CONSTRAINT fk_capability_business_rule_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid),
  CONSTRAINT fk_capability_business_rule_snapshot FOREIGN KEY (evidence_snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_relation_candidates (
  relation_candidate_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  candidate_hash VARCHAR(71) NOT NULL,
  relation_type VARCHAR(32) NOT NULL,
  source VARCHAR(32) NOT NULL,
  capability_keys_json LONGTEXT NOT NULL,
  evidence_json LONGTEXT NOT NULL,
  status VARCHAR(32) NOT NULL,
  PRIMARY KEY (relation_candidate_gid),
  UNIQUE KEY uq_capability_relation_candidate (snapshot_gid, candidate_hash),
  CONSTRAINT fk_capability_relation_candidate_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_business_reviews (
  business_review_gid BIGINT NOT NULL,
  proposal_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  decision VARCHAR(32) NOT NULL,
  decision_reason VARCHAR(2000) NOT NULL,
  reviewer_gid BIGINT NOT NULL,
  reviewer_role VARCHAR(64) NOT NULL,
  evidence_snapshot_gid BIGINT NOT NULL,
  decided_at DATETIME(6) NOT NULL,
  PRIMARY KEY (business_review_gid),
  KEY ix_capability_business_review_subject (capability_version_gid, definition_hash, decided_at),
  CONSTRAINT fk_capability_business_review_proposal FOREIGN KEY (proposal_gid)
    REFERENCES workmanship_base_capability_change_proposals (proposal_gid),
  CONSTRAINT fk_capability_business_review_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid),
  CONSTRAINT fk_capability_business_review_snapshot FOREIGN KEY (evidence_snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_rule_effectiveness (
  effectiveness_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  definition_hash VARCHAR(71) NOT NULL,
  metric_name VARCHAR(128) NOT NULL,
  metric_value BIGINT NOT NULL,
  evidence_json LONGTEXT NOT NULL,
  measured_from DATETIME(6) NOT NULL,
  measured_to DATETIME(6) NOT NULL,
  PRIMARY KEY (effectiveness_gid),
  KEY ix_capability_rule_effectiveness_subject (capability_version_gid, definition_hash, measured_to),
  CONSTRAINT fk_capability_rule_effectiveness_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid)
);
