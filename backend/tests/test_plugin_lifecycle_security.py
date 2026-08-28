from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import pytest


INSTALL = {
    "plugin_id": "plugin.example",
    "release_version": "1.2.3",
    "release_sha256": "sha256:" + "b" * 64,
    "requested_grants": ["project.read"],
    "idempotency_key": "shared-key",
}


class Repository:
    """Small lifecycle boundary fake; signature/dependency policy stays in the real service."""

    def __init__(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        self._private_key = private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ).decode("utf-8")
        self.platform_public_key = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        self.manifest = {
            "schema_version": "2.0", "plugin_id": "devteam.example.plugin", "publisher_id": "devteam",
            "name": "Example", "version": "1.2.3", "compatibility": {"platform_api": "1", "web_sdk": "1"},
            "runtimes": {"web": {"entry": "index.html"}}, "permissions": ["project.read"],
            "capabilities": {"required": [], "optional": []},
            "artifact": {"object_key": "plugins/example.zip", "sha256": "b" * 64, "size": 1, "media_type": "application/zip"},
        }
        from backend.plugin_platform.manifest import parse_manifest
        from backend.plugin_platform.signing import canonical_release, sign
        self.manifest = parse_manifest(self.manifest).model_dump(mode="json")
        self.release_row = {
            "plugin_id": "devteam.example.plugin",
            "version": "1.2.3",
            "artifact_sha256": "b" * 64,
            "status": "published",
            "platform_signature": sign(self._private_key, canonical_release(self.manifest, "b" * 64)),
            "permissions": ["project.read"],
            "manifest": self.manifest,
        }
        self.installations: dict[tuple[str, str], dict] = {}
        self.replays: dict[tuple[str, str, str, str], tuple[str, dict]] = {}

    def resign(self) -> None:
        from backend.plugin_platform.manifest import parse_manifest
        from backend.plugin_platform.signing import canonical_release, sign
        self.manifest = parse_manifest(self.manifest).model_dump(mode="json")
        self.release_row["manifest"] = self.manifest
        self.release_row["platform_signature"] = sign(self._private_key, canonical_release(self.manifest, "b" * 64))

    @contextmanager
    def transaction(self):
        yield self

    def release(self, _plugin_id, _version, *, lock=False):
        return deepcopy(self.release_row)

    def installation(self, tenant_gid, plugin_id, *, lock=False):
        value = self.installations.get((tenant_gid, plugin_id))
        return deepcopy(value) if value else None

    def save_installation(self, row):
        self.installations[(row["tenant_gid"], row["plugin_id"])] = deepcopy(row)

    def claim(self, *, tenant_gid, actor_gid, operation, idempotency_key, command_sha256):
        stored = self.replays.get((tenant_gid, actor_gid, operation, idempotency_key))
        if stored is None:
            self.replays[(tenant_gid, actor_gid, operation, idempotency_key)] = (command_sha256, None)
            return None
        if stored[0] != command_sha256:
            from backend.plugin_platform.service import PluginLifecycleError
            raise PluginLifecycleError("idempotency_conflict", "command changed")
        return deepcopy(stored[1])

    def complete(self, *, tenant_gid, actor_gid, operation, idempotency_key, command_sha256, result):
        self.replays[(tenant_gid, actor_gid, operation, idempotency_key)] = (command_sha256, deepcopy(result))

    def revoke_mounts(self, **_kwargs):
        return None

    def preserve_tenant_data(self, **_kwargs):
        return None

    def audit(self, _event):
        return None


def _service(repository: Repository):
    from backend.plugin_platform.service import PluginPlatformService

    return PluginPlatformService(
        repository=repository,
        platform_public_key_provider=lambda: repository.platform_public_key,
    )


def test_install_rejects_an_invalid_nonempty_platform_signature():
    """Fails if a truthy database signature can substitute for Ed25519 verification."""
    from backend.plugin_platform.service import PluginLifecycleError

    repository = Repository()
    repository.release_row["platform_signature"] = "invalid-but-nonempty"
    with pytest.raises(PluginLifecycleError, match="release_not_verified"):
        _service(repository).request_install(
            actor={"gid": "user_1", "tenant_gid": "tenant_1"}, command={**INSTALL, "plugin_id": "devteam.example.plugin"},
        )


