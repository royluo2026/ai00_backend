-- Project-shared metadata only. No credentials, FMS tickets or JT bytes.
CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_batches (
 batch_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 tenant_gid VARCHAR(64) NOT NULL, actor_gid VARCHAR(64) NOT NULL,
 project_gid VARCHAR(64) NOT NULL, project_name VARCHAR(512) NOT NULL,
 phase VARCHAR(256) NOT NULL, display_name VARCHAR(512) NOT NULL,
 selector_json LONGTEXT NOT NULL, source_hash CHAR(71) NOT NULL,
 status VARCHAR(32) NOT NULL, created_at VARCHAR(40) NOT NULL, updated_at VARCHAR(40) NOT NULL,
 completed_at VARCHAR(40) NULL, row_version BIGINT NOT NULL DEFAULT 1,
 node_count INT NOT NULL DEFAULT 0, fields_json LONGTEXT NOT NULL,
 error_code VARCHAR(255) NULL, trigger_kind VARCHAR(32) NOT NULL,
 request_key VARCHAR(255) NOT NULL, request_hash CHAR(64) NOT NULL,
 connector_device_id VARCHAR(128) NULL, principal_hash CHAR(71) NULL,
 UNIQUE KEY uq_cloud_cache_request(tenant_gid,actor_gid,request_key),
 KEY ix_cloud_cache_project(tenant_gid,project_gid,created_at),
 KEY ix_cloud_cache_worker(status,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_tasks (
 batch_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 task_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 kind VARCHAR(32) NOT NULL, payload_json LONGTEXT NOT NULL,
 status VARCHAR(32) NOT NULL, operation_id VARCHAR(256) NULL, attempt INT NOT NULL DEFAULT 0,
 PRIMARY KEY(batch_id,task_key), KEY ix_cloud_cache_task(batch_id,status),
 FOREIGN KEY(batch_id) REFERENCES workmanship_sim_cloud_cache_batches(batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_nodes (
 batch_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 node_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 data_json LONGTEXT NOT NULL, PRIMARY KEY(batch_id,node_key),
 FOREIGN KEY(batch_id) REFERENCES workmanship_sim_cloud_cache_batches(batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_receipts (
 batch_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 receipt_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 body_hash CHAR(64) NOT NULL, PRIMARY KEY(batch_id,receipt_key),
 FOREIGN KEY(batch_id) REFERENCES workmanship_sim_cloud_cache_batches(batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
