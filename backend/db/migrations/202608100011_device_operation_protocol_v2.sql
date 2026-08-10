-- Local Integration protocol V2 status normalization.
-- The existing columns remain transport-neutral; command gid is now the Base Operation ID.
UPDATE workmanship_runtime_commands
SET status = 'completed'
WHERE status = 'succeeded';

UPDATE workmanship_runtime_commands
SET error = 'lease_retry_limit_reached'
WHERE error = 'lease retry limit reached';