def test_install_rejects_a_release_without_a_signed_manifest_dependency_resolution():
    """Fails if absent required dependency evidence is treated as ready."""
    from backend.plugin_platform.service import PluginLifecycleError

    repository = Repository()
    repository.release_row.pop("manifest")
    with pytest.raises(PluginLifecycleError, match="release_not_verified"):
        _service(repository).request_install(
            actor={"gid": "user_1", "tenant_gid": "tenant_1"}, command={**INSTALL, "plugin_id": "devteam.example.plugin"},
        )


def test_required_catalog_dependency_fails_closed_while_optional_dependency_does_not():
    """Fails if a missing required signed dependency is silently treated as an optional one."""
    from backend.plugin_platform.service import PluginLifecycleError

    required = Repository()
    required.manifest["capabilities"] = {"required": [{"id": "missing.capability", "major": 1}], "optional": []}
    required.resign()
    with pytest.raises(PluginLifecycleError, match="release_not_verified"):
        _service(required).request_install(
            actor={"gid": "user_1", "tenant_gid": "tenant_1"}, command={**INSTALL, "plugin_id": "devteam.example.plugin"},
        )

    optional = Repository()
    optional.manifest["capabilities"] = {"required": [], "optional": [{"id": "missing.capability", "major": 1}]}
    optional.resign()
    assert _service(optional).request_install(
        actor={"gid": "user_1", "tenant_gid": "tenant_1"}, command={**INSTALL, "plugin_id": "devteam.example.plugin"},
    )["state"] == "disabled"


def test_required_tenant_plugin_dependency_must_be_installed():
    """Fails if a signed required plugin can be installed without its tenant dependency."""
    from backend.plugin_platform.service import PluginLifecycleError

    required = Repository()
    required.manifest["plugins"] = {
        "required": [{"plugin_id": "devteam.dependency.plugin", "version": "1.0.0"}],
        "optional": [],
    }
    required.resign()
    with pytest.raises(PluginLifecycleError, match="release_not_verified"):
        _service(required).request_install(
            actor={"gid": "user_1", "tenant_gid": "tenant_1"}, command={**INSTALL, "plugin_id": "devteam.example.plugin"},
        )

    ready = Repository()
    ready.manifest["plugins"] = required.manifest["plugins"]
    ready.resign()
    ready.installations[("tenant_1", "devteam.dependency.plugin")] = {
        "tenant_gid": "tenant_1", "plugin_id": "devteam.dependency.plugin", "release_version": "1.0.0", "state": "enabled",
    }
    assert _service(ready).request_install(
        actor={"gid": "user_1", "tenant_gid": "tenant_1"}, command={**INSTALL, "plugin_id": "devteam.example.plugin"},
    )["state"] == "disabled"


def test_platform_public_key_provider_fails_closed_without_a_public_key(monkeypatch):
    """Fails if verification can silently fall back to a publication private key or empty key."""
    from backend.plugin_platform.service import platform_public_key
    from backend.plugin_platform.signing import SignatureError

    monkeypatch.delenv("AI00_PLUGIN_PLATFORM_ED25519_PUBLIC_KEY", raising=False)
    with pytest.raises(SignatureError, match="not configured"):
        platform_public_key()
    monkeypatch.setenv("AI00_PLUGIN_PLATFORM_ED25519_PUBLIC_KEY", "public-key\\nvalue")
    assert platform_public_key() == "public-key\nvalue"


def test_idempotency_is_scoped_to_tenant_and_conflicts_on_a_changed_command():
    """Fails if an actor can replay tenant A's result in tenant B or mutate a claimed command."""
    repository = Repository()
    service = _service(repository)

    command = {**INSTALL, "plugin_id": "devteam.example.plugin"}
    first = service.request_install(actor={"gid": "user_1", "tenant_gid": "tenant_a"}, command=command)
    second = service.request_install(actor={"gid": "user_1", "tenant_gid": "tenant_b"}, command=command)

    assert first["tenant_gid"] == "tenant_a"
    assert second["tenant_gid"] == "tenant_b"
    with pytest.raises(Exception, match="idempotency_conflict"):
        service.request_install(
            actor={"gid": "user_1", "tenant_gid": "tenant_b"},
            command={**command, "release_version": "9.9.9"},
        )
