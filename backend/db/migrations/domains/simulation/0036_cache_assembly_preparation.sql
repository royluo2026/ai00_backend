-- Shared assembly metadata only: never JT bytes, local paths or FMS tickets.
ALTER TABLE workmanship_sim_cloud_cache_batches ADD COLUMN IF NOT EXISTS preparation_status VARCHAR(32) NOT NULL DEFAULT 'not_prepared';
ALTER TABLE workmanship_sim_cloud_cache_batches ADD COLUMN IF NOT EXISTS preparation_error VARCHAR(255) NULL;
CREATE TABLE IF NOT EXISTS workmanship_sim_cache_assembly_preparations (
 batch_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
 preparation_hash CHAR(71) NOT NULL,
 preparation_json LONGTEXT NOT NULL,
 FOREIGN KEY(batch_id) REFERENCES workmanship_sim_cloud_cache_batches(batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
