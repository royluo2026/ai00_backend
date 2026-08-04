import json

from backend.plugin_loader import PluginLoader


def test_legacy_loader_strips_third_party_backend_and_registry(tmp_path):
    packages = tmp_path / "packages"; plugins = tmp_path / "plugins"
    package = packages / "evil"; package.mkdir(parents=True); plugins.mkdir()
    (package / "manifest.json").write_text(json.dumps({
        "plugin_id": "third.evil.plugin", "backend": {"routers_module": "evil.code"},
        "frontend": {"tabs": [{"id": "evil", "src": "index.html"}]}
    }), encoding="utf-8")
    loader = PluginLoader(packages, plugins); found = loader.discover()
    assert "backend" not in found[0]
    assert loader.get_routers() == []
    assert loader.get_web_registry() == {"tabDefs": {}, "navItems": []}
