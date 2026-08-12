"""Application service requiring one atomic revision-and-outbox unit of work."""
from __future__ import annotations


class KnowledgePublicationService:
    def __init__(self, unit_of_work):
        self.unit_of_work = unit_of_work

    def publish(self, *, document_gid: str, expected_revision: int, actor_gid: str) -> dict:
        revision, event = self.unit_of_work.publish(
            document_gid=document_gid,
            expected_revision=expected_revision,
            actor_gid=actor_gid,
        )
        return {
            "document_ref": f"knowledge-document:{document_gid}",
            "revision_ref": revision["gid"],
            "event_type": event["event_type"],
        }

