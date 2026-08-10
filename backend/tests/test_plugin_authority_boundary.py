import unittest
from pathlib import Path

from backend.capabilities.registry_next import capability_registry
from backend.plugin_platform.service import validate_capability_grants

ROOT = Path(__file__).resolve().parents[2]


class PluginAuthorityBoundaryTests(unittest.TestCase):
    def test_capability_must_opt_in_to_plugin_exposure(self):
        self.assertTrue(capability_registry.get("system.echo").spec.plugin_callable)
        self.assertFalse(capability_registry.get("plugin.install").spec.plugin_callable)
        self.assertEqual(validate_capability_grants(["system.echo"]), ("system.echo",))
        self.assertEqual({spec.id for spec in capability_registry.list(plugin_callable=True)}, {"system.echo", "plugin.storage.get", "plugin.storage.list", "plugin.storage.put", "plugin.storage.delete"})
        with self.assertRaises(ValueError):
            validate_capability_grants(["plugin.install"])
        with self.assertRaises(ValueError):
            validate_capability_grants(["missing.capability"])

    def test_only_mount_session_router_constructs_plugin_identity(self):
        service = (ROOT / "backend/plugin_platform/service.py").read_text(encoding="utf-8")
        router = (ROOT / "backend/routers/plugin_marketplace.py").read_text(encoding="utf-8")
        self.assertNotIn("def authorize_plugin_invocation", service)
        self.assertIn("_resolve_mount_for_user", router)
        self.assertIn("type=ConsumerType.PLUGIN", router)


if __name__ == "__main__":
    unittest.main()
