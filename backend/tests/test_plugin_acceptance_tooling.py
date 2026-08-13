import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.plugin_platform.artifacts import validate_package
from backend.plugin_platform.manifest import parse_manifest
from backend.plugin_platform.signing import canonical_release
from backend.scripts.plugin_platform_acceptance import Client
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
    def test_database_isolation_verifier_covers_all_first_class_domains(self):
        self.assertEqual(set(URLS), {
            "base", "agent", "craft", "digital_model", "project_management",
            "simulation", "ontology", "knowledge", "local_integration",
        })

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

    def test_reference_release_signs_the_same_canonical_document_the_server_verifies(self):
        root = Path(__file__).resolve().parents[2]
        source = root / "packages/plugin-sdk/examples/hello-capability"
        builder = _load_builder()
        _package, _release, value = builder.build(source, source / "dist")
        normalized = parse_manifest(value).model_dump(mode="json")
        private_key = Ed25519PrivateKey.generate()
        publisher_message = canonical_release(value, value["artifact"]["sha256"])
        server_message = canonical_release(normalized, normalized["artifact"]["sha256"])

        signature = private_key.sign(publisher_message)
        private_key.public_key().verify(signature, server_message)

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

    def test_sdk_example_and_template_only_request_current_plugin_capabilities(self):
        root = Path(__file__).resolve().parents[2]
        catalog = json.loads(
            (root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
        )
        plugin_capabilities = {
            item["id"] for item in catalog["descriptors"] if item["exposure"]["plugin"]
        }
        for source in (
            root / "packages/plugin-sdk/examples/hello-capability/plugin.json",
            root / "packages/plugin-sdk/templates/web-capability/plugin.json",
        ):
            descriptor = json.loads(source.read_text(encoding="utf-8"))
            self.assertLessEqual(set(descriptor["permissions"]), plugin_capabilities)

    def test_lifecycle_acceptance_pins_capability_major_version(self):
        client = Client("http://localhost", "token")
        calls = []

        def request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path.endswith(":confirm"):
                return {"data": {"confirmation_token": "confirm-1"}}
            return {"success": True}

        client.request = request
        client.lifecycle("plugin.install", {"plugin_id": "acme.ai00.hello"})

        self.assertEqual(calls[0][2]["json"]["version"], 1)
        self.assertEqual(calls[1][2]["json"]["version"], 1)
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
