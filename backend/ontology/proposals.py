"""Append-only ontology change proposals and revisions."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping, Sequence

from backend.ontology.canonical import canonical_json_bytes

ALLOWED_OPERATIONS = frozenset(
    {f"{kind}.{action}" for kind in ("concept", "property", "relation", "mapping", "constraint") for action in ("add", "change", "deprecate")}
    | {"parent.change"}
)
REVIEW_DECISIONS = frozenset({"approve", "reject", "request_changes"})


def normalize_changes(changes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(changes, bytes | str) or not isinstance(changes, Sequence) or not changes:
        raise ValueError("changes must be a non-empty array")
    result = []
    identities = set()
    for raw in changes:
        if not isinstance(raw, Mapping):
            raise ValueError("each change must be an object")
        operation = str(raw.get("operation") or "").strip().lower()
        stable_gid = str(raw.get("stable_gid") or "").strip()
        value = raw.get("value")
        if operation not in ALLOWED_OPERATIONS:
            raise ValueError(f"unsupported ontology change operation: {operation or '<empty>'}")
        if not stable_gid or not isinstance(value, Mapping):
            raise ValueError("stable_gid and value object are required for each operation")
        identity = (operation, stable_gid)
        if identity in identities:
            raise ValueError(f"duplicate change operation: {operation}/{stable_gid}")
        identities.add(identity)
        result.append({
            "operation": operation,
            "stable_gid": stable_gid,
            "value": dict(value),
            "source_evidence": list(raw.get("source_evidence") or []),
        })
    result.sort(key=lambda item: (item["operation"], item["stable_gid"]))
    return result


def proposal_revision_content(base_release_gid: str, changes: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], bytes, str]:
    normalized = normalize_changes(changes)
    content = {"base_release_gid": base_release_gid, "changes": normalized}
    data = canonical_json_bytes(content)
    import hashlib
    return content, data, hashlib.sha256(data).hexdigest()


@contextmanager
def _open(factory: Callable[[], Any]) -> Iterator[Any]:
    candidate = factory()
    if hasattr(candidate, "__enter__"):
        with candidate as conn:
            yield conn
    else:
        yield candidate


class ProposalConflict(RuntimeError):
    pass


class ProposalIntegrityError(RuntimeError):
    pass


class OntologyProposalRepository:
    def __init__(self, connection_factory: Callable[[], Any] | None = None):
        if connection_factory is None:
            from backend.db.connection import get_conn
            connection_factory = get_conn
        self._connection_factory = connection_factory

    def get_active(self) -> dict[str, Any] | None:
        from backend.ontology.repository import OntologyReleaseRepository
        return OntologyReleaseRepository(self._connection_factory).get_active("default")

    def create(
        self, *, proposal_gid: str, revision_gid: str, base_release_gid: str,
        changes: Sequence[Mapping[str, Any]], author_gid: str, channel: str,
    ) -> dict[str, Any]:
        content, _data, digest = proposal_revision_content(base_release_gid, changes)
        with _open(self._connection_factory) as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT release_gid FROM workmanship_base_ontology_active_refs WHERE ref_name='default' FOR UPDATE"
                    )
                    active = cursor.fetchone()
                    current = str(active["release_gid"]) if active else None
                    if current != base_release_gid:
                        raise ProposalConflict(f"base release changed: expected {base_release_gid!r}, current {current!r}")
                    cursor.execute(
                        "INSERT INTO workmanship_base_ontology_change_proposals "
                        "(gid,base_release_gid,status,author_gid,channel) VALUES (%s,%s,'review',%s,%s)",
                        (proposal_gid, base_release_gid, author_gid, channel[:32]),
                    )
                    cursor.execute(
                        "INSERT INTO workmanship_base_ontology_proposal_revisions "
                        "(gid,proposal_gid,revision_no,content_sha256,changes_json,evidence_json,created_by) "
                        "VALUES (%s,%s,1,%s,%s,%s,%s)",
                        (
                            revision_gid, proposal_gid, digest,
                            json.dumps(content["changes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            json.dumps([e for item in content["changes"] for e in item["source_evidence"]], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            author_gid,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "proposal_gid": proposal_gid, "proposal_revision_gid": revision_gid,
            "revision_no": 1, "base_release_gid": base_release_gid,
            "content_sha256": digest, "changes": content["changes"],
            "status": "review", "author_gid": author_gid,
        }

    def append_revision(
        self, *, proposal_gid: str, revision_gid: str,
        changes: Sequence[Mapping[str, Any]], author_gid: str,
    ) -> dict[str, Any]:
        with _open(self._connection_factory) as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT p.base_release_gid,p.status,p.author_gid,r.revision_no "
                        "FROM workmanship_base_ontology_change_proposals p "
                        "JOIN workmanship_base_ontology_proposal_revisions r ON r.proposal_gid=p.gid "
                        "WHERE p.gid=%s ORDER BY r.revision_no DESC LIMIT 1 FOR UPDATE",
                        (proposal_gid,),
                    )
                    proposal = cursor.fetchone()
                    if not proposal or str(proposal["author_gid"]) != author_gid:
                        raise ProposalConflict("only the proposal author can append a revision")
                    if str(proposal["status"]) != "changes_requested":
                        raise ProposalConflict("a new revision is accepted only after request_changes")
                    base_release_gid = str(proposal["base_release_gid"])
                    content, _data, digest = proposal_revision_content(base_release_gid, changes)
                    revision_no = int(proposal["revision_no"]) + 1
                    cursor.execute(
                        "INSERT INTO workmanship_base_ontology_proposal_revisions "
                        "(gid,proposal_gid,revision_no,content_sha256,changes_json,evidence_json,created_by) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (
                            revision_gid, proposal_gid, revision_no, digest,
                            json.dumps(content["changes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            json.dumps([e for item in content["changes"] for e in item["source_evidence"]], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            author_gid,
                        ),
                    )
                    cursor.execute(
                        "UPDATE workmanship_base_ontology_change_proposals SET status='review',updated_at=NOW() WHERE gid=%s",
                        (proposal_gid,),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "proposal_gid": proposal_gid, "proposal_revision_gid": revision_gid,
            "revision_no": revision_no, "base_release_gid": base_release_gid,
            "content_sha256": digest, "changes": content["changes"],
            "status": "review", "author_gid": author_gid,
        }
    def get(self, proposal_gid: str) -> dict[str, Any] | None:
        with _open(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT p.gid AS proposal_gid,p.base_release_gid,p.status,p.author_gid,p.channel,"
                    "r.gid AS proposal_revision_gid,r.revision_no,r.content_sha256,r.changes_json,r.created_at "
                    "FROM workmanship_base_ontology_change_proposals p "
                    "JOIN workmanship_base_ontology_proposal_revisions r ON r.proposal_gid=p.gid "
                    "WHERE p.gid=%s ORDER BY r.revision_no DESC LIMIT 1",
                    (proposal_gid,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        raw = result.get("changes_json")
        result["changes"] = json.loads(raw) if isinstance(raw, str) else raw
        result.pop("changes_json", None)
        return result

    def search(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE p.status=%s"
            params.append(status)
        params.append(max(1, min(limit, 100)))
        with _open(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT p.gid AS proposal_gid,p.base_release_gid,p.status,p.author_gid,p.channel,p.updated_at "
                    "FROM workmanship_base_ontology_change_proposals p " + where +
                    " ORDER BY p.updated_at DESC LIMIT %s",
                    tuple(params),
                )
                return [dict(row) for row in cursor.fetchall()]

    def list_reviews(self, proposal_gid: str, proposal_revision_gid: str) -> list[dict[str, Any]]:
        with _open(self._connection_factory) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid AS review_gid,proposal_gid,proposal_revision_gid,content_sha256,decision,reviewer_gid,comment,created_at "
                    "FROM workmanship_base_ontology_proposal_reviews "
                    "WHERE proposal_gid=%s AND proposal_revision_gid=%s ORDER BY created_at",
                    (proposal_gid, proposal_revision_gid),
                )
                return [dict(row) for row in cursor.fetchall()]
    def save_review(
        self, *, review_gid: str, proposal_gid: str, proposal_revision_gid: str,
        content_sha256: str, decision: str, reviewer_gid: str, comment: str | None,
    ) -> dict[str, Any]:
        if decision not in REVIEW_DECISIONS:
            raise ValueError("invalid review decision")
        with _open(self._connection_factory) as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT p.status,p.author_gid,r.gid AS proposal_revision_gid,r.content_sha256 "
                        "FROM workmanship_base_ontology_change_proposals p "
                        "JOIN workmanship_base_ontology_proposal_revisions r ON r.proposal_gid=p.gid "
                        "WHERE p.gid=%s ORDER BY r.revision_no DESC LIMIT 1 FOR UPDATE",
                        (proposal_gid,),
                    )
                    current = cursor.fetchone()
                    if not current or str(current["proposal_revision_gid"]) != proposal_revision_gid or str(current["content_sha256"]) != content_sha256:
                        raise ProposalIntegrityError("review must bind the current immutable proposal revision and hash")
                    if str(current["status"]) == "changes_requested" and decision == "approve":
                        raise ProposalConflict("request_changes requires a new proposal revision before approval")
                    cursor.execute(
                        "INSERT INTO workmanship_base_ontology_proposal_reviews "
                        "(gid,proposal_gid,proposal_revision_gid,content_sha256,decision,reviewer_gid,comment) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (review_gid, proposal_gid, proposal_revision_gid, content_sha256, decision, reviewer_gid, comment),
                    )
                    next_status = {"approve": "review", "reject": "rejected", "request_changes": "changes_requested"}[decision]
                    cursor.execute(
                        "UPDATE workmanship_base_ontology_change_proposals SET status=%s,updated_at=NOW() WHERE gid=%s",
                        (next_status, proposal_gid),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "review_gid": review_gid, "proposal_gid": proposal_gid,
            "proposal_revision_gid": proposal_revision_gid, "content_sha256": content_sha256,
            "decision": decision, "reviewer_gid": reviewer_gid,
        }
