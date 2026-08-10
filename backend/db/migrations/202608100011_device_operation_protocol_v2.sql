-- Local Integration protocol V2 status normalization.
-- The existing columns remain transport-neutral; command gid is now the Base Operation ID.
--
-- This migration is intentionally metadata-only. OceanBase DDL implicitly commits,
-- so versioned migrations must not mix resumability tracking with data backfills.
-- Legacy status `succeeded` is projected as `completed`, and the legacy error text
-- `lease retry limit reached` as `lease_retry_limit_reached`, at the read boundary.

ALTER TABLE workmanship_runtime_commands
    ADD COLUMN IF NOT EXISTS protocol_version VARCHAR(64) NULL;
