from __future__ import annotations

from plugins.knowledge.knowledge_backend.application.publication import KnowledgePublicationService


class UnitOfWork:
    def __init__(self):
        self.revisions = {}
        self.outbox = []
        self.committed = False

    def publish(self, *, document_gid, expected_revision, actor_gid):
        revision = {"gid": "rev-4", "document_gid": document_gid, "revision_no": 4, "immutable": True}
        event = {"event_type": "knowledge.document.published.v1", "subject_ref": document_gid, "revision_ref": revision["gid"]}
        self.revisions[revision["gid"]] = revision
        self.outbox.append(event)
        self.committed = True
        return revision, event


def test_publish_writes_immutable_revision_and_outbox_atomically():
    uow = UnitOfWork()
    result = KnowledgePublicationService(uow).publish(document_gid="doc-1", expected_revision=3, actor_gid="user-1")

    assert uow.committed is True
    assert uow.revisions[result["revision_ref"]]["immutable"] is True
    assert uow.outbox[0]["event_type"] == "knowledge.document.published.v1"
    assert uow.outbox[0]["subject_ref"] == "doc-1"

