CREATE TABLE IF NOT EXISTS workmanship_base_desktop_transactions (
    transaction_hash CHAR(64) PRIMARY KEY,
    binding_json TEXT NOT NULL,
    expires_at BIGINT NOT NULL,
    code_hash CHAR(64) UNIQUE,
    code_expires_at BIGINT,
    consumed INTEGER NOT NULL DEFAULT 0
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS workmanship_base_desktop_families (
    family_id CHAR(64) PRIMARY KEY,
    binding_json TEXT NOT NULL,
    current_hash CHAR(64) NOT NULL,
    expires_at BIGINT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS workmanship_base_desktop_refresh_tokens (
    token_hash CHAR(64) PRIMARY KEY,
    family_id CHAR(64) NOT NULL
) ENGINE=InnoDB;
