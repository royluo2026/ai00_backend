-- Complete snapshot membership is separate from displayed TC business data.
-- Existing rows remain untouched and receive membership when accepted by @2.
ALTER TABLE workmanship_sim_cloud_cache_nodes
 ADD COLUMN IF NOT EXISTS snapshot_generation CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL;
ALTER TABLE workmanship_sim_cloud_cache_nodes
 ADD COLUMN IF NOT EXISTS snapshot_position INT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cloud_cache_snapshot_position
 ON workmanship_sim_cloud_cache_nodes(batch_id,snapshot_generation,snapshot_position);
