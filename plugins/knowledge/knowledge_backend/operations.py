"""Knowledge-owned implementation of the public operations port."""
from __future__ import annotations

from typing import Any


class KnowledgeOperationsProvider:
    owner = "knowledge"

    def health(self, _context: object) -> dict[str, Any]:
        from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn

        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, COUNT(*) AS count "
                    "FROM workmanship_know_publish_outbox GROUP BY status"
                )
                counts = {str(row["status"]): int(row["count"]) for row in cur.fetchall()}
        return {"outbox_counts": counts}


__all__ = ["KnowledgeOperationsProvider"]
