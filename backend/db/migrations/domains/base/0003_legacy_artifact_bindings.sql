CREATE TABLE IF NOT EXISTS workmanship_base_legacy_artifact_bindings (
    binding_hash CHAR(64) PRIMARY KEY,
    owner_domain VARCHAR(32) NOT NULL,
    parent_type VARCHAR(32) NOT NULL,
    parent_gid VARCHAR(128) NOT NULL,
    tenant_gid VARCHAR(128) NOT NULL,
    owner_gid VARCHAR(128) NOT NULL,
    reader_gid VARCHAR(128) NOT NULL,
    reference_hash CHAR(64) NOT NULL,
    object_key VARCHAR(2048) NOT NULL,
    artifact_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY legacy_artifact_parent (owner_domain,parent_type,parent_gid,tenant_gid)
);
