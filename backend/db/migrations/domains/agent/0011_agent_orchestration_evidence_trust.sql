-- Evidence used by KPI calculations is immutable, hash-bound and time-bound.
ALTER TABLE workmanship_agent_orch_workload_baselines
  ADD COLUMN IF NOT EXISTS authorization_artifact_hash VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS authorization_valid_from DATETIME(6) NULL,
  ADD COLUMN IF NOT EXISTS authorization_valid_until DATETIME(6) NULL,
  ADD COLUMN IF NOT EXISTS authorization_revoked TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE workmanship_agent_orch_acceptance_facts
  ADD COLUMN IF NOT EXISTS acceptance_artifact_hash VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS acceptance_valid_from DATETIME(6) NULL,
  ADD COLUMN IF NOT EXISTS acceptance_valid_until DATETIME(6) NULL,
  ADD COLUMN IF NOT EXISTS acceptance_revoked TINYINT(1) NOT NULL DEFAULT 0;
