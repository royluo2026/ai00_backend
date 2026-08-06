-- Base owns the shared ontology control plane; legacy workmanship_onto_* remains Craft editor storage.
CREATE TABLE IF NOT EXISTS workmanship_base_ontology_releases (
    gid VARCHAR(128) PRIMARY KEY,
    parent_release_gid VARCHAR(128) NULL,
    source VARCHAR(64) NOT NULL,
    source_gid VARCHAR(128) NULL,
    content_sha256 CHAR(64) NOT NULL,
    object_count BIGINT NOT NULL,
    ois_object_key VARCHAR(1024) NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_ontology_release_hash (content_sha256),
    UNIQUE KEY uq_base_ontology_release_source (source, source_gid),
    INDEX idx_base_ontology_release_parent (parent_release_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_ontology_release_objects (
    release_gid VARCHAR(128) NOT NULL,
    object_kind VARCHAR(32) NOT NULL,
    stable_object_gid VARCHAR(128) NOT NULL,
    object_sha256 CHAR(64) NOT NULL,
    object_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (release_gid, object_kind, stable_object_gid),
    INDEX idx_base_ontology_object_identity (object_kind, stable_object_gid, release_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_ontology_change_proposals (
    gid VARCHAR(128) PRIMARY KEY,
    base_release_gid VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    author_gid VARCHAR(128) NOT NULL,
    channel VARCHAR(32) NOT NULL DEFAULT 'web',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_base_ontology_proposal_base (base_release_gid, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_ontology_proposal_revisions (
    gid VARCHAR(128) PRIMARY KEY,
    proposal_gid VARCHAR(128) NOT NULL,
    revision_no BIGINT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    changes_json JSON NOT NULL,
    evidence_json JSON NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_ontology_proposal_revision (proposal_gid, revision_no),
    UNIQUE KEY uq_base_ontology_proposal_revision_hash (proposal_gid, content_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_ontology_proposal_reviews (
    gid VARCHAR(128) PRIMARY KEY,
    proposal_gid VARCHAR(128) NOT NULL,
    proposal_revision_gid VARCHAR(128) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    reviewer_gid VARCHAR(128) NOT NULL,
    comment TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_base_ontology_review (proposal_revision_gid, reviewer_gid),
    INDEX idx_base_ontology_review_proposal (proposal_gid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workmanship_base_ontology_active_refs (
    ref_name VARCHAR(128) PRIMARY KEY,
    release_gid VARCHAR(128) NOT NULL,
    release_sha256 CHAR(64) NOT NULL,
    updated_by VARCHAR(128) NOT NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_base_ontology_active_release (release_gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
