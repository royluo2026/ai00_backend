import base64
import io
import json
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.plugin_platform.artifacts import ArtifactError, validate_package
from backend.plugin_platform.compatibility import satisfies
from backend.plugin_platform.lifecycle import LifecycleError, begin_upgrade, require_transition, rollback
from backend.plugin_platform.manifest import ManifestError, parse_manifest
from backend.plugin_platform.signing import SignatureError, canonical_release, verify


def descriptor():
    return {
        "schema_version": "2.0", "plugin_id": "acme.ai00.hello", "publisher_id": "acme",
        "name": "Hello", "description": "test", "version": "1.2.3",
        "compatibility": {"platform_api": ">=1.0.0 <2.0.0", "web_sdk": "^0.1.0"},
        "runtimes": {"web": {"entry": "index.html", "sandbox": "allow-scripts"}},
        "permissions": ["plugin.storage.get"],
        "data": {"stores_personal_data": False, "retention": "none", "uninstall": "delete"},
    }


def package_bytes(value=None, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(value or descriptor(), separators=(",", ":")))
        archive.writestr("index.html", "<!doctype html><title>safe</title>")
        if extra: archive.writestr(extra, "bad")
    return output.getvalue()


def release(package):
    import hashlib
    value = descriptor()
    digest = hashlib.sha256(package).hexdigest()
    value["artifact"] = {"object_key": f"plugins/acme/acme.ai00.hello/1.2.3/{digest}.zip", "sha256": digest, "size": len(package), "media_type": "application/zip"}
    return value


def test_manifest_rejects_backend_execution_and_namespace_escape():
    value = release(package_bytes())
    value["backend"] = {"routers_module": "evil.routers"}
    with pytest.raises(ManifestError): parse_manifest(value)
    value = release(package_bytes()); value["plugin_id"] = "other.ai00.hello"
    with pytest.raises(ManifestError): parse_manifest(value)


def test_publisher_signature_and_tamper_detection():
    package = package_bytes(); manifest = parse_manifest(release(package)); normalized = manifest.model_dump(mode="json")
    private = Ed25519PrivateKey.generate(); public = private.public_key()
    pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    message = canonical_release(normalized, manifest.artifact.sha256)
    signature = base64.b64encode(private.sign(message)).decode()
    verify(pem, message, signature)
    with pytest.raises(SignatureError): verify(pem, message + b"x", signature)


def test_zip_validation_and_path_traversal_rejection():
    package = package_bytes(); manifest = parse_manifest(release(package))
    assert validate_package(package, manifest) == manifest.artifact.sha256
    unsafe = package_bytes(extra="../escape.txt"); unsafe_manifest = parse_manifest(release(unsafe))
    with pytest.raises(ArtifactError): validate_package(unsafe, unsafe_manifest)


def test_lifecycle_upgrade_rollback_and_invalid_transition():
    require_transition("disabled", "enabled")
    result = begin_upgrade("1.0.0", "1.1.0")
    assert (result.state, result.previous_version) == ("upgrading", "1.0.0")
    restored = rollback(result.current_version, result.previous_version)
    assert (restored.current_version, restored.state) == ("1.0.0", "rolled_back")
    with pytest.raises(LifecycleError): require_transition("enabled", "uninstalled")


def test_compatibility_ranges():
    assert satisfies("1.4.2", ">=1.0.0 <2.0.0")
    assert satisfies("0.1.9", "^0.1.0")
    assert not satisfies("2.0.0", ">=1.0.0 <2.0.0")
