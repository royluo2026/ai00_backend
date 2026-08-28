from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest


INSTALL = {
    "plugin_id": "plugin.example",
    "release_version": "1.2.3",
    "release_sha256": "sha256:" + "b" * 64,
    "requested_grants": ["project.read"],
    "idempotency_key": "idem-plugin-1",
}
UNINSTALL = {
    "plugin_id": "plugin.example",
    "expected_revision": 3,
    "retain_tenant_data": True,
    "idempotency_key": "idem-plugin-2",
}
ACTOR = {"gid": "user_1", "tenant_gid": "tenant_1"}


class MemoryPluginLifecycleRepository:
    def __init__(self) -> None:
        self.releases = {
            ("plugin.example", "1.2.3"): {
                "plugin_id": "plugin.example", "version": "1.2.3",
                "artifact_sha256": "b" * 64, "status": "published",
                "platform_signature": "platform-signed", "dependencies_ready": True,
                "permissions": ["project.read"],
            }
        }
        self.installations: dict[tuple[str, str], dict] = {}
        self.idempotency: dict[tuple[str, str, str], dict] = {}
        self.events: list[dict] = []
        self.mounts_revoked: list[tuple[str, str]] = []
        self.data_policy: list[tuple[str, str, bool]] = []

    @contextmanager
    def transaction(self):
        yield self

    def release(self, plugin_id: str, version: str, *, lock: bool = False):
        return deepcopy(self.releases.get((plugin_id, version)))

    def installation(self, tenant_gid: str, plugin_id: str, *, lock: bool = False):
        row = self.installations.get((tenant_gid, plugin_id))
        return deepcopy(row) if row else None

    def save_installation(self, row: dict) -> None:
        self.installations[(row["tenant_gid"], row["plugin_id"])] = deepcopy(row)

    def claim(self, *, actor_gid: str, operation: str, idempotency_key: str):
        return deepcopy(self.idempotency.get((actor_gid, operation, idempotency_key)))

    def complete(self, *, actor_gid: str, operation: str, idempotency_key: str, result: dict) -> None:
        self.idempotency[(actor_gid, operation, idempotency_key)] = deepcopy(result)

    def revoke_mounts(self, *, tenant_gid: str, plugin_id: str, installation_id: str, new_revision: int) -> None:
        self.mounts_revoked.append((tenant_gid, plugin_id))

    def preserve_tenant_data(self, *, tenant_gid: str, plugin_id: str, retain: bool) -> None:
        self.data_policy.append((tenant_gid, plugin_id, retain))

    def audit(self, event: dict) -> None:
        self.events.append(deepcopy(event))


def service():
    from backend.plugin_platform.service import PluginPlatformService

    repository = MemoryPluginLifecycleRepository()
    return PluginPlatformService(repository=repository), repository


def test_install_accepts_only_closed_signed_release_identity_and_known_grants():
    """Removing command validation or release/grant verification must fail this test."""
    from backend.plugin_platform.service import PluginLifecycleError

    lifecycle, repository = service()
    with pytest.raises(PluginLifecycleError, match="invalid_input"):
        lifecycle.request_install(actor=ACTOR, command={**INSTALL, "url": "https://evil.example/plugin.zip"})
    with pytest.raises(PluginLifecycleError, match="invalid_input"):
        lifecycle.request_install(actor=ACTOR, command={**INSTALL, "requested_grants": ["unknown.grant"]})
    repository.releases[("plugin.example", "1.2.3")]["platform_signature"] = ""
    with pytest.raises(PluginLifecycleError, match="release_not_verified"):
        lifecycle.request_install(actor=ACTOR, command=INSTALL)
    assert repository.installations == {}


def test_install_is_tenant_bound_and_replays_the_original_outcome():
    """Removing actor tenant binding or idempotency replay must fail this test."""
    lifecycle, repository = service()
    result = lifecycle.request_install(actor=ACTOR, command=INSTALL)
    replay = lifecycle.request_install(actor=ACTOR, command=INSTALL)

    assert result == replay
    assert result == {
        "plugin_id": "plugin.example", "release_version": "1.2.3", "state": "disabled",
        "revision": 1, "granted_capabilities": ["project.read"], "tenant_gid": "tenant_1",
    }
    assert ("tenant_1", "plugin.example") in repository.installations
    assert ("tenant_2", "plugin.example") not in repository.installations
    assert len(repository.events) == 1


def test_uninstall_revokes_mounts_and_grants_but_retains_tenant_data_atomically():
    """Removing any uninstall transition side effect must fail this test."""
    lifecycle, repository = service()
    installed = lifecycle.request_install(actor=ACTOR, command=INSTALL)
    result = lifecycle.transition_uninstall(actor=ACTOR, command={**UNINSTALL, "expected_revision": installed["revision"]})
    replay = lifecycle.transition_uninstall(actor=ACTOR, command={**UNINSTALL, "expected_revision": installed["revision"]})

    assert result == replay
    assert result["state"] == "uninstalled"
    assert result["revision"] == 2
    row = repository.installations[("tenant_1", "plugin.example")]
    assert row["state"] == "uninstalled"
    assert row["granted_capabilities"] == []
    assert repository.mounts_revoked == [("tenant_1", "plugin.example")]
    assert repository.data_policy == [("tenant_1", "plugin.example", True)]
    assert repository.events[-1]["operation"] == "transition.uninstall"


def test_uninstall_rejects_stale_revision_and_cross_tenant_access():
    """Removing revision or tenant ownership checks must fail this test."""
    from backend.plugin_platform.service import PluginLifecycleError

    lifecycle, _repository = service()
    lifecycle.request_install(actor=ACTOR, command=INSTALL)
    with pytest.raises(PluginLifecycleError, match="revision_conflict"):
        lifecycle.transition_uninstall(actor=ACTOR, command={**UNINSTALL, "expected_revision": 3})
    with pytest.raises(PluginLifecycleError, match="resource_not_found"):
        lifecycle.transition_uninstall(actor={"gid": "user_2", "tenant_gid": "tenant_2"}, command={**UNINSTALL, "expected_revision": 1})
