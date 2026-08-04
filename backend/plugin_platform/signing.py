"""Publisher verification and platform release signing using Ed25519."""
from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class SignatureError(ValueError):
    pass


def canonical_release(manifest: dict, artifact_sha256: str) -> bytes:
    body = {"artifact_sha256": artifact_sha256, "manifest": manifest}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint(public_key_pem: str) -> str:
    key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(key, Ed25519PublicKey):
        raise SignatureError("publisher key must be Ed25519")
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def verify(public_key_pem: str, message: bytes, signature_b64: str) -> None:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            raise SignatureError("publisher key must be Ed25519")
        key.verify(base64.b64decode(signature_b64, validate=True), message)
    except SignatureError:
        raise
    except Exception as exc:
        raise SignatureError("invalid release signature") from exc


def sign(private_key_pem: str, message: bytes) -> str:
    try:
        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise SignatureError("platform key must be Ed25519")
        return base64.b64encode(key.sign(message)).decode("ascii")
    except SignatureError:
        raise
    except Exception as exc:
        raise SignatureError("invalid platform signing key") from exc
