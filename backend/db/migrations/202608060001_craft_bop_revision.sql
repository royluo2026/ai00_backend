-- Authoritative optimistic-lock revision for governed BOP Capability writes.
ALTER TABLE workmanship_bop_bop_versions
    ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;
