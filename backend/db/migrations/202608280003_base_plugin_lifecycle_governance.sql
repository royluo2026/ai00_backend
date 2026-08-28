-- Install/uninstall needs durable optimistic concurrency and replay evidence;
-- existing marketplace rows intentionally remain the source of tenant data.
ALTER TABLE workmanship_plugin_installations
  ADD COLUMN IF NOT EXISTS revision BIGINT UNSIGNED NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS workmanship_base_plugin_lifecycle_idempotency (
    actor_gid VARCHAR(128) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result_json JSON NULL,
    completed_at DATETIME(6) NULL,
    PRIMARY KEY (actor_gid, operation, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
