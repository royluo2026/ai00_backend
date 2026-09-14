"""Database-backed parsed product trees for imported immutable PLMXML documents."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .connection import get_simulation_conn


ALGORITHM_VERSION = "plmxml-product-tree.v1"


def dependency_signature(values: list[dict[str, Any]]) -> str:
    refs = sorted((str(item.get("location") or ""),
                   str((item.get("artifact_ref") or {}).get("sha256") or "").removeprefix("sha256:"))
                  for item in values)
    return hashlib.sha256(json.dumps(refs, separators=(",", ":")).encode()).hexdigest()


def _authorized_document(cursor, document_gid: str, ref: Mapping[str, Any], tenant_gid: str,
                         actor_gid: str) -> str:
    if not str(document_gid).isdigit() or not str(tenant_gid).isdigit() or not str(actor_gid).isdigit():
        raise ValueError("model_document_not_found")
    cursor.execute(
        "SELECT d.artifact_ref_json,d.content_sha256 FROM workmanship_sim_vm_documents d "
        "JOIN workmanship_sim_workspaces w ON w.gid=d.workspace_gid "
        "WHERE d.gid=%s AND d.tenant_gid=%s AND (w.owner_gid=%s OR w.visibility='shared') "
        "AND d.status='active' AND d.removed_at IS NULL AND w.removed_at IS NULL",
        (document_gid, tenant_gid, actor_gid),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("model_document_not_found")
    stored = row["artifact_ref_json"]
    stored = json.loads(stored) if isinstance(stored, str) else dict(stored or {})
    actual_sha = str(row["content_sha256"]).removeprefix("sha256:")
    if (str(ref.get("sha256") or "").removeprefix("sha256:") != actual_sha
            or str(ref.get("artifact_id") or "") != str(stored.get("artifact_id") or "")
            or str(ref.get("version") or "") != str(stored.get("version") or "")):
        raise ValueError("model_document_artifact_mismatch")
    return actual_sha


def read_product_tree(*, document_gid: str, artifact_ref: Mapping[str, Any], dependencies: list[dict[str, Any]],
                      tenant_gid: str, actor_gid: str) -> dict[str, Any] | None:
    with get_simulation_conn() as conn, conn.cursor() as cursor:
        sha = _authorized_document(cursor, document_gid, artifact_ref, tenant_gid, actor_gid)
        cursor.execute(
            "SELECT payload_json,source_sha256 FROM workmanship_sim_plmxml_product_tree_cache "
            "WHERE document_gid=%s AND dependency_signature=%s AND algorithm_version=%s",
            (document_gid, dependency_signature(dependencies), ALGORITHM_VERSION),
        )
        row = cursor.fetchone()
    if not row or str(row["source_sha256"]) != sha:
        return None
    value = row["payload_json"]
    return json.loads(value) if isinstance(value, str) else dict(value)


def save_product_tree(*, document_gid: str, artifact_ref: Mapping[str, Any], dependencies: list[dict[str, Any]],
                      tenant_gid: str, actor_gid: str, tree: Mapping[str, Any]) -> None:
    with get_simulation_conn() as conn, conn.cursor() as cursor:
        sha = _authorized_document(cursor, document_gid, artifact_ref, tenant_gid, actor_gid)
        cursor.execute(
            "INSERT INTO workmanship_sim_plmxml_product_tree_cache "
            "(document_gid,dependency_signature,algorithm_version,source_sha256,payload_json) "
            "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json),"
            "source_sha256=VALUES(source_sha256)",
            (document_gid, dependency_signature(dependencies), ALGORITHM_VERSION, sha,
             json.dumps(dict(tree), ensure_ascii=False, separators=(",", ":"))),
        )
