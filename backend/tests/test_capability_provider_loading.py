import json
from pathlib import Path

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.plugin_loader import PluginLoader


def test_official_domain_providers_load_without_kernel_importing_domains():
    root = Path(__file__).resolve().parents[2]
    loader = PluginLoader(root / "missing-packages", root / "plugins")
    loader.discover()

    loaded = loader.register_capabilities(CapabilityRegistry())

    assert loaded == (
        "agent", "base", "craft", "device", "digital_model", "factory",
        "integration", "knowledge", "ontology", "project_management", "simulation",
    )
    kernel_source = (root / "backend/capabilities/registry_next.py").read_text(encoding="utf-8")
    assert "craft_backend" not in kernel_source
    assert "plugins.craft" not in kernel_source


def test_third_party_manifest_cannot_load_backend_provider(tmp_path):
    packages = tmp_path / "packages"
    plugins = tmp_path / "plugins"
    package = packages / "third-party"
    package.mkdir(parents=True)
    plugins.mkdir()
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "plugin_id": "third.example",
                "backend": {"capabilities_module": "third_party.capabilities"},
            }
        ),
        encoding="utf-8",
    )
    loader = PluginLoader(packages, plugins)

    found = loader.discover()

    assert "backend" not in found[0]
    loaded = loader.register_capabilities(CapabilityRegistry())
    assert "third.example" not in loaded
    assert "base" in loaded


def test_discovered_official_backend_cannot_bypass_central_manifest(tmp_path):
    packages = tmp_path / "packages"
    plugins = tmp_path / "plugins"
    package = packages / "broken"
    package.mkdir(parents=True)
    plugins.mkdir()
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "plugin_id": "official.broken",
                "backend": {"capabilities_module": "module_that_does_not_exist"},
            }
        ),
        encoding="utf-8",
    )
    loader = PluginLoader(packages, plugins)
    loader.discover()

    loaded = loader.register_capabilities(CapabilityRegistry())

    assert "official.broken" not in loaded
