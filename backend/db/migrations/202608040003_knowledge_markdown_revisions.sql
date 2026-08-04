-- Knowledge-owned Markdown/OIS metadata. Markdown bodies never live in these tables.
CREATE TABLE IF NOT EXISTS workmanship_know_spaces (
    gid VARCHAR(128) PRIMARY KEY,
    tenant_gid VARCHAR(128) NOT NULL,
    name VARCHAR(512) NOT NULL,
    visibility VARCHAR(32) NOT NULL DEFAULT 'team',
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_know_space_tenant_name (tenant_gid, name),
    INDEX idx_know_spaces_tenant (tenant_gid, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_know_documents (
    gid VARCHAR(128) PRIMARY KEY,
    tenant_gid VARCHAR(128) NOT NULL,
    space_gid VARCHAR(128) NOT NULL,
    title VARCHAR(512) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    current_revision_gid VARCHAR(128) NULL,
    published_revision_gid VARCHAR(128) NULL,
    source_entry_gid VARCHAR(128) NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_know_document_space_slug (space_gid, slug),
    UNIQUE KEY uq_know_document_source (source_entry_gid),
    INDEX idx_know_documents_tenant_space (tenant_gid, space_gid, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_know_revisions (
    gid VARCHAR(128) PRIMARY KEY,
    tenant_gid VARCHAR(128) NOT NULL,
    space_gid VARCHAR(128) NOT NULL,
    document_gid VARCHAR(128) NOT NULL,
    revision_no BIGINT NOT NULL,
    base_revision_gid VARCHAR(128) NULL,
    restored_from_revision_gid VARCHAR(128) NULL,
    proposal_gid VARCHAR(128) NULL,
    object_key VARCHAR(1024) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    byte_size BIGINT NOT NULL,
    media_type VARCHAR(128) NOT NULL DEFAULT 'text/markdown; charset=utf-8',
    state VARCHAR(32) NOT NULL DEFAULT 'draft',
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_know_revision_number (document_gid, revision_no),
    UNIQUE KEY uq_know_revision_object (object_key),
    INDEX idx_know_revisions_document (document_gid, created_at),
    INDEX idx_know_revisions_proposal (proposal_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_know_document_acl (
    document_gid VARCHAR(128) NOT NULL,
    subject_type VARCHAR(32) NOT NULL,
    subject_gid VARCHAR(128) NOT NULL,
    permission VARCHAR(32) NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (document_gid, subject_type, subject_gid),
    INDEX idx_know_document_acl_subject (subject_type, subject_gid, permission)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;