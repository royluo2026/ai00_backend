-- Allocate visible v1/v2/... atomically within each tenant/project/data stage.
CREATE TABLE IF NOT EXISTS workmanship_sim_cloud_cache_versions (
 tenant_gid VARCHAR(64) NOT NULL,
 project_gid VARCHAR(64) NOT NULL,
 phase VARCHAR(256) NOT NULL,
 next_version BIGINT NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant_gid,project_gid,phase)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
