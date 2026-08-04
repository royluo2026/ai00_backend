import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.capabilities.registry_next import capability_registry
from backend.plugin_platform.service import authorize_plugin_invocation, validate_capability_grants

ROOT = Path(__file__).resolve().parents[2]
V3_ROOT = ROOT.parent


class _Cursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _params):
        return None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.cursor_value = _Cursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value


def _connection_module(row):
    module = types.ModuleType("backend.db.connection")
    module.get_conn = lambda: _Connection(row)
    return module


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

    def test_server_authorizes_active_tenant_installation_and_exact_version(self):
        row = {"state": "enabled", "current_version": "1.2.3", "status": "published", "granted_capabilities": '["system.echo"]'}
        with patch.dict(sys.modules, {"backend.db.connection": _connection_module(row)}):
            identity = authorize_plugin_invocation({"gid": "u1", "team_id": "t1"}, "acme.ai00.hello", "1.2.3", "system.echo")
        self.assertEqual(identity["tenant_gid"], "t1")
        self.assertEqual(identity["plugin_id"], "acme.ai00.hello")

    def test_server_rejects_disabled_or_wrong_version_plugin(self):
        disabled = {"state": "disabled", "current_version": "1.2.3", "status": "published", "granted_capabilities": '["system.echo"]'}
        with patch.dict(sys.modules, {"backend.db.connection": _connection_module(disabled)}):
            with self.assertRaises(PermissionError):
                authorize_plugin_invocation({"gid": "u1"}, "acme.ai00.hello", "1.2.3", "system.echo")
        active = dict(disabled, state="enabled")
        with patch.dict(sys.modules, {"backend.db.connection": _connection_module(active)}):
            with self.assertRaises(PermissionError):
                authorize_plugin_invocation({"gid": "u1"}, "acme.ai00.hello", "2.0.0", "system.echo")

    def test_web_bridge_sends_plugin_identity_to_capability_kernel(self):
        workspace = (V3_ROOT / "workmanship-web/web/workspace/workspace.js").read_text(encoding="utf-8")
        compat = (V3_ROOT / "workmanship-web/web/core/web_compat.js").read_text(encoding="utf-8")
        self.assertIn("plugin.pluginId, plugin.version", workspace)
        self.assertIn("'X-AI00-Plugin-ID': pluginId", compat)
        self.assertIn("'X-AI00-Plugin-Version': pluginVersion", compat)


if __name__ == "__main__":
    unittest.main()