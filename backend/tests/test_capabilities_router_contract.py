from backend.routers.capabilities import InvokeRequest


def test_web_invoke_transport_preserves_reliability_and_concurrency_fields():
    body = InvokeRequest.model_validate({
        "payload": {"document_gid": "doc_1", "base_revision_gid": "rev_1"},
        "version": 1,
        "confirmation_token": "approval_1",
        "idempotency_key": "idem_1",
        "expected_resource_version": "rev_1",
    })

    assert body.idempotency_key == "idem_1"
    assert body.expected_resource_version == "rev_1"
