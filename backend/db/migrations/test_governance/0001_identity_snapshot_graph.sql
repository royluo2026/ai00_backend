CREATE TABLE IF NOT EXISTS workmanship_base_capability_entries (
  capability_gid BIGINT NOT NULL,
  capability_id VARCHAR(128) NOT NULL,
  owner_domain VARCHAR(64) NOT NULL,
  current_major_version INT NOT NULL,
  current_lifecycle_status VARCHAR(32) NOT NULL,
  first_seen_at DATETIME(6) NOT NULL,
  last_seen_at DATETIME(6) NOT NULL,
  row_version BIGINT NOT NULL DEFAULT 1,
  PRIMARY KEY (capability_gid),
  UNIQUE KEY uq_capability_entry_id (capability_id),
  KEY ix_capability_entry_owner_status (owner_domain, current_lifecycle_status)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_versions (
  capability_version_gid BIGINT NOT NULL,
  capability_gid BIGINT NOT NULL,
  major_version INT NOT NULL,
  semantic_class VARCHAR(32) NOT NULL,
  business_effect VARCHAR(1000) NOT NULL,
  lifecycle_status VARCHAR(32) NOT NULL,
  first_seen_snapshot_gid BIGINT NULL,
  latest_snapshot_gid BIGINT NULL,
  retired_at DATETIME(6) NULL,
  row_version BIGINT NOT NULL DEFAULT 1,
  PRIMARY KEY (capability_version_gid),
  UNIQUE KEY uq_capability_version (capability_gid, major_version),
  KEY ix_capability_version_status (lifecycle_status),
  KEY ix_capability_version_latest_snapshot (latest_snapshot_gid),
  CONSTRAINT fk_capability_version_entry FOREIGN KEY (capability_gid)
    REFERENCES workmanship_base_capability_entries (capability_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_scan_runs (
  scan_run_gid BIGINT NOT NULL,
  environment_key VARCHAR(128) NOT NULL,
  trigger_type VARCHAR(32) NOT NULL,
  code_revision VARCHAR(128) NOT NULL,
  catalog_release_id VARCHAR(128) NOT NULL,
  requested_by_gid BIGINT NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  error_summary VARCHAR(1000) NULL,
  PRIMARY KEY (scan_run_gid),
  UNIQUE KEY uq_capability_scan_idempotency (environment_key, idempotency_key),
  KEY ix_capability_scan_status (status)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_snapshots (
  snapshot_gid BIGINT NOT NULL,
  scan_run_gid BIGINT NOT NULL,
  snapshot_hash VARCHAR(71) NOT NULL,
  code_revision VARCHAR(128) NOT NULL,
  catalog_release_id VARCHAR(128) NOT NULL,
  descriptor_count INT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (snapshot_gid),
  UNIQUE KEY uq_capability_snapshot_hash (snapshot_hash),
  KEY ix_capability_snapshot_scan (scan_run_gid),
  CONSTRAINT fk_capability_snapshot_scan FOREIGN KEY (scan_run_gid)
    REFERENCES workmanship_base_capability_scan_runs (scan_run_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_snapshot_entries (
  snapshot_entry_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  descriptor_hash VARCHAR(71) NOT NULL,
  input_schema_hash VARCHAR(71) NOT NULL,
  output_schema_hash VARCHAR(71) NOT NULL,
  error_schema_hash VARCHAR(71) NOT NULL,
  policy_hash VARCHAR(71) NOT NULL,
  provider_hash VARCHAR(71) NOT NULL,
  descriptor_json LONGTEXT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (snapshot_entry_gid),
  UNIQUE KEY uq_capability_snapshot_entry (snapshot_gid, capability_version_gid),
  KEY ix_capability_snapshot_entry_version (capability_version_gid),
  CONSTRAINT fk_capability_snapshot_entry_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid),
  CONSTRAINT fk_capability_snapshot_entry_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_implementation_nodes (
  implementation_node_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  owner_domain VARCHAR(64) NOT NULL,
  node_type VARCHAR(32) NOT NULL,
  canonical_key VARCHAR(512) NOT NULL,
  source_path VARCHAR(1024) NOT NULL,
  source_symbol VARCHAR(512) NULL,
  http_method VARCHAR(16) NULL,
  route_path VARCHAR(512) NULL,
  artifact_hash VARCHAR(71) NOT NULL,
  metadata_json LONGTEXT NOT NULL,
  PRIMARY KEY (implementation_node_gid),
  UNIQUE KEY uq_capability_implementation_node (snapshot_gid, canonical_key),
  KEY ix_capability_implementation_owner (owner_domain),
  KEY ix_capability_implementation_snapshot (snapshot_gid),
  CONSTRAINT fk_capability_implementation_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_bindings (
  binding_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  capability_version_gid BIGINT NOT NULL,
  implementation_node_gid BIGINT NOT NULL,
  binding_type VARCHAR(32) NOT NULL,
  binding_hash VARCHAR(71) NOT NULL,
  PRIMARY KEY (binding_gid),
  UNIQUE KEY uq_capability_binding (snapshot_gid, capability_version_gid, implementation_node_gid, binding_type),
  KEY ix_capability_binding_version (capability_version_gid),
  CONSTRAINT fk_capability_binding_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid),
  CONSTRAINT fk_capability_binding_version FOREIGN KEY (capability_version_gid)
    REFERENCES workmanship_base_capability_versions (capability_version_gid),
  CONSTRAINT fk_capability_binding_node FOREIGN KEY (implementation_node_gid)
    REFERENCES workmanship_base_capability_implementation_nodes (implementation_node_gid)
);

CREATE TABLE IF NOT EXISTS workmanship_base_capability_implementation_relations (
  relation_gid BIGINT NOT NULL,
  snapshot_gid BIGINT NOT NULL,
  from_node_gid BIGINT NOT NULL,
  to_node_gid BIGINT NOT NULL,
  relation_type VARCHAR(32) NOT NULL,
  relation_hash VARCHAR(71) NOT NULL,
  PRIMARY KEY (relation_gid),
  UNIQUE KEY uq_capability_implementation_relation (snapshot_gid, from_node_gid, to_node_gid, relation_type),
  KEY ix_capability_relation_snapshot (snapshot_gid),
  CONSTRAINT fk_capability_relation_snapshot FOREIGN KEY (snapshot_gid)
    REFERENCES workmanship_base_capability_snapshots (snapshot_gid),
  CONSTRAINT fk_capability_relation_from_node FOREIGN KEY (from_node_gid)
    REFERENCES workmanship_base_capability_implementation_nodes (implementation_node_gid),
  CONSTRAINT fk_capability_relation_to_node FOREIGN KEY (to_node_gid)
    REFERENCES workmanship_base_capability_implementation_nodes (implementation_node_gid)
);
