"""Fail-closed loading for official domain Capability Providers."""
from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from .contracts import SideEffectLevel
from .domain_manifest import DomainManifest, DomainManifestSet

if TYPE_CHECKING:
    from backend.capabilities.registry_next import CapabilityRegistry


class ProviderTrustError(RuntimeError):
    """An official Provider failed a frozen trust-boundary check."""


def _resolved_artifact_root(root: Path, relative_path: str) -> Path:
    repository_root = root.resolve()
    candidate = repository_root.joinpath(*relative_path.split("/"))
    current = repository_root
    for part in relative_path.split("/"):
        current = current / part
        if current.is_symlink():
            raise ProviderTrustError(f"provider_path_symlink: {relative_path}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repository_root)
    except ValueError as exc:
        raise ProviderTrustError(f"provider_path_escape: {relative_path}") from exc
    if not resolved.is_dir():
        raise ProviderTrustError(f"provider_artifact_not_found: {relative_path}")
    return resolved


def hash_domain_artifact(root: Path, relative_path: str) -> str:
    """Hash Python/JSON files in a domain tree using stable repository paths."""

    repository_root = root.resolve()
    artifact_root = _resolved_artifact_root(repository_root, relative_path)
    files: list[tuple[str, Path]] = []
    for path in artifact_root.rglob("*"):
        if path.is_symlink():
            raise ProviderTrustError(f"provider_path_symlink: {relative_path}")
        if not path.is_file() or path.suffix not in {".py", ".json"}:
            continue
        resolved = path.resolve()
        try:
            repository_relative = resolved.relative_to(repository_root).as_posix()
        except ValueError as exc:
            raise ProviderTrustError(f"provider_path_escape: {relative_path}") from exc
        files.append((repository_relative, resolved))
    if not files:
        raise ProviderTrustError(f"provider_artifact_empty: {relative_path}")

    digest = hashlib.sha256()
    for repository_relative, path in sorted(files):
        content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest.update(repository_relative.encode("utf-8") + b"\0" + content + b"\0")
    return f"sha256:{digest.hexdigest()}"


class DomainProviderLoader:
    def __init__(self, root: Path, manifests: DomainManifestSet) -> None:
        self._root = root.resolve()
        self._manifests = manifests

    def register_all(self, registry: "CapabilityRegistry") -> tuple[str, ...]:
        ordered = tuple(sorted(self._manifests.domains, key=lambda item: item.domain_id))
        for manifest in ordered:
            actual_hash = hash_domain_artifact(self._root, manifest.artifact_path)
            if actual_hash != manifest.artifact.artifact_hash:
                raise ProviderTrustError(f"provider_artifact_mismatch: {manifest.domain_id}")

        for manifest in ordered:
            before = set(registry.keys())
            module = self._import_frozen_module(manifest)
            register = getattr(module, "register_capabilities", None)
            if not callable(register):
                raise ProviderTrustError(f"provider_entrypoint_missing: {manifest.domain_id}")
            try:
                register(registry)
            except Exception as exc:
                raise ProviderTrustError(f"provider_load_failed: {manifest.domain_id}") from exc
            added = set(registry.keys()) - before
            owners = {
                registry.get(capability_id, major_version).spec.owner
                for capability_id, major_version in added
            }
            if not owners <= set(manifest.allowed_owners):
                raise ProviderTrustError(f"provider_owner_mismatch: {manifest.domain_id}")
            for owner in manifest.allowed_owners:
                registry.bind_provider_artifact(owner, manifest.artifact)

        self._validate_search_exports(registry)
        return tuple(item.domain_id for item in ordered)

    def _import_frozen_module(self, manifest: DomainManifest) -> ModuleType:
        artifact_root = _resolved_artifact_root(self._root, manifest.artifact_path)
        first_package = manifest.artifact.module.split(".", 1)[0]
        import_root = artifact_root.parent if artifact_root.name == first_package else self._root
        import_root_text = str(import_root)
        injected = import_root_text not in sys.path
        if injected:
            sys.path.insert(0, import_root_text)
        try:
            module = importlib.import_module(manifest.artifact.module)
        except Exception as exc:
            raise ProviderTrustError(f"provider_import_failed: {manifest.domain_id}") from exc
        finally:
            if injected and import_root_text in sys.path:
                sys.path.remove(import_root_text)

        module_file = getattr(module, "__file__", None)
        if module_file is None:
            raise ProviderTrustError(f"provider_module_location_missing: {manifest.domain_id}")
        try:
            Path(module_file).resolve().relative_to(artifact_root)
        except ValueError as exc:
            raise ProviderTrustError(f"provider_module_path_mismatch: {manifest.domain_id}") from exc
        return module

    def _validate_search_exports(self, registry: "CapabilityRegistry") -> None:
        for manifest in self._manifests.domains:
            export = manifest.search_export
            if export is None:
                continue
            try:
                registered = registry.get(export.capability_id, export.major_version)
            except KeyError as exc:
                raise ProviderTrustError(
                    f"search_export_missing: {manifest.domain_id}"
                ) from exc
            descriptor = registered.descriptor
            owner_matches = registered.spec.owner in set(manifest.allowed_owners)
            is_read = (
                descriptor is not None
                and descriptor.side_effect_level is SideEffectLevel.READ
            )
            if not owner_matches or not is_read:
                raise ProviderTrustError(
                    f"search_export_owner_mismatch: {manifest.domain_id}"
                )


__all__ = ["DomainProviderLoader", "ProviderTrustError", "hash_domain_artifact"]
