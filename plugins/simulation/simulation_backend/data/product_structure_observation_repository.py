"""Append-only persistence for Teamcenter online structure observations."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable

from backend.platform_sdk.ids import next_gid

from ..domain.product_structure_observation import (
    GeometryReference, ObservationPage, OccurrenceRecord, SourceSelector,
    ProductStructureValidationError, validate_observation_pages,
)
from .connection import get_simulation_conn


class ProductStructureRepositoryError(RuntimeError):
    pass


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _gid(value: object, field: str) -> str:
    text = str(value or "")
    if not text.isdecimal() or int(text) <= 0:
        raise ProductStructureRepositoryError(f"{field}_invalid")
    return text


def _mysql_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError) as exc:
        raise ProductStructureRepositoryError(f"{field}_invalid") from exc


def _page_body(page: ObservationPage) -> dict:
    return {
        "cursor": page.cursor,
        "next_cursor": page.next_cursor,
        "nodes": [asdict(node) for node in page.nodes],
    }


def _node(value: dict) -> OccurrenceRecord:
    return OccurrenceRecord(**{
        **value,
        "transform": tuple(value["transform"]) if value.get("transform") is not None else None,
        "absolute_transform": tuple(value["absolute_transform"]) if value.get("absolute_transform") is not None else None,
        "bbox": tuple(value["bbox"]) if value.get("bbox") is not None else None,
        "geometry_refs": tuple(GeometryReference(**item) for item in value.get("geometry_refs", [])),
    })


class ProductStructureObservationRepository:
    def __init__(self, connection_factory: Callable = get_simulation_conn,
                 gid_factory: Callable[[], object] = next_gid):
        self._connect = connection_factory
        self._next_gid = gid_factory

    def register_online_source(self, *, workspace_gid: str, selector: SourceSelector,
                               display_name: str, expected_workspace_version: int,
                               actor_gid: str, tenant_gid: str,
                               insertion_instance_id: str) -> dict:
        workspace_gid = _gid(workspace_gid, "workspace_gid")
        actor_gid, tenant_gid = _gid(actor_gid, "actor_gid"), _gid(tenant_gid, "tenant_gid")
        if not isinstance(selector, SourceSelector):
            raise ProductStructureRepositoryError("source_selector_invalid")
        if not insertion_instance_id or len(insertion_instance_id) > 64:
            raise ProductStructureRepositoryError("insertion_instance_id_invalid")
        if len(display_name) > 512:
            raise ProductStructureRepositoryError("display_name_invalid")
        source_hash = selector.identity_hash[7:]
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT row_version,cache_revision_hash FROM workmanship_sim_workspaces WHERE gid=%s AND tenant_gid=%s "
                "AND owner_gid=%s AND removed_at IS NULL FOR UPDATE",
                (workspace_gid, tenant_gid, actor_gid),
            )
            workspace = cursor.fetchone()
            if not workspace:
                raise ProductStructureRepositoryError("workspace_not_found")
            cursor.execute(
                "SELECT gid,document_gid FROM workmanship_sim_online_model_sources WHERE workspace_gid=%s "
                "AND source_identity_hash=%s AND insertion_instance_id=%s",
                (workspace_gid, source_hash, insertion_instance_id),
            )
            existing = cursor.fetchone()
            if existing:
                return {"source_gid": str(existing["gid"]), "source_identity_hash": selector.identity_hash,
                        "insertion_instance_id": insertion_instance_id, "document_gid": str(existing["document_gid"]),
                        "workspace_row_version": int(workspace["row_version"]),
                        "cache_revision_hash": str(workspace["cache_revision_hash"])}
            if int(workspace["row_version"]) != int(expected_workspace_version):
                raise ProductStructureRepositoryError("version_conflict")
            source_gid = str(self._next_gid())
            document_gid = str(self._next_gid())
            document_hash = hashlib.sha256(f"{source_hash}\0{insertion_instance_id}".encode()).hexdigest()
            cursor.execute(
                "SELECT COUNT(*) AS count,COALESCE(MAX(sort_order),-1) AS max_order FROM workmanship_sim_vm_documents "
                "WHERE workspace_gid=%s AND removed_at IS NULL", (workspace_gid,),
            )
            position = cursor.fetchone() or {"count": 0, "max_order": -1}
            primary = int(position["count"]) == 0
            cursor.execute(
                "INSERT INTO workmanship_sim_vm_documents "
                "(gid,workspace_gid,tenant_gid,owner_gid,document_role,primary_slot,display_name,media_type,artifact_ref_json,"
                "content_sha256,portability,connector_device_id,sort_order,source_kind,source_identity_hash,status,row_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'device_bound',NULL,%s,'teamcenter_online',%s,'active',1)",
                (document_gid, workspace_gid, tenant_gid, actor_gid, "primary" if primary else "inserted",
                 1 if primary else None, display_name, "application/vnd.siemens.teamcenter.visualization-document",
                 _canonical({"source_selector": asdict(selector), "insertion_instance_id": insertion_instance_id}),
                 source_hash, int(position["max_order"]) + 1, document_hash),
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_online_model_sources "
                "(gid,tenant_gid,owner_gid,workspace_gid,document_gid,insertion_instance_id,source_identity_hash,endpoint_id,"
                "object_uid,item_revision_uid,bom_view_uid,revision_rule,configuration_date,display_name,source_selector_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (source_gid, tenant_gid, actor_gid, workspace_gid, document_gid, insertion_instance_id, source_hash,
                 selector.endpoint_id, selector.object_uid, selector.item_revision_uid or None,
                 selector.bom_view_uid or None, selector.revision_rule,
                 _mysql_datetime(selector.configuration_date, "configuration_date"),
                 display_name or None, _canonical(asdict(selector))),
            )
            next_version = int(workspace["row_version"]) + 1
            cache_hash = "sha256:" + hashlib.sha256(
                f"{workspace['cache_revision_hash']}|online_source:{source_gid}|{next_version}".encode()).hexdigest()
            cursor.execute("UPDATE workmanship_sim_workspaces SET row_version=%s,cache_revision_hash=%s WHERE gid=%s AND row_version=%s",
                           (next_version, cache_hash, workspace_gid, int(workspace["row_version"])))
            if cursor.rowcount != 1:
                raise ProductStructureRepositoryError("version_conflict")
        return {"source_gid": source_gid, "source_identity_hash": selector.identity_hash,
                "insertion_instance_id": insertion_instance_id, "document_gid": document_gid,
                "workspace_row_version": next_version, "cache_revision_hash": cache_hash}

    def begin_observation(self, *, source_gid: str, workspace_gid: str, tenant_gid: str,
                          actor_gid: str, observation_id: str, captured_at: str,
                          node_count: int, page_count: int) -> dict:
        source_gid, workspace_gid = _gid(source_gid, "source_gid"), _gid(workspace_gid, "workspace_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        if not observation_id.startswith("tcobs:") or len(observation_id) != 70:
            raise ProductStructureRepositoryError("observation_id_invalid")
        if not (1 <= int(node_count) <= 250_000 and 1 <= int(page_count) <= 250_000):
            raise ProductStructureRepositoryError("observation_size_invalid")
        manifest = {"observation_id": observation_id, "captured_at": captured_at,
                    "node_count": int(node_count), "page_count": int(page_count)}
        manifest_hash = _hash(manifest)
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT gid FROM workmanship_sim_online_model_sources WHERE gid=%s AND workspace_gid=%s "
                "AND tenant_gid=%s AND owner_gid=%s FOR UPDATE",
                (source_gid, workspace_gid, tenant_gid, actor_gid),
            )
            if not cursor.fetchone():
                raise ProductStructureRepositoryError("online_source_not_found")
            cursor.execute(
                "SELECT gid,manifest_hash FROM workmanship_sim_product_structure_observations "
                "WHERE tenant_gid=%s AND observation_id=%s",
                (tenant_gid, observation_id),
            )
            existing = cursor.fetchone()
            if existing:
                if str(existing["manifest_hash"]) != manifest_hash:
                    raise ProductStructureRepositoryError("observation_manifest_conflict")
                observation_gid = str(existing["gid"])
            else:
                observation_gid = str(self._next_gid())
                cursor.execute(
                    "INSERT INTO workmanship_sim_product_structure_observations "
                    "(gid,tenant_gid,workspace_gid,source_gid,observation_id,captured_at,node_count,page_count,complete,manifest_hash,schema_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,1)",
                    (observation_gid, tenant_gid, workspace_gid, source_gid, observation_id,
                     _mysql_datetime(captured_at, "captured_at"), int(node_count), int(page_count), manifest_hash),
                )
        return {"observation_gid": observation_gid, **manifest,
                "manifest_hash": "sha256:" + manifest_hash, "complete": False}

    def append_observation_page(self, observation_gid: str, page_index: int,
                                page: ObservationPage, *, tenant_gid: str,
                                actor_gid: str) -> dict:
        observation_gid = _gid(observation_gid, "observation_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        if type(page_index) is not int or page_index < 0 or not isinstance(page, ObservationPage):
            raise ProductStructureRepositoryError("observation_page_invalid")
        body = _page_body(page)
        page_hash = _hash(body)
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT o.complete,o.page_count FROM workmanship_sim_product_structure_observations o "
                "JOIN workmanship_sim_online_model_sources s ON s.gid=o.source_gid "
                "WHERE o.gid=%s AND o.tenant_gid=%s AND s.owner_gid=%s FOR UPDATE",
                (observation_gid, tenant_gid, actor_gid),
            )
            manifest = cursor.fetchone()
            if not manifest:
                raise ProductStructureRepositoryError("observation_not_found")
            if bool(manifest["complete"]):
                raise ProductStructureRepositoryError("observation_already_published")
            if page_index >= int(manifest["page_count"]):
                raise ProductStructureRepositoryError("observation_page_invalid")
            cursor.execute(
                "SELECT page_hash FROM workmanship_sim_product_structure_chunks WHERE observation_gid=%s AND page_index=%s",
                (observation_gid, page_index),
            )
            existing = cursor.fetchone()
            if existing:
                if str(existing["page_hash"]) != page_hash:
                    raise ProductStructureRepositoryError("observation_page_conflict")
                return {"page_hash": "sha256:" + page_hash, "replayed": True}
            cursor.execute(
                "INSERT INTO workmanship_sim_product_structure_chunks "
                "(observation_gid,page_index,cursor_value,node_count,payload_json,page_hash) VALUES (%s,%s,%s,%s,%s,%s)",
                (observation_gid, page_index, page.cursor, len(page.nodes), _canonical(body), page_hash),
            )
        return {"page_hash": "sha256:" + page_hash, "replayed": False}

    def publish_observation(self, observation_gid: str, *, tenant_gid: str,
                            actor_gid: str) -> dict:
        observation_gid = _gid(observation_gid, "observation_gid")
        tenant_gid, actor_gid = _gid(tenant_gid, "tenant_gid"), _gid(actor_gid, "actor_gid")
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT o.observation_id,o.node_count,o.page_count,o.complete FROM workmanship_sim_product_structure_observations o "
                "JOIN workmanship_sim_online_model_sources s ON s.gid=o.source_gid "
                "WHERE o.gid=%s AND o.tenant_gid=%s AND s.owner_gid=%s FOR UPDATE",
                (observation_gid, tenant_gid, actor_gid),
            )
            manifest = cursor.fetchone()
            if not manifest:
                raise ProductStructureRepositoryError("observation_not_found")
            cursor.execute(
                "SELECT page_index,payload_json FROM workmanship_sim_product_structure_chunks "
                "WHERE observation_gid=%s ORDER BY page_index", (observation_gid,),
            )
            rows = cursor.fetchall()
            if len(rows) != int(manifest["page_count"]):
                raise ProductStructureRepositoryError("observation_incomplete")
            pages = []
            for expected, row in enumerate(rows):
                if int(row["page_index"]) != expected:
                    raise ProductStructureRepositoryError("observation_incomplete")
                value = json.loads(row["payload_json"])
                pages.append(ObservationPage(value["cursor"], value["next_cursor"],
                                             tuple(_node(item) for item in value["nodes"])))
            try:
                validate_observation_pages(tuple(pages), int(manifest["node_count"]))
            except ProductStructureValidationError as error:
                raise ProductStructureRepositoryError(str(error)) from error
            if not bool(manifest["complete"]):
                cursor.execute(
                    "UPDATE workmanship_sim_product_structure_observations SET complete=1 WHERE gid=%s AND complete=0",
                    (observation_gid,),
                )
        return {"observation_id": str(manifest["observation_id"]), "complete": True,
                "node_count": int(manifest["node_count"]), "page_count": int(manifest["page_count"])}

    def get_observation_page(self, *, observation_id: str, tenant_gid: str,
                             actor_gid: str, cursor: int, page_size: int) -> dict:
        tenant_gid = _gid(tenant_gid, "tenant_gid")
        actor_gid = _gid(actor_gid, "actor_gid")
        if type(cursor) is not int or cursor < 0 or type(page_size) is not int or not 1 <= page_size <= 1000:
            raise ProductStructureRepositoryError("observation_page_request_invalid")
        with self._connect() as conn, conn.cursor() as db_cursor:
            db_cursor.execute(
                "SELECT o.gid,o.node_count FROM workmanship_sim_product_structure_observations o "
                "JOIN workmanship_sim_online_model_sources s ON s.gid=o.source_gid "
                "WHERE o.tenant_gid=%s AND o.observation_id=%s AND o.complete=1 AND s.owner_gid=%s",
                (tenant_gid, observation_id, actor_gid),
            )
            manifest = db_cursor.fetchone()
            if not manifest:
                raise ProductStructureRepositoryError("observation_not_found")
            db_cursor.execute(
                "SELECT page_index,cursor_value,payload_json FROM workmanship_sim_product_structure_chunks "
                "WHERE observation_gid=%s AND cursor_value<=%s ORDER BY cursor_value DESC LIMIT 1",
                (manifest["gid"], cursor),
            )
            row = db_cursor.fetchone()
            selected = []
            page_index = int(row["page_index"]) if row else 0
            while len(selected) < page_size:
                db_cursor.execute(
                    "SELECT page_index,cursor_value,payload_json FROM workmanship_sim_product_structure_chunks "
                    "WHERE observation_gid=%s AND page_index=%s LIMIT 1",
                    (manifest["gid"], page_index),
                )
                chunk = db_cursor.fetchone()
                if not chunk:
                    break
                value = json.loads(chunk["payload_json"])
                offset = max(0, cursor - int(chunk["cursor_value"]))
                selected.extend(value["nodes"][offset:offset + page_size - len(selected)])
                page_index += 1
        next_cursor = cursor + len(selected)
        return {"observation_id": observation_id, "cursor": cursor,
                "next_cursor": next_cursor if next_cursor < int(manifest["node_count"]) else None,
                "nodes": selected, "node_count": int(manifest["node_count"])}


__all__ = ["ProductStructureObservationRepository", "ProductStructureRepositoryError"]
