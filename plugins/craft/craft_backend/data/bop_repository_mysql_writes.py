"""Transactional write helpers kept separate from the repository query adapter."""
from __future__ import annotations

import hashlib
from typing import Any

from backend.platform_sdk.ids import next_gid

from .bop_repository import BopRepositoryError
from .bop_repository_mysql import _json


def save_space_version(store, *, space_gid, tenant_gid, actor_gid, expected_head_version,
                       version_kind, source_refs, algorithm_versions, idempotency_key):
    payload = {"space_gid": space_gid, "expected_head_version": expected_head_version,
               "version_kind": version_kind, "source_refs": source_refs,
               "algorithm_versions": algorithm_versions}
    if version_kind not in {"saved", "frozen", "fork_base", "proposal_base"}:
        raise BopRepositoryError("version_kind_invalid")
    with store._connect() as conn, conn.cursor() as cur:
        def effect():
            head = store._row(cur, "SELECT h.gid,h.row_version,h.content_hash,s.repository_gid FROM workmanship_craft_bop_space_heads h JOIN workmanship_craft_bop_spaces s ON s.gid=h.space_gid WHERE h.space_gid=%s AND h.tenant_gid=%s AND s.deleted_at IS NULL FOR UPDATE", (space_gid, tenant_gid), "space_not_found")
            if head["row_version"] != expected_head_version: raise BopRepositoryError("resource_version_conflict")
            vg = str(next_gid()); manifest = "sha256:" + hashlib.sha256(_json({"head":head["content_hash"],"source_refs":source_refs,"algorithm_versions":algorithm_versions}).encode()).hexdigest()
            cur.execute("INSERT INTO workmanship_craft_bop_space_versions (gid,space_gid,tenant_gid,version_kind,source_refs_json,algorithm_versions_json,manifest_hash,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(vg,space_gid,tenant_gid,version_kind,_json(source_refs),_json(algorithm_versions),manifest,actor_gid))
            cur.execute("SELECT member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone FROM workmanship_craft_bop_space_head_members WHERE space_head_gid=%s ORDER BY member_kind,logical_gid", (head["gid"],))
            for member in cur.fetchall():
                cur.execute("INSERT INTO workmanship_craft_bop_space_version_members (gid,space_version_gid,member_kind,logical_gid,node_revision_gid,binding_revision_gid,vpps_group_version_gid,is_tombstone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (str(next_gid()),vg,member["member_kind"],member["logical_gid"],member["node_revision_gid"],member["binding_revision_gid"],member["vpps_group_version_gid"],member["is_tombstone"]))
            return {"version_gid":vg,"space_gid":str(space_gid),"version_kind":version_kind,"manifest_hash":manifest}
        return store._write(cur,tenant_gid=tenant_gid,operation="space_version.save",resource_gid=space_gid,key=idempotency_key,payload=payload,effect=effect)


def freeze_team_space(store, *, space_gid, tenant_gid, actor_gid, expected_head_version, version_gid, idempotency_key):
    payload={"space_gid":space_gid,"expected_head_version":expected_head_version,"version_gid":version_gid}
    with store._connect() as conn, conn.cursor() as cur:
        def effect():
            space=store._row(cur,"SELECT space_kind,row_version FROM workmanship_craft_bop_spaces WHERE gid=%s AND tenant_gid=%s AND deleted_at IS NULL FOR UPDATE",(space_gid,tenant_gid),"space_not_found")
            if space["space_kind"]!="team": raise BopRepositoryError("team_space_required")
            if space["row_version"]!=expected_head_version: raise BopRepositoryError("resource_version_conflict")
            cur.execute("SELECT gid FROM workmanship_craft_bop_space_versions WHERE gid=%s AND space_gid=%s AND tenant_gid=%s",(version_gid,space_gid,tenant_gid))
            if not cur.fetchone(): raise BopRepositoryError("space_version_invalid")
            cur.execute("UPDATE workmanship_craft_bop_spaces SET frozen_version_gid=%s,row_version=row_version+1,updated_at=CURRENT_TIMESTAMP(6) WHERE gid=%s",(version_gid,space_gid))
            return {"space_gid":str(space_gid),"frozen_version_gid":str(version_gid),"row_version":expected_head_version+1}
        return store._write(cur,tenant_gid=tenant_gid,operation="space.freeze",resource_gid=space_gid,key=idempotency_key,payload=payload,effect=effect)


def set_baseline(store, *, repository_gid, tenant_gid, actor_gid, expected_row_version, version_gid, idempotency_key):
    payload={"repository_gid":repository_gid,"expected_row_version":expected_row_version,"version_gid":version_gid}
    with store._connect() as conn, conn.cursor() as cur:
        def effect():
            repo=store._row(cur,"SELECT row_version FROM workmanship_craft_bop_repositories WHERE gid=%s AND tenant_gid=%s AND deleted_at IS NULL FOR UPDATE",(repository_gid,tenant_gid),"repository_not_found")
            if repo["row_version"]!=expected_row_version: raise BopRepositoryError("resource_version_conflict")
            cur.execute("SELECT v.gid FROM workmanship_craft_bop_space_versions v JOIN workmanship_craft_bop_spaces s ON s.gid=v.space_gid WHERE v.gid=%s AND s.repository_gid=%s AND s.space_kind='team'",(version_gid,repository_gid))
            if not cur.fetchone(): raise BopRepositoryError("baseline_version_invalid")
            cur.execute("UPDATE workmanship_craft_bop_repositories SET baseline_version_gid=%s,row_version=row_version+1,updated_at=CURRENT_TIMESTAMP(6) WHERE gid=%s",(version_gid,repository_gid))
            return {"repository_gid":str(repository_gid),"baseline_version_gid":str(version_gid),"row_version":expected_row_version+1}
        return store._write(cur,tenant_gid=tenant_gid,operation="repository.baseline",resource_gid=repository_gid,key=idempotency_key,payload=payload,effect=effect)


def delete_personal_space(store, *, space_gid, tenant_gid, owner_gid, expected_row_version, idempotency_key, actor_gid=None):
    payload={"space_gid":space_gid,"expected_row_version":expected_row_version}
    with store._connect() as conn, conn.cursor() as cur:
        def effect():
            row=store._row(cur,"SELECT row_version FROM workmanship_craft_bop_spaces WHERE gid=%s AND tenant_gid=%s AND space_kind='managed_personal' AND owner_user_gid=%s AND deleted_at IS NULL FOR UPDATE",(space_gid,tenant_gid,owner_gid),"space_not_found")
            if row["row_version"]!=expected_row_version: raise BopRepositoryError("resource_version_conflict")
            cur.execute("SELECT 1 FROM workmanship_craft_bop_change_proposals WHERE personal_space_gid=%s AND apply_status<>'applied' AND review_status NOT IN ('rejected','withdrawn','cancelled','superseded') LIMIT 1",(space_gid,))
            if cur.fetchone(): raise BopRepositoryError("unresolved_proposal_exists")
            deletion_gid=str(next_gid()); cur.execute("UPDATE workmanship_craft_bop_spaces SET deleted_at=CURRENT_TIMESTAMP(6),deleted_by=%s,deletion_gid=%s,row_version=row_version+1 WHERE gid=%s",(owner_gid,deletion_gid,space_gid))
            return {"space_gid":str(space_gid),"deleted":True,"deletion_gid":deletion_gid,"row_version":expected_row_version+1}
        return store._write(cur,tenant_gid=tenant_gid,operation="personal.delete",resource_gid=space_gid,key=idempotency_key,payload=payload,effect=effect)
