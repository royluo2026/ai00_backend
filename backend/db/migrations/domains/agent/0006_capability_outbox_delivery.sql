ALTER TABLE workmanship_agent_capability_outbox
  ADD COLUMN IF NOT EXISTS outcome_operation_id VARCHAR(128) NULL AFTER operation_id;

ALTER TABLE workmanship_agent_capability_outbox
  ADD COLUMN IF NOT EXISTS async_operation_id VARCHAR(128) NULL AFTER outcome_operation_id;

ALTER TABLE workmanship_agent_capability_outbox
  ADD COLUMN IF NOT EXISTS major_version INT NULL AFTER capability_id;

ALTER TABLE workmanship_agent_capability_outbox
  ADD COLUMN IF NOT EXISTS lease_owner VARCHAR(128) NULL AFTER delivered_at;

ALTER TABLE workmanship_agent_capability_outbox
  ADD COLUMN IF NOT EXISTS lease_token VARCHAR(255) NULL AFTER lease_owner;

ALTER TABLE workmanship_agent_capability_outbox
  ADD COLUMN IF NOT EXISTS lease_expires_at DATETIME(6) NULL AFTER lease_token;

ALTER TABLE workmanship_agent_capability_outbox
  ADD COLUMN IF NOT EXISTS last_error VARCHAR(500) NULL AFTER lease_expires_at;

-- Historical 0005 rows are ambiguous: operation_id may be either the Base
-- reliability outcome id or a business async operation id.  Never guess.
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_agent_capability_outbox
SET state='quarantined',
    last_error='legacy_operation_id_ambiguous',
    outcome_operation_id=NULL,
    async_operation_id=NULL
WHERE outcome_operation_id IS NULL
  AND state IN ('pending','processing');

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_capability_outbox_outcome
  ON workmanship_agent_capability_outbox (outcome_operation_id);
