from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "plugin-sdk"


def load_script(name: str):
    path = SKILL_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class KeyGenerationTests(unittest.TestCase):
    def setUp(self):
        test_tmp = Path.cwd() / ".test-tmp-ai00-plugin-development"
        test_tmp.mkdir(exist_ok=True)
        self.root = test_tmp / uuid.uuid4().hex
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_generate_keypair_matches_platform_fingerprint(self):
        keygen = load_script("generate_publisher_keypair")
        result = keygen.generate_keypair(self.root, "huangjing")
        private = serialization.load_pem_private_key(
            Path(result["private_key"]).read_bytes(), password=None
        )
        public = serialization.load_pem_public_key(
            Path(result["public_key"]).read_bytes()
        )
        self.assertIsInstance(private, Ed25519PrivateKey)
        self.assertEqual(
            private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
            public.public_bytes(Encoding.Raw, PublicFormat.Raw),
        )
        raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.assertEqual(result["fingerprint"], hashlib.sha256(raw).hexdigest())

    def test_generate_keypair_refuses_overwrite_without_changing_files(self):
        keygen = load_script("generate_publisher_keypair")
        first = keygen.generate_keypair(self.root, "huangjing")
        before = {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in first.items()
            if name.endswith("key")
        }
        with self.assertRaises(FileExistsError):
            keygen.generate_keypair(self.root, "huangjing")
        after = {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in first.items()
            if name.endswith("key")
        }
        self.assertEqual(before, after)


class PackagePreparationTests(unittest.TestCase):
    def setUp(self):
        test_tmp = Path.cwd() / ".test-tmp-ai00-plugin-development"
        test_tmp.mkdir(exist_ok=True)
        self.root = test_tmp / uuid.uuid4().hex
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.plugin = self.root / "plugin"
        self.plugin.mkdir()
        self.manifest = {
            "schema_version": "2.0",
            "plugin_id": "huangjing.demo.hello",
            "publisher_id": "huangjing",
            "name": "Hello",
            "version": "1.0.0",
            "compatibility": {
                "platform_api": ">=1.0.0 <2.0.0",
                "web_sdk": ">=0.1.0 <1.0.0",
            },
            "runtimes": {"web": {"entry": "index.html", "sandbox": "allow-scripts"}},
            "permissions": [],
        }
        (self.plugin / "plugin.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        (self.plugin / "index.html").write_text("<!doctype html><title>Hello</title>", encoding="utf-8")
        keygen = load_script("generate_publisher_keypair")
        keys = keygen.generate_keypair(self.root / "keys", "huangjing")
        self.private = Path(keys["private_key"])
        self.public = Path(keys["public_key"])
        self.output = self.root / "dist" / "huangjing.demo.hello-1.0.0.ai00pkg"

    def test_prepare_package_builds_exact_verified_bundle(self):
        prepare = load_script("prepare_signed_package")
        result = prepare.prepare_package(
            self.plugin, SDK_ROOT, self.private, self.public, self.output, None
        )
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"plugin.zip", "release.json", "publisher.sig"},
            )
        verified = prepare.verify_bundle(self.output, self.public)
        self.assertEqual(verified["artifact_sha256"], result["artifact_sha256"])

    def test_prepare_package_rejects_mismatched_keys(self):
        prepare = load_script("prepare_signed_package")
        keygen = load_script("generate_publisher_keypair")
        other = keygen.generate_keypair(self.root / "other", "otherpub")
        with self.assertRaisesRegex(ValueError, "does not match"):
            prepare.prepare_package(
                self.plugin,
                SDK_ROOT,
                self.private,
                Path(other["public_key"]),
                self.output,
                None,
            )
        self.assertFalse(self.output.exists())

    def test_verify_bundle_rejects_each_tampered_entry(self):
        prepare = load_script("prepare_signed_package")
        prepare.prepare_package(
            self.plugin, SDK_ROOT, self.private, self.public, self.output, None
        )
        with zipfile.ZipFile(self.output) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        for entry in ("plugin.zip", "release.json", "publisher.sig"):
            tampered = self.root / f"tampered-{entry.replace('.', '-')}.ai00pkg"
            with zipfile.ZipFile(tampered, "w") as archive:
                for name, data in original.items():
                    archive.writestr(name, data + b"x" if name == entry else data)
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                prepare.verify_bundle(tampered, self.public)

    def test_prepare_package_rejects_manifest_v21(self):
        prepare = load_script("prepare_signed_package")
        self.manifest["schema_version"] = "2.1"
        self.manifest["provides"] = [
            {
                "capability_id": "huangjing.demo.echo",
                "major": 1,
                "owner_domain": "huangjing",
                "module": "provider.mjs",
                "export": "invoke",
                "result": "json",
            }
        ]
        (self.plugin / "plugin.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "governed Provider"):
            prepare.prepare_package(
                self.plugin, SDK_ROOT, self.private, self.public, self.output, None
            )
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
