from fastapi.testclient import TestClient

from backend.main import app
from backend.base.self_annotations import SelfAnnotationService
from backend.routers.deps import get_current_user
from backend.tests.test_base_self_annotation_service import ATTACHMENT, FakeAnnotationRepository, FakeAttachmentVisibilityPort


def _user():
    return {"gid": "user_owner", "team_id": "tenant_1", "is_active": True}


def test_annotation_rest_write_rejects_unknown_top_level_and_attachment_keys_before_service():
    app.dependency_overrides[get_current_user] = _user
    try:
        client = TestClient(app)
        try:
            common = {"expected_revision": 1, "status": "open", "schedule": None, "note": "", "attachments": [], "idempotency_key": "idem-1"}
            assert client.put("/api/self_ann/item_1", json={**common, "unknown": True}).status_code == 422
            attachment = {"attachment_gid": "att_1", "media_type": "image/png", "display_name": "a.png", "size": 1, "checksum": "sha256:" + "a" * 64, "token": "no"}
            assert client.put("/api/self_ann/item_1", json={**common, "attachments": [attachment]}).status_code == 422
        finally:
            client.close()
    finally:
        app.dependency_overrides.clear()


def test_rest_annotation_attachment_registry_allows_owner_and_denies_unregistered(monkeypatch):
    def service(allowed: bool):
        return SelfAnnotationService(
            repository=FakeAnnotationRepository(),
            visibility_port=FakeAttachmentVisibilityPort({("user_owner", "tenant_1", "att_1")} if allowed else set()),
        )

    body = {"expected_revision": 1, "status": "open", "schedule": None, "note": "", "attachments": [ATTACHMENT], "idempotency_key": "idem-route"}
    app.dependency_overrides[get_current_user] = _user
    try:
        monkeypatch.setattr("backend.routers.self_annotations._service", lambda: service(True))
        client = TestClient(app)
        try:
            assert client.put("/api/self_ann/item_1", json=body).status_code == 200
        finally:
            client.close()
        monkeypatch.setattr("backend.routers.self_annotations._service", lambda: service(False))
        client = TestClient(app)
        try:
            assert client.put("/api/self_ann/item_1", json={**body, "idempotency_key": "idem-denied"}).status_code == 403
        finally:
            client.close()
    finally:
        app.dependency_overrides.clear()


def test_gateway_annotation_attachment_registry_allows_owner_and_denies_unregistered(monkeypatch):
    from backend.base import web_atomic
    from backend.capability_v2.provider_contracts import CapabilityBusinessError

    command = {"item_gid": "item_1", "expected_revision": 1, "status": "open", "schedule": None, "note": "", "attachments": [ATTACHMENT], "idempotency_key": "idem-gateway"}
    context = type("Context", (), {"user_gid": "user_owner", "team_gid": "tenant_1", "active_roles": ("member",)})()
    allowed = SelfAnnotationService(repository=FakeAnnotationRepository(), visibility_port=FakeAttachmentVisibilityPort({("user_owner", "tenant_1", "att_1")}))
    monkeypatch.setattr("backend.base.self_annotations.SelfAnnotationService", lambda: allowed)
    assert web_atomic._annotation_change(command, context)["annotation"]["attachments"] == [ATTACHMENT]
    denied = SelfAnnotationService(repository=FakeAnnotationRepository(), visibility_port=FakeAttachmentVisibilityPort(set()))
    monkeypatch.setattr("backend.base.self_annotations.SelfAnnotationService", lambda: denied)
    with __import__("pytest").raises(CapabilityBusinessError) as caught:
        web_atomic._annotation_change({**command, "idempotency_key": "idem-gateway-denied"}, context)
    assert caught.value.code == "attachment_not_visible"


def test_rest_and_gateway_batch_delegate_to_the_same_owner_service_method(monkeypatch):
    from backend.base import web_atomic
    from backend.routers import self_annotations as routes

    calls = []

    class BatchService:
        def batch(self, *, actor, item_gids):
            calls.append((actor["gid"], tuple(item_gids)))
            return {"items": [{"item_gid": "item_1", "status": "open", "schedule": "", "has_note": False, "attach_count": 0}]}

    service = BatchService()
    monkeypatch.setattr(routes, "_service", lambda: service)
    monkeypatch.setattr("backend.base.self_annotations.SelfAnnotationService", lambda: service)

    rest = routes.get_batch(gids="item_1", user={"gid": "user_owner", "team_id": "tenant_1"})
    context = type("Context", (), {"user_gid": "user_owner", "team_gid": "tenant_1", "active_roles": ("member",)})()
    gateway = web_atomic._annotation_batch({"item_gids": ["item_1"]}, context)

    assert rest == {"item_1": {"status": "open", "schedule": "", "has_note": False, "attach_count": 0}}
    assert gateway == {"items": [{"item_gid": "item_1", "status": "open", "schedule": "", "has_note": False, "attach_count": 0}]}
    assert calls == [("user_owner", ("item_1",)), ("user_owner", ("item_1",))]
