import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest


def bundle():
    from backend.tests.test_plugin_lifecycle_security import Repository
    from backend.plugin_platform.signing import canonical_release, sign
    repo = Repository()
    descriptor = dict(repo.manifest); descriptor.pop('artifact')
    package = io.BytesIO()
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('plugin.json', json.dumps(descriptor))
        archive.writestr('index.html', '<h1>Plugin</h1>')
    data = package.getvalue(); digest = hashlib.sha256(data).hexdigest()
    manifest = {**descriptor, 'artifact': {'object_key': f'plugins/devteam/devteam.example.plugin/1.2.3/{digest}.zip', 'sha256': digest, 'size': len(data), 'media_type': 'application/zip'}}
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as archive:
        archive.writestr('release.json', json.dumps(manifest))
        archive.writestr('publisher.sig', sign(repo._private_key, canonical_release(manifest, digest)))
        archive.writestr('plugin.zip', data)
    return result.getvalue(), repo, manifest


def test_bundle_validates_embedded_package_and_detached_signature(monkeypatch):
    from backend.plugin_platform.package_upload import submit_package
    from backend.plugin_platform.signing import verify, canonical_release
    data, repo, manifest = bundle(); calls = []
    monkeypatch.setattr('backend.platform_sdk.artifacts.read_artifact', lambda *a, **kw: data)
    monkeypatch.setattr('backend.plugin_platform.service.verify_submission_signature', lambda m, sig: verify(repo.platform_public_key, canonical_release(m, m['artifact']['sha256']), sig))
    monkeypatch.setattr('backend.plugin_platform.artifacts.upload_to_ois', lambda *a: calls.append('upload'))
    monkeypatch.setattr('backend.plugin_platform.artifacts.publish_web_assets', lambda *a: calls.append('assets'))
    monkeypatch.setattr('backend.plugin_platform.service.submit_release', lambda m, s, actor: {'plugin_id': m['plugin_id'], 'version': m['version'], 'status': 'submitted'})
    ref = {'media_type': 'application/zip', 'byte_size': len(data)}
    assert submit_package(ref, SimpleNamespace(user_gid='admin'))['status'] == 'submitted'
    assert calls == ['upload', 'assets']
    monkeypatch.setattr('backend.plugin_platform.service.verify_submission_signature', lambda *a: (_ for _ in ()).throw(ValueError('bad signature')))
    calls.clear()
    with pytest.raises(ValueError, match='bad signature'): submit_package(ref, SimpleNamespace(user_gid='admin'))
    assert calls == []


def test_bundle_rejects_unsafe_shape_before_storage():
    from backend.plugin_platform.package_upload import unpack_bundle
    for names in [('release.json', '../plugin.zip', 'publisher.sig'), ('release.json', 'release.json', 'publisher.sig'), ('plugin.json', 'index.html')]:
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            for name in names: archive.writestr(name, '{}')
        with pytest.raises(ValueError): unpack_bundle(data.getvalue())
