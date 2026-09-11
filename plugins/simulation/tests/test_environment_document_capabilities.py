from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityBusinessError
from plugins.simulation.simulation_backend.capabilities.environment_documents import EnvironmentDocumentProvider, specs


class _Repo:
    def __init__(self): self.calls = []
    def search_model_documents(self, **kwargs):
        self.calls.append(("search", kwargs)); return {"items": []}
    def add_model_document(self, **kwargs):
        self.calls.append(("add", kwargs)); return {"document_gid": "9", "workspace_gid": kwargs["workspace_gid"], "role": kwargs["document"]["role"], "row_version": 1, "workspace_row_version": 2, "cache_revision_hash": "sha256:" + "0" * 64}
    def remove_model_document(self, **kwargs):
        self.calls.append(("remove", kwargs)); return {"document_gid": kwargs["document_gid"], "workspace_gid": kwargs["workspace_gid"], "removed": True, "workspace_row_version": 2, "cache_revision_hash": "sha256:" + "0" * 64}


def _context(): return CapabilityContext(user_gid="30", team_gid="20", request_id="r1")


def test_document_capabilities_are_atomic_and_scoped():
    repo = _Repo(); provider = EnvironmentDocumentProvider(repo)
    payload = {"workspace_gid": "10", "expected_row_version": 1, "role": "primary", "display_name": "W10",
               "media_type": "application/plmxml+xml", "artifact_ref": {"artifact_id": "artifact_x"}, "source_kind": "artifact",
               "source_identity_hash": "sha256:" + "a" * 64, "content_sha256": "sha256:" + "b" * 64,
               "portability": "portable", "idempotency_key": "doc-1"}
    provider.add(payload, _context())
    provider.search({"workspace_gid": "10"}, _context())
    assert repo.calls[0][1]["tenant_gid"] == "20" and repo.calls[0][1]["actor_gid"] == "30"
    assert [item[0].id for item in specs(provider)] == [
        "simulation.environment.model_document.search",
        "simulation.environment.model_document.add",
        "simulation.environment.model_document.remove",
    ]


def test_document_provider_rejects_device_bound_artifact_without_device_identity():
    provider = EnvironmentDocumentProvider(_Repo())
    payload = {"workspace_gid": "10", "expected_row_version": 1, "role": "inserted", "display_name": "tool",
               "media_type": "model/vnd.jt", "artifact_ref": {"artifact_id": "artifact_x"}, "source_kind": "local_file",
               "source_identity_hash": "sha256:" + "a" * 64, "content_sha256": "sha256:" + "b" * 64,
               "portability": "device_bound", "idempotency_key": "doc-1"}
    try:
        provider.add(payload, _context())
    except CapabilityBusinessError as exc:
        assert "connector_device_id_required" in str(exc)
    else:
        raise AssertionError("device-bound document must carry a Connector device identity")
