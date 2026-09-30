-- Bound each metadata packet and avoid OceanBase CONCAT result-size limits.
CREATE TABLE IF NOT EXISTS workmanship_sim_cache_assembly_preparation_chunks (
 batch_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 chunk_index INT NOT NULL,
 chunk_text MEDIUMTEXT NOT NULL,
 PRIMARY KEY(batch_id,chunk_index),
 FOREIGN KEY(batch_id) REFERENCES workmanship_sim_cloud_cache_batches(batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
