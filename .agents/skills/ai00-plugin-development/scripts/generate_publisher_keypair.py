#!/usr/bin/env python3
"""Generate a non-overwriting Ed25519 publisher key pair for AI00 plugins."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


PRIVATE = serialization.PrivateFormat.PKCS8
PUBLIC = serialization.PublicFormat.SubjectPublicKeyInfo


def _exclusive_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def generate_keypair(output_dir: Path, publisher_id: str) -> dict[str, str]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,127}", publisher_id):
        raise ValueError("publisher_id must be one lowercase namespace segment")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    private_path = output_dir / f"{publisher_id}-private.pem"
    public_path = output_dir / f"{publisher_id}-public.pem"
    if private_path.exists() or public_path.exists():
        raise FileExistsError(
            "publisher key output already exists; refusing to overwrite"
        )

    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(
        Encoding.PEM, PRIVATE, serialization.NoEncryption()
    )
    public_bytes = key.public_key().public_bytes(Encoding.PEM, PUBLIC)
    _exclusive_write(private_path, private_bytes)
    try:
        _exclusive_write(public_path, public_bytes)
    except Exception:
        private_path.unlink(missing_ok=True)
        raise

    if os.name != "nt":
        private_path.chmod(0o600)
    raw_public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {
        "private_key": str(private_path),
        "public_key": str(public_path),
        "fingerprint": hashlib.sha256(raw_public).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an Ed25519 publisher key pair without overwriting files."
    )
    parser.add_argument("--publisher-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = generate_keypair(args.output_dir, args.publisher_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if os.name == "nt":
        print(
            "Protect the key directory with a user-only Windows ACL; the script does not alter directory ACLs.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
