"""Persistence for immutable Connector environment manifests."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext

from ..domain.environment_manifest import SimulationEnvironmentManifestV1
from .connection import get_simulation_conn


def _visible_clause(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"({prefix}owner_gid=%s OR (%s IS NOT NULL AND {prefix}team_gid=%s))"


class EnvironmentManifestRepository:
    def insert_manifest(
        self,
        manifest: SimulationEnvironmentManifestV1,
        context: CapabilityContext,
        *,
        name: str | None = None,
    ) -> None:
        value = manifest.model_dump(mode="json")
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        identity = (manifest.environment_id, name or manifest.environment_id, context.user_gid, context.team_gid)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO workmanship_sim_connector_environments "
                "(environment_id,name,status,owner_gid,team_gid,created_at,updated_at) "
                "VALUES (%s,%s,'active',%s,%s,NOW(6),NOW(6))",
                identity,
            )
            cursor.execute(
                "INSERT INTO workmanship_sim_environment_manifests "
                "(environment_id,environment_version,manifest_hash,manifest_json,owner_gid,team_gid,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,NOW(6))",
                (
                    manifest.environment_id, manifest.environment_version, manifest.manifest_hash,
                    encoded, context.user_gid, context.team_gid,
                ),
            )
            rows = [
                (
                    manifest.environment_id, manifest.environment_version, "product", "product",
                    item.product_ref, item.node_key,
                    json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    context.user_gid, context.team_gid,
                )
                for item in manifest.product_bindings
            ] + [
                (
                    manifest.environment_id, manifest.environment_version, "resource", item.resource_type,
                    item.code, item.node_key,
                    json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    context.user_gid, context.team_gid,
                )
                for item in manifest.resource_bindings
            ]
            if rows:
                cursor.executemany(
                    "INSERT INTO workmanship_sim_environment_bindings "
                    "(environment_id,environment_version,binding_kind,source_type,source_code,node_key,binding_json,owner_gid,team_gid,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6))",
                    rows,
                )

    def get_manifest(
        self,
        environment_id: str,
        environment_version: int,
        context: CapabilityContext,
    ) -> SimulationEnvironmentManifestV1 | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT manifest_json FROM workmanship_sim_environment_manifests "
                f"WHERE environment_id=%s AND environment_version=%s AND {_visible_clause()}",
                (environment_id, environment_version, context.user_gid, context.team_gid, context.team_gid),
            )
            row = cursor.fetchone()
        if not row:
            return None
        value: Any = row["manifest_json"]
        return SimulationEnvironmentManifestV1.model_validate(json.loads(value) if isinstance(value, str) else value)

    def search_manifests(
        self, context: CapabilityContext, *, limit: int = 50,
    ) -> tuple[SimulationEnvironmentManifestV1, ...]:
        bounded = max(1, min(int(limit), 200))
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT m.manifest_json FROM workmanship_sim_environment_manifests m "
                "JOIN workmanship_sim_connector_environments e ON e.environment_id=m.environment_id "
                f"WHERE e.status='active' AND {_visible_clause('m')} "
                "ORDER BY m.created_at DESC LIMIT %s",
                (context.user_gid, context.team_gid, context.team_gid, bounded),
            )
            rows = cursor.fetchall()
        return tuple(
            SimulationEnvironmentManifestV1.model_validate(
                json.loads(row["manifest_json"])
                if isinstance(row["manifest_json"], str) else row["manifest_json"]
            )
            for row in rows
        )

    def archive(self, environment_id: str, context: CapabilityContext) -> bool:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_connector_environments SET status='archived',updated_at=NOW(6) "
                f"WHERE environment_id=%s AND status='active' AND {_visible_clause()}",
                (environment_id, context.user_gid, context.team_gid, context.team_gid),
            )
            return cursor.rowcount == 1


repository = EnvironmentManifestRepository()


__all__ = ["EnvironmentManifestRepository", "repository"]
