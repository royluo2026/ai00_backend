"""ZIP safety validation and immutable OIS artifact upload."""
from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile

from .manifest import PluginManifestV2


class ArtifactError(ValueError):
    pass


def validate_package(data: bytes, manifest: PluginManifestV2) -> str:
    if len(data) != manifest.artifact.size:
        raise ArtifactError("package size does not match signed manifest")
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest.artifact.sha256:
        raise ArtifactError("package SHA-256 does not match signed manifest")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000:
                raise ArtifactError("package contains too many files")
            if any(item.file_size > 25 * 1024 * 1024 for item in infos):
                raise ArtifactError("an individual plugin asset exceeds 25 MiB")
            expanded = sum(item.file_size for item in infos)
            if expanded > 250 * 1024 * 1024:
                raise ArtifactError("expanded package exceeds limit")
            names: set[str] = set()
            for item in infos:
                path = item.filename.replace("\\", "/")
                segments = path.split("/")
                if path.startswith("/") or ".." in segments or any(":" in segment for segment in segments):
                    raise ArtifactError("package contains an unsafe path")
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ArtifactError("symbolic links are forbidden")
                names.add(path.rstrip("/"))
            if "plugin.json" not in names:
                raise ArtifactError("package root must contain plugin.json")
            embedded = json.loads(archive.read("plugin.json"))
            # Artifact digest/size describe the enclosing ZIP and cannot recursively
            # be embedded. plugin.json is the descriptor; artifact metadata is detached.
            submitted_descriptor = manifest.model_dump(mode="json")
            submitted_descriptor.pop("artifact", None)
            if "capabilities" not in embedded and submitted_descriptor.get("capabilities") == {
                "required": [], "optional": [],
            }:
                submitted_descriptor.pop("capabilities")
            if embedded != submitted_descriptor:
                raise ArtifactError("embedded plugin.json differs from signed release descriptor")
    except ArtifactError:
        raise
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ArtifactError("invalid plugin ZIP package") from exc
    return digest


def upload_to_ois(data: bytes, manifest: PluginManifestV2) -> str:
    expected_key = f"plugins/{manifest.publisher_id}/{manifest.plugin_id}/{manifest.version}/{manifest.artifact.sha256}.zip"
    if manifest.artifact.object_key != expected_key:
        raise ArtifactError(f"artifact.object_key must be {expected_key}")
    from backend.core import ois_storage
    cfg = ois_storage._get_ois_config()
    identify = cfg.get("identify", "")
    client, error = ois_storage._make_client()
    if not identify or not client:
        raise ArtifactError(f"OIS is unavailable: {error or 'missing identify'}")
    response = client.put_object(identify, expected_key, io.BytesIO(data))
    if not (hasattr(response, "is_succeed") and response.is_succeed()):
        raise ArtifactError("OIS rejected plugin artifact upload")
    return expected_key


def publish_web_assets(data: bytes, manifest: PluginManifestV2) -> dict:
    """Expand validated files to immutable OIS keys for the sandbox asset gateway."""
    from backend.core import ois_storage
    cfg = ois_storage._get_ois_config()
    identify = cfg.get("identify", "")
    client, error = ois_storage._make_client()
    if not identify or not client: raise ArtifactError(f"OIS is unavailable: {error or 'missing identify'}")
    prefix = f"plugin-assets/{manifest.publisher_id}/{manifest.plugin_id}/{manifest.version}/{manifest.artifact.sha256}"
    uploaded = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            path = item.filename.replace("\\", "/").rstrip("/")
            if not path or item.is_dir(): continue
            response = client.put_object(identify, f"{prefix}/{path}", io.BytesIO(archive.read(item)))
            if not (hasattr(response, "is_succeed") and response.is_succeed()):
                raise ArtifactError(f"OIS rejected plugin asset: {path}")
            uploaded += 1
    return {"prefix": prefix, "uploaded_files": uploaded}
