"""Encrypted, authenticated references for immutable private workspace exports."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class ExportRefError(ValueError): pass


def _fernet() -> Fernet:
    secret=os.getenv("AI00_SIMULATION_EXPORT_SIGNING_KEY","")
    if len(secret)<8: raise ExportRefError("export_signing_key_unavailable")
    key=base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def issue_export_ref(claims: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(claims,sort_keys=True,separators=(",", ":")).encode()).decode()


def verify_export_ref(reference: str, *, now_epoch: int | None = None) -> dict[str, Any]:
    try: claims=json.loads(_fernet().decrypt(reference.encode()).decode())
    except (InvalidToken,ValueError,TypeError,json.JSONDecodeError) as exc: raise ExportRefError("private_export_invalid") from exc
    if now_epoch is not None and int(claims["expires_at_epoch"]) <= now_epoch: raise ExportRefError("private_export_expired")
    return claims


def export_ref_digest(reference: str) -> str:
    return "sha256:"+hashlib.sha256(reference.encode()).hexdigest()
