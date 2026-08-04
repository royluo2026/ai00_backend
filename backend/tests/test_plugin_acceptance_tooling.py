import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.plugin_platform.artifacts import validate_package
from backend.plugin_platform.manifest import parse_manifest
from backend.scripts.plugin_platform_preflight import evaluate
from backend.scripts.verify_domain_db_isolation import URLS, verify


def _load_builder():
    path = Path(__file__).resolve().parents[2] / "packages/plugin-sdk/tools/build_release.py"
    spec = importlib.util.spec_from_file_location("ai00_plugin_build_release", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PluginAcceptanceToolingTests(unittest.TestCase):
    def test_reference_package_is_deterministic_and_platform_valid(self):
        root = Path(__file__).resolve().parents[2]
        source = root / "packages/plugin-sdk/examples/hello-capability"
        builder = _load_builder()
        output = source / "dist"
        zip1, release1, value1 = builder.build(source, output)
        first_bytes = zip1.read_bytes()
        zip2, _release2, value2 = builder.build(source, output)
        self.assertEqual(first_bytes, zip2.read_bytes())
        self.assertEqual(value1["artifact"]["sha256"], value2["artifact"]["sha256"])
        manifest = parse_manifest(json.loads(release1.read_text(encoding="utf-8")))
        self.assertEqual(validate_package(zip1.read_bytes(), manifest), value1["artifact"]["sha256"])

    def test_template_package_contains_sdk_and_is_platform_valid(self):
        root = Path(__file__).resolve().parents[2]
        source = root / "packages/plugin-sdk/templates/web-capability"
        builder = _load_builder()
        package, release, value = builder.build(source, source / "dist")
        manifest = parse_manifest(json.loads(release.read_text(encoding="utf-8")))
        self.assertEqual(validate_package(package.read_bytes(), manifest), value["artifact"]["sha256"])
        with zipfile.ZipFile(package) as archive:
            names = set(archive.namelist())
            self.assertIn("ai00-plugin-sdk.js", names)
            self.assertIn('from "./ai00-plugin-sdk.js"', archive.read("app.js").decode("utf-8"))
            self.assertIn("export class Ai00PluginClient", archive.read("ai00-plugin-sdk.js").decode("utf-8"))
    def test_preflight_fails_closed_without_echoing_secrets(self):
        secret = "do-not-print-this-secret-value-123456789"
        checks = evaluate({"AI00_PLUGIN_MOUNT_SECRET": secret})
        self.assertTrue(any(item.name == "AI00_DDL_DB_URL" and item.status == "fail" for item in checks))
        self.assertFalse(any(secret in item.detail for item in checks))

    def test_isolation_verifier_reports_all_missing_accounts_without_db_driver(self):
        inventory = Path(__file__).resolve().parents[1] / "governance/table_inventory.json"
        results = verify(inventory, env={})
        self.assertEqual(len(results), len(URLS))
        self.assertTrue(all(not item.ok and item.check == "connection" for item in results))


if __name__ == "__main__":
    unittest.main()