from datetime import datetime, timezone

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.simulation.simulation_backend.capabilities.provider import descriptor_for
from plugins.simulation.simulation_backend.capabilities.workspaces import WorkspaceProvider, candidate_specs
from plugins.simulation.simulation_backend.domain.cache_lease import (
    CacheLeaseError,
    permission_version,
    verify_cache_lease,
)


NOW = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
REVISION = "sha256:" + "a" * 64


class Repository:
    def __init__(self, row=None):
        self.row = row or {
            "workspace_gid": "456",
            "row_version": 12,
            "cache_revision_hash": REVISION,
        }
        self.calls = []

    def get(self, workspace_gid, **scope):
        self.calls.append((workspace_gid, scope))
        return self.row


def context(**updates):
    values = {
        "user_gid": "123",
        "team_gid": "20",
        "request_id": "request-1",
        "permissions": ("simulation.use",),
        "active_roles": ("member",),
        "resource_refs": ("simulation-workspace:456",),
    }
    values.update(updates)
    return CapabilityContext(**values)


def test_cache_lease_is_bound_to_actor_workspace_and_revision(monkeypatch):
    monkeypatch.setenv("AI00_SIMULATION_EXPORT_SIGNING_KEY", "test-signing-key")
    repository = Repository()
    provider = WorkspaceProvider(repository, clock=lambda: NOW)

    result = provider.cache_lease_get(
        {"workspace_gid": "456", "expires_in_seconds": 120}, context()
    ).data
    claims = verify_cache_lease(result["read_lease"], now_epoch=int(NOW.timestamp()))

    assert result["auth_subject_gid"] == claims["auth_subject_gid"] == "123"
    assert result["workspace_gid"] == claims["workspace_gid"] == "456"
    assert result["cache_revision_hash"] == claims["cache_revision_hash"] == REVISION
    assert result["row_version"] == claims["row_version"] == 12
    assert result["expires_in_seconds"] == 120
    assert repository.calls == [("456", {"tenant_gid": "20", "owner_gid": "123"})]


def test_cache_lease_ttl_is_bounded_and_tamper_is_rejected(monkeypatch):
    monkeypatch.setenv("AI00_SIMULATION_EXPORT_SIGNING_KEY", "test-signing-key")
    provider = WorkspaceProvider(Repository(), clock=lambda: NOW)

    with pytest.raises(CapabilityBusinessError, match="cache_lease_ttl_invalid"):
        provider.cache_lease_get({"workspace_gid": "456", "expires_in_seconds": 301}, context())
    lease = provider.cache_lease_get({"workspace_gid": "456"}, context()).data["read_lease"]
    with pytest.raises(CacheLeaseError, match="cache_lease_invalid"):
        verify_cache_lease(lease + "tampered", now_epoch=int(NOW.timestamp()))


def test_permission_version_changes_with_effective_permission_scope():
    original = permission_version(context())
    changed = permission_version(context(active_roles=("project_admin",)))
    assert isinstance(original, int) and original >= 1
    assert original != changed


def test_cache_lease_refuses_removed_or_unreadable_workspace(monkeypatch):
    monkeypatch.setenv("AI00_SIMULATION_EXPORT_SIGNING_KEY", "test-signing-key")
    provider = WorkspaceProvider(Repository(row=None), clock=lambda: NOW)
    provider.repository.row = None
    with pytest.raises(CapabilityBusinessError, match="workspace_not_found"):
        provider.cache_lease_get({"workspace_gid": "456"}, context())


def test_cache_lease_reports_missing_signing_configuration_as_domain_error(monkeypatch):
    monkeypatch.delenv("AI00_SIMULATION_EXPORT_SIGNING_KEY", raising=False)
    provider = WorkspaceProvider(Repository(), clock=lambda: NOW)
    with pytest.raises(CapabilityBusinessError, match="cache_lease_signing_key_unavailable"):
        provider.cache_lease_get({"workspace_gid": "456"}, context())


def test_cache_lease_capability_is_read_scoped_to_one_workspace():
    spec = next(
        spec for spec, _handler in candidate_specs(WorkspaceProvider(Repository()))
        if spec.id == "simulation.environment.workspace.cache_lease.get"
    )
    descriptor = descriptor_for(spec)
    assert spec.risk == "read"
    assert [(item.resource_type, item.payload_path) for item in descriptor.resource_selectors] == [
        ("simulation-workspace", "workspace_gid")
    ]
    assert {item.code for item in descriptor.domain_errors} >= {
        "workspace_not_found",
        "cache_lease_ttl_invalid",
        "cache_lease_signing_key_unavailable",
    }
