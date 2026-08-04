"""Simulation environments built from immutable Craft execution-plan contracts."""
from __future__ import annotations

import json
import secrets
from typing import Any, Mapping

from backend.contracts.simulation_environment_source_v1 import pin_environment_source

from .data.connection import get_simulation_conn


def create_environment(
    *, name: str, plan: Mapping[str, Any], snapshot_uri: str,
    creator_gid: str, team_gid: str | None = None,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("name is required")
    if len(clean_name) > 255:
        raise ValueError("name is too long")
    pinned = pin_environment_source(plan, snapshot_uri)
    gid = f"simenv_{secrets.token_hex(16)}"
    with get_simulation_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_sim_environments
                   (gid, name, status, owner_gid, team_gid, source_bop_version_gid,
                    source_bop_revision, source_bop_hash, execution_plan_snapshot_uri,
                    pinned_source, created_at, updated_at)
                   VALUES (%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())""",
                (
                    gid, clean_name, creator_gid, team_gid,
                    pinned["source_bop_version_gid"], pinned["source_bop_revision"],
                    pinned["source_bop_hash"], pinned["execution_plan_snapshot_uri"],
                    json.dumps(pinned, ensure_ascii=False),
                ),
            )
    return {"gid": gid, "name": clean_name, "status": "draft", "source": pinned}


def get_environment(gid: str, user_gid: str, team_gid: str | None = None) -> dict[str, Any]:
    with get_simulation_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT gid,name,status,owner_gid,team_gid,pinned_source,created_at,updated_at
                   FROM workmanship_sim_environments
                   WHERE gid=%s AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))""",
                (gid, user_gid, team_gid, team_gid),
            )
            row = cur.fetchone()
    if not row:
        raise LookupError("simulation environment not found")
    result = dict(row)
    if isinstance(result.get("pinned_source"), str):
        result["pinned_source"] = json.loads(result["pinned_source"])
    return result


def list_environments(user_gid: str, team_gid: str | None = None) -> list[dict[str, Any]]:
    with get_simulation_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT gid,name,status,owner_gid,team_gid,source_bop_version_gid,
                          source_bop_revision,source_bop_hash,created_at,updated_at
                   FROM workmanship_sim_environments
                   WHERE owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s)
                   ORDER BY updated_at DESC LIMIT 200""",
                (user_gid, team_gid, team_gid),
            )
            return [dict(row) for row in cur.fetchall()]
