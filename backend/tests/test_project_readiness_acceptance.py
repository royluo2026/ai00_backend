from pathlib import Path

import pytest

from backend.scripts.project_readiness_acceptance import AcceptanceError, verify_mount_contract


def test_verify_mount_contract_requires_exact_manifest_grants():
    manifest = {
        "plugin_id": "devteam.ai00.project-readiness",
        "permissions": ["base.project.search", "plugin.storage.get"],
    }
    mount = {
        "plugin_id": manifest["plugin_id"],
        "mount_session_id": "mount-1",
        "mount_url": "/asset/index.html",
        "capability_versions": {"base.project.search": 1, "plugin.storage.get": 1},
    }
    assert verify_mount_contract(manifest, mount) == (
        "base.project.search",
        "plugin.storage.get",
    )


def test_verify_mount_contract_rejects_missing_or_extra_grants():
    manifest = {"plugin_id": "devteam.ai00.project-readiness", "permissions": ["base.project.search"]}
    with pytest.raises(AcceptanceError, match="mount grants differ"):
        verify_mount_contract(manifest, {
            "plugin_id": manifest["plugin_id"],
            "mount_session_id": "mount-1",
            "mount_url": "/asset/index.html",
            "capability_versions": {"base.project.search": 1, "system.search": 1},
        })


def test_reference_plugin_contains_no_direct_platform_access():
    root = Path(__file__).resolve().parents[2]
    plugin = root / "packages/plugin-sdk/examples/project-readiness"
    source = "\n".join(path.read_text(encoding="utf-8") for path in plugin.glob("*.js"))
    for forbidden in ("document.cookie", "localStorage", "indexedDB", "electronAPI", "fetch(", "XMLHttpRequest", "/api/"):
        assert forbidden not in source
