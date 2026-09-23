#!/usr/bin/env python3
"""Build, sign, assemble, and verify an AI00 Manifest 2.0 upload bundle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


BUNDLE_ENTRIES = {"plugin.zip", "release.json", "publisher.sig"}
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def canonical_release(release: dict) -> bytes:
    return json.dumps(
        {"artifact_sha256": release["artifact"]["sha256"], "manifest": release},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_builder(sdk_root: Path):
    builder_path = sdk_root.resolve() / "tools" / "build_release.py"
    if not builder_path.is_file():
        raise ValueError(f"official build_release.py not found under SDK root: {sdk_root}")
    spec = importlib.util.spec_from_file_location(
        f"ai00_build_release_{uuid.uuid4().hex}", builder_path
    )
    if spec is None or spec.loader is None:
        raise ValueError("could not load the official AI00 release builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exclusive_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _load_keys(private_key: Path, public_key: Path) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    private = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
    public = serialization.load_pem_public_key(public_key.read_bytes())
    if not isinstance(private, Ed25519PrivateKey):
        raise ValueError("private key must be Ed25519")
    if not isinstance(public, Ed25519PublicKey):
        raise ValueError("public key must be Ed25519")
    derived = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    supplied = public.public_bytes(Encoding.Raw, PublicFormat.Raw)
    if derived != supplied:
        raise ValueError("supplied public key does not match the private key")
    return private, public


def verify_bundle(bundle: Path, public_key: Path) -> dict[str, object]:
    try:
        with zipfile.ZipFile(bundle) as archive:
            names = archive.namelist()
            if set(names) != BUNDLE_ENTRIES or len(names) != 3:
                raise ValueError(
                    "signed package must contain exactly release.json, publisher.sig and plugin.zip"
                )
            release = json.loads(archive.read("release.json").decode("utf-8-sig"))
            if not isinstance(release, dict):
                raise ValueError("release.json must contain an object")
            package = archive.read("plugin.zip")
            signature = base64.b64decode(
                archive.read("publisher.sig").strip(), validate=True
            )
        digest = hashlib.sha256(package).hexdigest()
        artifact = release.get("artifact", {})
        if not isinstance(artifact, dict):
            raise ValueError("release artifact must contain an object")
        if digest != artifact.get("sha256") or len(package) != artifact.get("size"):
            raise ValueError("plugin ZIP does not match release artifact")
        plugin_id = release.get("plugin_id")
        version = release.get("version")
        if not isinstance(plugin_id, str) or not isinstance(version, str):
            raise ValueError("release must contain string plugin_id and version")
        key = serialization.load_pem_public_key(public_key.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("public key must be Ed25519")
        key.verify(signature, canonical_release(release))
    except ValueError:
        raise
    except (InvalidSignature, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ValueError("invalid signed AI00 package") from exc
    return {
        "artifact_sha256": digest,
        "version": version,
        "plugin_id": plugin_id,
        "package_size": len(package),
    }


def prepare_package(
    source: Path,
    sdk_root: Path,
    private_key: Path,
    public_key: Path,
    output: Path,
    version: str | None,
) -> dict[str, object]:
    source = source.resolve()
    output = output.resolve()
    manifest_path = source / "plugin.json"
    if not manifest_path.is_file():
        raise ValueError("plugin source must contain plugin.json at its root")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "2.0":
        raise ValueError(
            "generic release preparation supports Manifest 2.0 only; Manifest 2.1 requires the governed Provider release path"
        )

    private, _ = _load_keys(Path(private_key), Path(public_key))
    output.parent.mkdir(parents=True, exist_ok=True)
    base = output.with_suffix("")
    package_copy = base.with_suffix(".plugin.zip")
    release_copy = base.with_suffix(".release.json")
    signature_copy = base.with_suffix(".publisher.sig")
    created = [package_copy, release_copy, signature_copy, output]
    if any(path.exists() for path in created):
        raise FileExistsError("release output already exists; refusing to overwrite")

    work = output.parent / f".ai00-release-{uuid.uuid4().hex}"
    work.mkdir()
    try:
        builder = _load_builder(Path(sdk_root))
        package_path, release_path, release = builder.build(source, work, version)
        package_data = package_path.read_bytes()
        release_data = release_path.read_bytes()
        signature_data = base64.b64encode(
            private.sign(canonical_release(release))
        ) + b"\n"

        _exclusive_write(package_copy, package_data)
        _exclusive_write(release_copy, release_data)
        _exclusive_write(signature_copy, signature_data)
        descriptor = os.open(output, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w+b") as stream:
                with zipfile.ZipFile(
                    stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
                ) as archive:
                    for name, data in (
                        ("plugin.zip", package_data),
                        ("release.json", release_data),
                        ("publisher.sig", signature_data),
                    ):
                        info = zipfile.ZipInfo(name, FIXED_TIME)
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = 0o100600 << 16
                        info.create_system = 3
                        archive.writestr(info, data)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        verified = verify_bundle(output, Path(public_key))
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        **verified,
        "bundle": str(output),
        "plugin_zip": str(package_copy),
        "release_json": str(release_copy),
        "publisher_signature": str(signature_copy),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version")
    args = parser.parse_args()
    result = prepare_package(
        args.source,
        args.sdk_root,
        args.private_key,
        args.public_key,
        args.output,
        args.version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
