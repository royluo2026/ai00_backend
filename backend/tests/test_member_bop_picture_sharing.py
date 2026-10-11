import hashlib
import io
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from backend.capability_v2 import artifacts as a
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, TenantIdentity
from types import SimpleNamespace
from backend.tests.test_desktop_historical_attachments import LocalDatabase, trust_fixture_upload
from plugins.craft.craft_backend.capabilities import member_pictures as pictures


def identity(user, tenant='team', role='member'):
    return ConsumerIdentity(actor=ActorIdentity(user_id=user, authentication_method='test', authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id=tenant, membership='member', active_roles=(role,)),
        consumer=ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id='test'))


def test_shared_download_keeps_private_uploads_and_integrity():
    service = a.ArtifactService(a.InMemoryArtifactStore(), a.InMemoryObjectStorage())
    owner = identity('owner')
    data = b'\x89PNG\r\n\x1a\nfixture'
    digest = hashlib.sha256(data).hexdigest()
    upload = service.create_upload(owner, media_type='image/png', expected_sha256=digest, expected_byte_size=len(data))
    service.upload_stream(upload.upload_id, owner, io.BytesIO(data))
    ref = service.finalize(upload.upload_id, owner, reported_sha256=digest)
    reader = identity('reader', 'other-team')
    with pytest.raises(a.ArtifactAuthorizationError):
        service.read(ref, reader, maximum=1024)
    # Only an explicit owning-domain share can expand download access.
    with patch.dict(a._shared_download_authorizers, {'craft': lambda record, who: who.actor.user_id == 'reader'}):
        assert service.read(ref, reader, maximum=1024) == data
        with pytest.raises(a.ArtifactAuthorizationError):
            service.read(ref, identity('external', role='external'), maximum=1024)
        with pytest.raises(a.ArtifactAuthorizationError):
            service.upload_stream(upload.upload_id, reader, io.BytesIO(data))
        with pytest.raises(a.ArtifactIntegrityError):
            service.read(ref.model_copy(update={'sha256': '0' * 64}), reader, maximum=1024)


@pytest.mark.parametrize('field', ('process_flow_pic','process_chart_pic','cad_sim_pics'))
def test_all_existing_and_future_bop_images_share_automatically(monkeypatch, field):
    import json
    from urllib.parse import quote
    db = LocalDatabase()
    db.db.execute('ALTER TABLE workmanship_bop_bop_entries ADD COLUMN meta TEXT')
    db.db.execute('INSERT INTO workmanship_bop_bop_versions VALUES(?,?,?,?,?,?)', ('bop','owner','owner','old-team','personal',None))
    monkeypatch.setattr(pictures, 'get_craft_conn', lambda: db)
    monkeypatch.setattr(pictures, 'get_active_identity_profile', lambda gid: None if gid=='inactive' else {'org_role': 'external' if gid=='external' else 'member'})
    service = a.ArtifactService(a.InMemoryArtifactStore(), a.InMemoryObjectStorage())
    monkeypatch.setattr('backend.platform_sdk.artifacts.artifact_service', lambda: service)
    owner = identity('owner', 'old-team')
    data = b'\x89PNG\r\n\x1a\nfixture'
    digest = hashlib.sha256(data).hexdigest()
    session = service.create_upload(owner, media_type='image/png', expected_sha256=digest, expected_byte_size=len(data))
    service.upload_stream(session.upload_id, owner, io.BytesIO(data))
    ref = service.finalize(session.upload_id, owner, reported_sha256=digest)
    record = service.authorize_download(ref.artifact_id, owner)
    url = 'artifact:'+quote(json.dumps(ref.model_dump(mode='json')),safe='')+'/photo.png'
    photo = {'url':url,'storage':'artifact','object_key':''}
    reader = identity('reader','new-team')
    # No per-file sharing table or registration exists in this database.
    with patch.dict(a._shared_download_authorizers, {'craft':pictures.authorize_shared_picture}):
        with pytest.raises(a.ArtifactAuthorizationError): service.read(ref,reader,maximum=1024)
        reader_context=SimpleNamespace(user_gid='reader',team_gid='new-team',active_roles=('member',))
        with pytest.raises(a.ArtifactAuthorizationError): pictures.validate_picture_updates({field:[photo]},reader_context)
        pictures.validate_picture_updates({field:[photo]},SimpleNamespace(user_gid='owner',team_gid='old-team',active_roles=('member',)))
        flow=json.dumps([photo]) if field=='process_flow_pic' else '[]'
        chart=json.dumps([photo]) if field=='process_chart_pic' else '[]'
        meta=json.dumps({'cad_sim_pics':[photo]}) if field=='cad_sim_pics' else '{}'
        db.db.execute('INSERT INTO workmanship_bop_bop_entries VALUES(?,?,?,?,?)',('bop',flow,chart,0,meta))
        # A single persisted BOP reference enables every active member, across
        # teams, independently of uploader/team history and version visibility.
        assert service.read(ref,reader,maximum=1024)==data
        pictures.validate_picture_updates({field:[photo]},reader_context)
        for user in ('external','inactive'):
            with pytest.raises(a.ArtifactAuthorizationError): service.read(ref,identity(user,'new-team'),maximum=1024)
        with pytest.raises(a.ArtifactIntegrityError): service.read(ref.model_copy(update={'sha256':'0'*64}),reader,maximum=1024)
        db.db.execute('UPDATE workmanship_bop_bop_entries SET is_deleted=1')
        with pytest.raises(a.ArtifactAuthorizationError): service.read(ref,reader,maximum=1024)


