ALTER TABLE workmanship_base_capability_snapshots
  ADD COLUMN IF NOT EXISTS catalog_hash VARCHAR(71) NULL AFTER catalog_release_id;

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_capability_snapshots AS snapshot
JOIN workmanship_base_capability_catalog_releases AS catalog
  ON BINARY catalog.release_id = BINARY snapshot.catalog_release_id
SET snapshot.catalog_hash = catalog.catalog_hash
WHERE snapshot.catalog_hash IS NULL;

-- A snapshot whose Catalog release is absent from the immutable release store
-- makes this migration fail closed instead of inventing a hash.
ALTER TABLE workmanship_base_capability_snapshots
  MODIFY COLUMN catalog_hash VARCHAR(71) NOT NULL;
