"""Base-owned Inbox and search projection for published Knowledge documents."""
from __future__ import annotations

import json
import os
from pathlib import Path

from backend.capability_v2.domain_database import connect_domain_database, load_domain_database_url
from backend.capability_v2.domain_events import DomainEventEnvelope
from backend.capability_v2.domain_manifest import load_domain_manifests


def _base_connection():
    root = Path(__file__).resolve().parents[2]
    manifest = load_domain_manifests(root / "backend/capability_v2/official_domains.json").require("base")
    return connect_domain_database(load_domain_database_url(manifest, os.environ, role="runtime"))


class BaseInboxProjector:
    def __init__(self, connection_factory=None):
        self._connection_factory = connection_factory or _base_connection

    def handle(self, event: DomainEventEnvelope) -> bool:
        document_ref = str(event.payload["document_ref"])
        revision_ref = str(event.payload["revision_ref"])
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT IGNORE INTO workmanship_base_domain_inbox "
                    "(tenant_gid,event_id,event_type,event_version,producer_domain,envelope_json,status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'processing')",
                    (event.tenant_id, event.event_id, event.event_type, event.event_version,
                     event.producer_domain, json.dumps(event.model_dump(mode="json"), ensure_ascii=False)),
                )
                if cursor.rowcount == 0:
                    connection.rollback()
                    return False
                cursor.execute(
                    "INSERT INTO workmanship_base_search_projection "
                    "(tenant_gid,subject_ref,source_domain,source_version,revision_ref,updated_at) "
                    "VALUES (%s,%s,'knowledge',%s,%s,NOW(6)) ON DUPLICATE KEY UPDATE "
                    "source_version=VALUES(source_version),revision_ref=VALUES(revision_ref),updated_at=NOW(6)",
                    (event.tenant_id, document_ref, event.aggregate_version, revision_ref),
                )
                cursor.execute(
                    "UPDATE workmanship_base_domain_inbox SET status='completed',completed_at=NOW(6) "
                    "WHERE tenant_gid=%s AND event_id=%s",
                    (event.tenant_id, event.event_id),
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class MemoryBaseProjectionStore:
    """Deterministic transactional test store for the production projector contract."""
    def __init__(self, *, failures_before_success: int = 0):
        self._inbox: set[str] = set()
        self._projection: dict[str, dict] = {}
        self._failures = failures_before_success

    def handle(self, event: DomainEventEnvelope) -> bool:
        if event.event_id in self._inbox:
            return False
        if self._failures:
            self._failures -= 1
            raise RuntimeError("transient projection failure")
        self._inbox.add(event.event_id)
        self._projection[str(event.payload["document_ref"])] = dict(event.payload)
        return True

    def inbox_count(self, event_id: str) -> int:
        return int(event_id in self._inbox)

    def projection_count(self, *, subject_ref: str) -> int:
        return int(subject_ref in self._projection)


__all__ = ["BaseInboxProjector", "MemoryBaseProjectionStore"]
