"""Local Windows DPAPI storage for the shared Agent Runtime credential."""
from __future__ import annotations

import ctypes
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

_DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(value: bytes, function_name: str) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is unavailable")
    buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _DataBlob()
    function = getattr(ctypes.windll.crypt32, function_name)
    if not function(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _protect(value: bytes) -> bytes:
    return _dpapi(value, "CryptProtectData")


def _unprotect(value: bytes) -> bytes:
    return _dpapi(value, "CryptUnprotectData")


class RuntimeSecretStore:
    def __init__(
        self,
        path: str | Path,
        *,
        protect: Callable[[bytes], bytes] | None = None,
        unprotect: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.path = Path(path)
        self._protect = protect or _protect
        self._unprotect = unprotect or _unprotect

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        value = json.loads(self._unprotect(self.path.read_bytes()).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("invalid Agent Runtime secret payload")
        return {str(key): str(item) for key, item in value.items()}

    def save(self, config: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")
        encrypted = self._protect(raw)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as handle:
                temporary_path = Path(handle.name)
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def runtime_secret_store() -> RuntimeSecretStore:
    configured = os.getenv("AI_RUNTIME_SECRET_FILE", "").strip()
    path = Path(configured) if configured else Path(__file__).resolve().parents[4] / ".runtime" / "agent-runtime-secret.dpapi"
    return RuntimeSecretStore(path)


def resolve_runtime_config(
    *, store: RuntimeSecretStore | None = None, default_model: str = _DEFAULT_MODEL,
) -> dict[str, str]:
    key = os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    if key:
        return {
            "model": os.getenv("AI_MODEL", default_model),
            "api_key": key,
            "api_base": os.getenv("AI_API_BASE", ""),
            "source": "env",
        }
    saved = (store or runtime_secret_store()).load()
    if saved.get("api_key"):
        return {
            "model": saved.get("model") or default_model,
            "api_key": saved["api_key"],
            "api_base": saved.get("api_base", ""),
            "source": "local_secret",
        }
    return {"model": "", "api_key": "", "api_base": "", "source": "none"}


__all__ = ["RuntimeSecretStore", "resolve_runtime_config", "runtime_secret_store"]
