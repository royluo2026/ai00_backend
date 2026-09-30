-- Derived query indexes and immutable completion evidence; original JSON is untouched.
ALTER TABLE workmanship_sim_cloud_cache_nodes
 ADD COLUMN parent_node_key VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
 GENERATED ALWAYS AS (NULLIF(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.parent_occurrence_id')),'null')) STORED;
ALTER TABLE workmanship_sim_cloud_cache_nodes
 ADD COLUMN sibling_order INT
 GENERATED ALWAYS AS (CAST(JSON_UNQUOTE(JSON_EXTRACT(data_json,'$.structure.child_order')) AS UNSIGNED)) STORED;
CREATE INDEX ix_cloud_cache_parent_order
 ON workmanship_sim_cloud_cache_nodes(batch_id,parent_node_key,sibling_order,node_key);
CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_manifests (
 batch_id CHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL PRIMARY KEY,
 manifest_json LONGTEXT NOT NULL,
 FOREIGN KEY(batch_id) REFERENCES workmanship_sim_cloud_cache_batches(batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