def test_historical_bop_pictures_are_visible_to_members_across_teams(monkeypatch):
    import json
    from plugins.craft.craft_backend.capabilities.desktop_pictures import list_picture_access
    from backend.platform_sdk.historical_artifacts import redeem_picture_grant
    db = LocalDatabase()
    image = b'\x89PNG\r\n\x1a\nfixture'
    db.db.execute('UPDATE workmanship_auth_users SET team_id=? WHERE gid=?', ('old-team','owner'))
    db.db.execute('INSERT INTO workmanship_bop_bop_versions VALUES(?,?,?,?,?,?)', ('bop','owner','owner','old-team','personal',None))
    photo = {'storage':'ois','object_key':'owned/photo.png','mime':'image/png'}
    db.db.execute('INSERT INTO workmanship_bop_bop_entries VALUES(?,?,?,?)', ('bop',json.dumps([photo]),'[]',0))
    trust_fixture_upload(db,'ois','owned/photo.png',image,'image/png',[{'owner_domain':'craft','parent_type':'bop_version','parent_gid':'bop'}],tenant='old-team')
    db.db.execute('INSERT INTO workmanship_auth_users VALUES(?,?,?,?,?,?)', ('reader','Reader','','new-team',1,'member'))
    monkeypatch.setattr('backend.platform_sdk.identity.get_conn', lambda: db)
    monkeypatch.setattr('backend.platform_sdk.historical_artifacts.get_conn', lambda: db)
    monkeypatch.setattr('plugins.craft.craft_backend.capabilities.desktop_pictures.get_craft_conn', lambda: db)
    monkeypatch.setattr('backend.core.ois_storage.generate_access_urls', lambda *a,**kw: {})
    monkeypatch.setattr('backend.platform_sdk.historical_artifacts.get_settings', lambda: SimpleNamespace(jwt_secret='member-picture-secret-at-least-32-characters'))
    reader = SimpleNamespace(user_gid='reader',team_gid='new-team',active_roles=('member',))
    result = list_picture_access({'version_gid':'bop'},reader)
    assert len(result['items']) == 1
    assert redeem_picture_grant(result['items'][0]['access_grant'],'reader','new-team')['object_key'] == 'owned/photo.png'
    with pytest.raises(Exception):
        redeem_picture_grant(result['items'][0]['access_grant'],'different-reader','new-team')
