-- Independent upload provenance. Runtime resolvers only SELECT; signed deployment importer only INSERTs.
CREATE TABLE IF NOT EXISTS workmanship_base_historical_uploads (
    object_hash CHAR(64) PRIMARY KEY,
    storage_backend VARCHAR(16) NOT NULL,
    object_key VARCHAR(2048) NOT NULL,
    tenant_gid VARCHAR(128) NOT NULL,
    owner_gid VARCHAR(128) NOT NULL,
    uploader_gid VARCHAR(128) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    byte_size BIGINT UNSIGNED NOT NULL,
    media_type VARCHAR(128) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    uploaded_at VARCHAR(40) NOT NULL,
    parents_json JSON NOT NULL,
    provenance_json JSON NOT NULL,
    registered_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
-- AI00: RESUMABLE CREATE TRIGGER
CREATE TRIGGER base_historical_uploads_no_update BEFORE UPDATE ON workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Historical upload provenance is append-only';
-- AI00: RESUMABLE CREATE TRIGGER
CREATE TRIGGER base_historical_uploads_no_delete BEFORE DELETE ON workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Historical upload provenance is append-only';
