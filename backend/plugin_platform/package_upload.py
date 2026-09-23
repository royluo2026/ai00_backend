"""One-file signed release transport; installation remains a separate outcome."""
import io
import json
import stat
import zipfile

from .manifest import parse_manifest

MAX_BUNDLE = 102 * 1024 * 1024
FILES = {'release.json': 256 * 1024, 'publisher.sig': 256, 'plugin.zip': 100 * 1024 * 1024}


def unpack_bundle(data):
    if not data or len(data) > MAX_BUNDLE:
        raise ValueError('Plugin package exceeds 102 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) != 3 or {item.filename for item in entries} != set(FILES):
                raise ValueError('Signed package must contain exactly release.json, publisher.sig and plugin.zip at its root.')
            for item in entries:
                if item.is_dir() or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1 or not 0 < item.file_size <= FILES[item.filename]:
                    raise ValueError('Invalid or oversized signed package entry.')
            manifest = parse_manifest(json.loads(archive.read('release.json').decode('utf-8-sig')))
            signature = archive.read('publisher.sig').decode('ascii').strip()
            package = archive.read('plugin.zip')
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError) as exc:
        raise ValueError('Invalid signed plugin package.') from exc
    from .artifacts import validate_package
    validate_package(package, manifest)
    return manifest, signature, package


def submit_package(artifact_ref, context):
    from backend.platform_sdk.artifacts import read_artifact
    from backend.capability_v2.artifacts import ArtifactError
    from . import artifacts, service
    if artifact_ref['media_type'] != 'application/zip' or not 0 < artifact_ref['byte_size'] <= MAX_BUNDLE:
        raise ValueError('Select a signed plugin ZIP package (maximum 102 MiB).')
    try:
        data = read_artifact(artifact_ref, context, maximum=MAX_BUNDLE)
    except ArtifactError as exc:
        raise ValueError('The uploaded artifact is unavailable, unauthorized or has changed.') from exc
    manifest, signature, package = unpack_bundle(data)
    normalized = manifest.model_dump(mode='json')
    service.verify_submission_signature(normalized, signature)
    artifacts.upload_to_ois(package, manifest)
    artifacts.publish_web_assets(package, manifest)
    return service.submit_release(normalized, signature, str(context.user_gid))
