"""Version-bound reference datasets for deterministic cross-domain algorithms."""
from __future__ import annotations


class ReferenceDataService:
    def __init__(self, repository): self.repository = repository

    def publish(self, *, dataset_gid, expected_version, schema, rows, actor_gid, tenant_gid):
        keys = [str(row.get("key") or "") for row in rows]
        if not keys or any(not key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("Reference data rows require unique non-empty keys")
        return self.repository.publish(dataset_gid, expected_version, schema, rows, actor_gid, tenant_gid)

    def lookup(self, *, dataset_gid, version_gid, keys, tenant_gid):
        if not version_gid:
            raise ValueError("dataset_version_ref is required for reproducible lookup")
        return self.repository.lookup(dataset_gid, version_gid, tuple(dict.fromkeys(keys)), tenant_gid)

