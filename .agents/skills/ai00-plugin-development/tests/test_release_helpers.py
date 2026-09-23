from __future__ import annotations

import hashlib
import importlib.util
import shutil
import unittest
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


SKILL_ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
