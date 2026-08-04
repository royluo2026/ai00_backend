import unittest

from backend.capabilities.models_next import CapabilityContext
from backend.plugin_platform.service import _apply_uninstall_data_policy
from backend.plugin_platform.storage import MAX_VALUE_BYTES, _encoded, _identity, _key


class _PolicyCursor:
    def __init__(self, manifest):
        self.manifest = manifest
        self.sql = []

    def execute(self, sql, params):
        self.sql.append((sql, params))

    def fetchone(self):
        return {"manifest": self.manifest}


class PluginNamespaceStorageContractTests(unittest.TestCase):
    def test_namespace_is_derived_from_authorized_context(self):
        context = CapabilityContext(user_gid="u1", team_gid="team-1", source="plugin", plugin_id="acme.ai00.hello", plugin_version="1.0.0")
        self.assertEqual(_identity(context), ("team-1", "acme.ai00.hello"))
        personal = CapabilityContext(user_gid="u1", source="plugin", plugin_id="acme.ai00.hello")
        self.assertEqual(_identity(personal), ("user:u1", "acme.ai00.hello"))

    def test_non_plugin_context_cannot_choose_a_namespace(self):
        with self.assertRaises(PermissionError):
            _identity(CapabilityContext(user_gid="u1", source="web", plugin_id="acme.ai00.hello"))

    def test_keys_and_values_are_bounded(self):
        self.assertEqual(_key({"key": "settings/view"}), "settings/view")
        for key in ("", "/root", "a/../b"):
            with self.assertRaises(ValueError):
                _key({"key": key})
        self.assertEqual(_encoded({"ok": True}), '{"ok":true}')
        with self.assertRaises(ValueError):
            _encoded("x" * MAX_VALUE_BYTES)

    def test_uninstall_applies_signed_data_policy(self):
        delete_cursor = _PolicyCursor('{"data":{"retention":"while-installed","uninstall":"delete"}}')
        self.assertEqual(_apply_uninstall_data_policy(delete_cursor, "t1", "acme.ai00.hello", "1.0.0"), "deleted")
        self.assertTrue(any("DELETE FROM workmanship_plugin_namespace_kv" in sql for sql, _ in delete_cursor.sql))
        export_cursor = _PolicyCursor('{"data":{"retention":"tenant-policy","uninstall":"export-then-delete"}}')
        with self.assertRaises(ValueError):
            _apply_uninstall_data_policy(export_cursor, "t1", "acme.ai00.hello", "1.0.0")

if __name__ == "__main__":
    unittest.main()