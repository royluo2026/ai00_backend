CREATE TABLE IF NOT EXISTS workmanship_base_capability_worker_leases (
  worker_lease_gid BIGINT NOT NULL,
  run_kind VARCHAR(32) NOT NULL,
  run_gid BIGINT NOT NULL,
  status VARCHAR(32) NOT NULL,
  worker_id VARCHAR(128) NULL,
  lease_expires_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  PRIMARY KEY (worker_lease_gid),
  UNIQUE KEY uq_capability_worker_lease_run (run_kind, run_gid),
  KEY ix_capability_worker_lease_status_expiry (status, lease_expires_at)
);
