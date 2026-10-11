from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from backend.routers import intro_videos as videos
from backend.routers.deps import get_current_user

@pytest.fixture
def setup(monkeypatch):
    metadata, objects = {}, {}
    monkeypatch.setattr(videos, "_metadata", lambda key: metadata.get(key))
    monkeypatch.setattr(videos, "_save", lambda key, value: metadata.update({key:value}))
    monkeypatch.setattr(videos.ois_storage, "is_enabled", lambda: True)
    def cloud_upload(key, stream):
        stream.seek(0); objects[key] = stream.read(); return key
    monkeypatch.setattr(videos.ois_storage, "put_immutable_stream", cloud_upload)
    monkeypatch.setattr(videos.ois_storage, "generate_access_url", lambda key, expire_in_seconds: "https://ois.example.com/"+key+"?expires=3600")
    app=FastAPI();app.include_router(videos.router)
    user={"gid":"user-1","org_role":"member"}
    app.dependency_overrides[get_current_user]=lambda:user
    return TestClient(app), user, metadata, objects

CONTENT=b"\0\0\0\x18ftypmp42"+b"0"*100

def test_super_admin_uploads_to_ois_and_cases_remain_independent(setup):
    client,user,metadata,objects=setup
    assert client.put("/api/intro-videos/craft",content=CONTENT,headers={"content-type":"video/mp4"}).status_code==403
    assert not objects
    user["org_role"]="super_admin"
    assert client.put("/api/intro-videos/craft",content=CONTENT,headers={"content-type":"video/mp4"}).status_code==200
    assert set(metadata)=={"craft"}
    value=metadata["craft"]
    assert value["storage"]=="ois" and "file" not in value and "url" not in value
    assert objects[value["object_key"]]==CONTENT
    response=client.get("/api/intro-videos/craft/content",follow_redirects=False)
    assert response.status_code==307
    assert response.headers["location"].startswith("https://ois.example.com/platform-intro/videos/craft/")
    assert client.get("/api/intro-videos/simulation/content").status_code==404

def test_unconfigured_or_failed_ois_does_not_fallback_to_local_storage(setup,monkeypatch):
    client,user,metadata,objects=setup
    user["org_role"]="super_admin"
    monkeypatch.setattr(videos.ois_storage,"is_enabled",lambda:False)
    assert client.put("/api/intro-videos/craft",content=CONTENT,headers={"content-type":"video/mp4"}).status_code==503
    monkeypatch.setattr(videos.ois_storage,"is_enabled",lambda:True)
    monkeypatch.setattr(videos.ois_storage,"put_immutable_stream",lambda *args:None)
    assert client.put("/api/intro-videos/craft",content=CONTENT,headers={"content-type":"video/mp4"}).status_code==502
    assert not metadata and not objects

def test_invalid_upload_or_failed_binding_preserves_previous_video(setup,monkeypatch):
    client,user,metadata,objects=setup
    user["org_role"]="super_admin"
    assert client.put("/api/intro-videos/craft",content=CONTENT,headers={"content-type":"video/mp4"}).status_code==200
    old=dict(metadata["craft"])
    assert client.put("/api/intro-videos/craft",content=b"not video",headers={"content-type":"video/mp4"}).status_code==415
    def fail(*args):raise RuntimeError("save failed")
    monkeypatch.setattr(videos,"_save",fail)
    with pytest.raises(RuntimeError,match="save failed"):
        client.put("/api/intro-videos/craft",content=CONTENT,headers={"content-type":"video/mp4"})
    assert metadata["craft"]==old
    monkeypatch.setattr(videos,"MAX_BYTES",8)
    assert client.put("/api/intro-videos/craft",content=CONTENT,headers={"content-type":"video/mp4"}).status_code==413
