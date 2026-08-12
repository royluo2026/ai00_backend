import unittest
from pathlib import Path

from backend.capability_v2.bootstrap import get_capability_registry
from backend.plugin_platform.service import validate_capability_grants

ROOT = Path(__file__).resolve().parents[2]


class PluginAuthorityBoundaryTests(unittest.TestCase):
    def test_capability_must_opt_in_to_plugin_exposure(self):
        capability_registry = get_capability_registry()
        install = capability_registry.get("plugin.install")
        self.assertTrue(install.spec.plugin_callable)
        self.assertEqual(
            validate_capability_grants(["plugin.install"]),
            ("plugin.install",),
        )
        self.assertEqual(install.descriptor.automation_level.value, "A0")
        self.assertEqual(install.descriptor.confirmation_policy, "admin")
        self.assertEqual(install.descriptor.authorization_policy, "base.v2:system.plugin.manage")
        with self.assertRaises(ValueError):
            validate_capability_grants(["missing.capability"])

    def test_only_mount_session_router_constructs_plugin_identity(self):
        service = (ROOT / "backend/plugin_platform/service.py").read_text(encoding="utf-8")
        router = (ROOT / "backend/routers/plugin_marketplace.py").read_text(encoding="utf-8")
        self.assertNotIn("def authorize_plugin_invocation", service)
        self.assertIn("_resolve_mount_for_user", router)
        self.assertIn("type=ConsumerType.PLUGIN", router)
        self.assertNotIn("from backend.base", router)
        self.assertNotIn("import backend.base", router)


if __name__ == "__main__":
    unittest.main()
