CREATE TABLE IF NOT EXISTS workmanship_base_revision_repositories (
  tenant_id VARCHAR(256) NOT NULL,
  repository_id VARCHAR(256) NOT NULL,
  owner_domain VARCHAR(64) NOT NULL,
  resource_id VARCHAR(256) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, repository_id),
  KEY ix_base_revision_repository_resource (tenant_id, owner_domain, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_revision_snapshots (
  tenant_id VARCHAR(256) NOT NULL,
  snapshot_id VARCHAR(64) NOT NULL,
  content_hash VARCHAR(72) NOT NULL,
  byte_size BIGINT UNSIGNED NOT NULL,
  content_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, snapshot_id),
  UNIQUE KEY uq_base_revision_snapshot_hash (tenant_id, content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_revision_commits (
  tenant_id VARCHAR(256) NOT NULL,
  repository_id VARCHAR(256) NOT NULL,
  commit_id VARCHAR(64) NOT NULL,
  snapshot_id VARCHAR(64) NOT NULL,
  content_hash VARCHAR(72) NOT NULL,
  author_id VARCHAR(256) NOT NULL,
  message VARCHAR(2000) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, repository_id, commit_id),
  UNIQUE KEY uq_base_revision_commit_id (commit_id),
  KEY ix_base_revision_commit_history (tenant_id, repository_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_revision_commit_parents (
  tenant_id VARCHAR(256) NOT NULL,
  repository_id VARCHAR(256) NOT NULL,
  commit_id VARCHAR(64) NOT NULL,
  parent_commit_id VARCHAR(64) NOT NULL,
  parent_order TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (tenant_id, repository_id, commit_id, parent_order),
  UNIQUE KEY uq_base_revision_parent (tenant_id, repository_id, commit_id, parent_commit_id),
  KEY ix_base_revision_parent_lookup (tenant_id, repository_id, parent_commit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_revision_branches (
  tenant_id VARCHAR(256) NOT NULL,
  repository_id VARCHAR(256) NOT NULL,
  branch_name VARCHAR(128) NOT NULL,
  head_commit_id VARCHAR(64) NOT NULL,
  is_protected TINYINT(1) NOT NULL DEFAULT 0,
  approval_policy VARCHAR(128) NULL,
  version BIGINT UNSIGNED NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, repository_id, branch_name),
  KEY ix_base_revision_branch_head (tenant_id, repository_id, head_commit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_revision_diffs (
  tenant_id VARCHAR(256) NOT NULL,
  repository_id VARCHAR(256) NOT NULL,
  diff_id VARCHAR(64) NOT NULL,
  from_commit_id VARCHAR(64) NOT NULL,
  to_commit_id VARCHAR(64) NOT NULL,
  changes_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, repository_id, diff_id),
  KEY ix_base_revision_diff_pair (tenant_id, repository_id, from_commit_id, to_commit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_revision_changesets (
  tenant_id VARCHAR(256) NOT NULL,
  repository_id VARCHAR(256) NOT NULL,
  changeset_id VARCHAR(64) NOT NULL,
  base_commit_id VARCHAR(64) NOT NULL,
  changes_json JSON NOT NULL,
  result_content_hash VARCHAR(72) NOT NULL,
  created_by VARCHAR(256) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, repository_id, changeset_id),
  KEY ix_base_revision_changeset_base (tenant_id, repository_id, base_commit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS workmanship_base_revision_lineage_edges (
  tenant_id VARCHAR(256) NOT NULL,
  edge_id VARCHAR(64) NOT NULL,
  upstream_repository_id VARCHAR(256) NOT NULL,
  upstream_commit_id VARCHAR(64) NOT NULL,
  downstream_repository_id VARCHAR(256) NOT NULL,
  downstream_commit_id VARCHAR(64) NOT NULL,
  relation_type VARCHAR(64) NOT NULL,
  created_by VARCHAR(256) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, edge_id),
  KEY ix_base_lineage_upstream (tenant_id, upstream_repository_id, upstream_commit_id),
  KEY ix_base_lineage_downstream (tenant_id, downstream_repository_id, downstream_commit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
