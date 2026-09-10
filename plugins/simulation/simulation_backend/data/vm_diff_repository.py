"""Immutable VM difference report persistence."""
from __future__ import annotations

import json
from collections.abc import Callable

from backend.platform_sdk.ids import next_gid

from .connection import get_simulation_conn
from ..domain.vm_identity import VmObservation


class VmDiffRepositoryError(RuntimeError):
    pass


def _gid(value, field="gid"):
    text = str(value or "")
    if not text.isdecimal() or int(text) <= 0:
        raise VmDiffRepositoryError(f"{field}_invalid")
    return text


def _report(row):
    value = dict(row)
    value["report_gid"] = str(value.pop("gid"))
    for field in ("workspace_gid", "before_snapshot_gid", "after_snapshot_gid"):
        value[field] = str(value[field])
    raw = value.pop("summary_json")
    value["summary"] = json.loads(raw) if isinstance(raw, str) else raw
    value["row_version"] = int(value["row_version"])
    for field in ("created_at", "archived_at"):
        if value.get(field) is not None and not isinstance(value[field], str): value[field] = value[field].isoformat()
    return value


class VmDiffRepository:
    def __init__(self, connection_factory: Callable = get_simulation_conn, *, gid_factory=next_gid):
        self._connection_factory, self._gid_factory = connection_factory, gid_factory

    def load_checkpoint_snapshot(self, checkpoint_gid, *, tenant_gid, created_by):
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.snapshot_gid,c.workspace_gid,o.gid occurrence_gid,o.kind,o.model_number,"
                "v.source_instance_id,v.bom_line,v.revision_code,v.catia_occurrence_name,v.parent_path_json,"
                "v.normalized_transform_json,v.raw_transform_json,v.representation_locations_json "
                "FROM workmanship_sim_vm_checkpoints c JOIN workmanship_sim_vm_snapshots s ON s.gid=c.snapshot_gid "
                "LEFT JOIN workmanship_sim_vm_observations v ON v.snapshot_gid=s.gid "
                "LEFT JOIN workmanship_sim_vm_occurrences o ON o.gid=v.occurrence_gid "
                "WHERE c.gid=%s AND c.tenant_gid=%s AND c.archived_at IS NULL "
                "AND (c.created_by=%s OR c.scope='shared_baseline') ORDER BY o.gid",
                (_gid(checkpoint_gid, "checkpoint_gid"), _gid(tenant_gid, "tenant_gid"), _gid(created_by, "created_by")),
            )
            rows = list(cursor.fetchall())
        if not rows: return None
        observations = []
        for row in rows:
            if row.get("occurrence_gid") is None: continue
            loads = lambda key: tuple(json.loads(row[key])) if isinstance(row.get(key), str) else tuple(row.get(key) or ())
            observations.append(VmObservation(occurrence_gid=str(row["occurrence_gid"]),
                source_instance_id=str(row["source_instance_id"]), session_gid="0", kind=str(row["kind"]),
                model_number=str(row["model_number"]), bom_line=str(row["bom_line"]), revision=str(row["revision_code"]),
                catia_occurrence_name=str(row["catia_occurrence_name"]), normalized_transform=loads("normalized_transform_json"),
                parent_path=loads("parent_path_json"), raw_transform=loads("raw_transform_json"),
                representation_locations=loads("representation_locations_json")))
        return {"snapshot_gid": str(rows[0]["snapshot_gid"]), "workspace_gid": str(rows[0]["workspace_gid"]),
                "observations": observations}

    def persist_report(self, *, workspace_gid, tenant_gid, created_by, before_snapshot_gid, after_snapshot_gid,
                       algorithm_version, report_kind, diff, idempotency_key):
        del idempotency_key
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT gid,workspace_gid,before_snapshot_gid,after_snapshot_gid,report_kind,algorithm_version,"
                "status,summary_json,row_version,created_at,archived_at FROM workmanship_sim_vm_diff_reports "
                "WHERE before_snapshot_gid=%s AND after_snapshot_gid=%s AND algorithm_version=%s FOR UPDATE",
                (_gid(before_snapshot_gid), _gid(after_snapshot_gid), algorithm_version))
            current = cursor.fetchone()
            if current: return _report(current)
            report_gid = _gid(self._gid_factory(), "report_gid")
            cursor.execute("INSERT INTO workmanship_sim_vm_diff_reports "
                "(gid,workspace_gid,tenant_gid,created_by,before_snapshot_gid,after_snapshot_gid,report_kind,algorithm_version,status,summary_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'completed',%s)",
                (report_gid, _gid(workspace_gid), _gid(tenant_gid), _gid(created_by), _gid(before_snapshot_gid),
                 _gid(after_snapshot_gid), report_kind, algorithm_version, json.dumps(diff.summary, sort_keys=True)))
            for sequence, item in enumerate(diff.items, 1):
                cursor.execute("INSERT INTO workmanship_sim_vm_diff_items "
                    "(gid,report_gid,sequence,change_type,before_occurrence_gid,after_occurrence_gid,severity,payload_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (_gid(self._gid_factory()), report_gid, sequence,
                    item.change_type, item.before_occurrence_gid, item.after_occurrence_gid, item.severity,
                    json.dumps(item.payload, sort_keys=True, separators=(",", ":"))))
            cursor.execute("SELECT gid,workspace_gid,before_snapshot_gid,after_snapshot_gid,report_kind,algorithm_version,"
                "status,summary_json,row_version,created_at,archived_at FROM workmanship_sim_vm_diff_reports WHERE gid=%s", (report_gid,))
            return _report(cursor.fetchone())

    def get_report(self, report_gid, *, tenant_gid, created_by):
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT r.gid,r.workspace_gid,r.before_snapshot_gid,r.after_snapshot_gid,r.report_kind,r.algorithm_version,"
                "r.status,r.summary_json,r.row_version,r.created_at,r.archived_at FROM workmanship_sim_vm_diff_reports r "
                "JOIN workmanship_sim_vm_checkpoints b ON b.snapshot_gid=r.before_snapshot_gid "
                "JOIN workmanship_sim_vm_checkpoints a ON a.snapshot_gid=r.after_snapshot_gid "
                "WHERE r.gid=%s AND r.tenant_gid=%s AND (r.created_by=%s OR "
                "(b.scope='shared_baseline' AND a.scope='shared_baseline')) LIMIT 1",
                (_gid(report_gid, "report_gid"), _gid(tenant_gid, "tenant_gid"), _gid(created_by, "created_by")))
            row = cursor.fetchone()
        return _report(row) if row else None

    def search_items(self, report_gid, *, tenant_gid, created_by, offset, page_size):
        if not self.get_report(report_gid, tenant_gid=tenant_gid, created_by=created_by):
            raise VmDiffRepositoryError("vm_diff_report_not_found")
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT sequence,change_type,before_occurrence_gid,after_occurrence_gid,severity,payload_json "
                "FROM workmanship_sim_vm_diff_items WHERE report_gid=%s ORDER BY sequence LIMIT %s OFFSET %s",
                (_gid(report_gid, "report_gid"), page_size + 1, offset))
            rows = list(cursor.fetchall())
        more = len(rows) > page_size
        items = []
        for row in rows[:page_size]:
            value = dict(row); raw = value.pop("payload_json")
            value["payload"] = json.loads(raw) if isinstance(raw, str) else raw
            for field in ("before_occurrence_gid", "after_occurrence_gid"):
                if value.get(field) is not None: value[field] = str(value[field])
            items.append(value)
        return {"items": items, "next_cursor": str(offset + page_size) if more else None}

    def can_read(self, report_gid, *, tenant_gid, created_by):
        return self.get_report(report_gid, tenant_gid=tenant_gid, created_by=created_by) is not None

    def compact_automatic_reports_for_snapshot(self, snapshot_gid, *, tenant_gid, owner_gid):
        del owner_gid
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT gid FROM workmanship_sim_vm_diff_reports WHERE tenant_gid=%s "
                "AND report_kind='automatic' AND compacted_at IS NULL "
                "AND (before_snapshot_gid=%s OR after_snapshot_gid=%s) FOR UPDATE",
                (_gid(tenant_gid, "tenant_gid"), _gid(snapshot_gid, "snapshot_gid"), _gid(snapshot_gid, "snapshot_gid")))
            report_gids = [str(row["gid"]) for row in cursor.fetchall()]
            for report_gid in report_gids:
                cursor.execute("DELETE FROM workmanship_sim_vm_diff_items WHERE report_gid=%s", (report_gid,))
                cursor.execute("UPDATE workmanship_sim_vm_diff_reports SET compacted_at=NOW(6),row_version=row_version+1 "
                               "WHERE gid=%s AND compacted_at IS NULL", (report_gid,))
            return len(report_gids)


repository = VmDiffRepository()

__all__ = ["VmDiffRepository", "VmDiffRepositoryError", "repository"]
