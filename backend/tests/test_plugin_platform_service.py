from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


INSTALL = {
    "plugin_id": "devteam.example.plugin",
    "release_version": "1.2.3",
    "release_sha256": "sha256:" + "b" * 64,
    "requested_grants": ["project.read"],
    "idempotency_key": "idem-plugin-1",
}
UNINSTALL = {
    "plugin_id": "devteam.example.plugin",
    "expected_revision": 3,
    "retain_tenant_data": True,
    "idempotency_key": "idem-plugin-2",
}
ACTOR = {"gid": "user_1", "tenant_gid": "tenant_1"}


class MemoryPluginLifecycleRepository:
    def __init__(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        self.platform_public_key = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        manifest = {
            "schema_version": "2.0", "plugin_id": "devteam.example.plugin", "publisher_id": "devteam",
            "name": "Example", "version": "1.2.3", "compatibility": {"platform_api": "1", "web_sdk": "1"},
            "runtimes": {"web": {"entry": "index.html"}}, "permissions": ["project.read"],
            "capabilities": {"required": [], "optional": []},
            "artifact": {"object_key": "plugins/example.zip", "sha256": "b" * 64, "size": 1, "media_type": "application/zip"},
        }
        from backend.plugin_platform.manifest import parse_manifest
        from backend.plugin_platform.signing import canonical_release, sign
        manifest = parse_manifest(manifest).model_dump(mode="json")
        self.releases = {
            ("devteam.example.plugin", "1.2.3"): {
                "plugin_id": "devteam.example.plugin", "version": "1.2.3",
                "artifact_sha256": "b" * 64, "status": "published",
                "platform_signature": sign(private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode("utf-8"), canonical_release(manifest, "b" * 64)),
                "permissions": ["project.read"], "manifest": manifest,
            }
        }
        self.installations: dict[tuple[str, str], dict] = {}
        self.idempotency: dict[tuple[str, str, str, str], tuple[str, dict | None]] = {}
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

    def claim(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, command_sha256: str):
        key = (tenant_gid, actor_gid, operation, idempotency_key)
        stored = self.idempotency.get(key)
        if stored is None:
            self.idempotency[key] = (command_sha256, None)
            return None
        if stored[0] != command_sha256:
            from backend.plugin_platform.service import PluginLifecycleError
            raise PluginLifecycleError("idempotency_conflict", "command changed")
        return deepcopy(stored[1])

    def complete(self, *, tenant_gid: str, actor_gid: str, operation: str, idempotency_key: str, command_sha256: str, result: dict) -> None:
        self.idempotency[(tenant_gid, actor_gid, operation, idempotency_key)] = (command_sha256, deepcopy(result))

    def revoke_mounts(self, *, tenant_gid: str, plugin_id: str, installation_id: str, new_revision: int) -> None:
        self.mounts_revoked.append((tenant_gid, plugin_id))

    def preserve_tenant_data(self, *, tenant_gid: str, plugin_id: str, retain: bool) -> None:
        self.data_policy.append((tenant_gid, plugin_id, retain))

    def audit(self, event: dict) -> None:
        self.events.append(deepcopy(event))


def service():
    from backend.plugin_platform.service import PluginPlatformService

    repository = MemoryPluginLifecycleRepository()
    return PluginPlatformService(repository=repository, platform_public_key_provider=lambda: repository.platform_public_key), repository


def test_install_accepts_only_closed_signed_release_identity_and_known_grants():
    """Removing command validation or release/grant verification must fail this test."""
    from backend.plugin_platform.service import PluginLifecycleError

    lifecycle, repository = service()
    with pytest.raises(PluginLifecycleError, match="invalid_input"):
        lifecycle.request_install(actor=ACTOR, command={**INSTALL, "url": "https://evil.example/plugin.zip"})
    with pytest.raises(PluginLifecycleError, match="invalid_input"):
        lifecycle.request_install(actor=ACTOR, command={**INSTALL, "requested_grants": ["unknown.grant"], "idempotency_key": "idem-invalid-grant"})
    repository.releases[("devteam.example.plugin", "1.2.3")]["platform_signature"] = ""
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
        "plugin_id": "devteam.example.plugin", "release_version": "1.2.3", "state": "disabled",
        "revision": 1, "granted_capabilities": ["project.read"], "tenant_gid": "tenant_1",
    }
    assert ("tenant_1", "devteam.example.plugin") in repository.installations
    assert ("tenant_2", "devteam.example.plugin") not in repository.installations
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
    row = repository.installations[("tenant_1", "devteam.example.plugin")]
    assert row["state"] == "uninstalled"
    assert row["granted_capabilities"] == []
    assert repository.mounts_revoked == [("tenant_1", "devteam.example.plugin")]
    assert repository.data_policy == [("tenant_1", "devteam.example.plugin", True)]
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
