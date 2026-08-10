CREATE TABLE IF NOT EXISTS workmanship_base_capability_catalog_releases (
  release_id VARCHAR(36) NOT NULL,
  catalog_hash CHAR(71) NOT NULL,
  descriptors_json JSON NOT NULL,
  provider_artifacts_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (release_id),
  UNIQUE KEY uq_base_capability_catalog_hash (catalog_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
