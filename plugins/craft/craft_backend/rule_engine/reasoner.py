"""Craft structural checks over a pinned immutable Ontology projection."""
from __future__ import annotations

from typing import Optional

from plugins.ontology.public import active_projection

from ..data.connection import get_conn


def _concept_map() -> dict[str, dict]:
    return {str(row["stable_gid"]): row for row in active_projection()["concept"]}


def get_ancestor_gids(class_gid: str, _cur=None) -> list[str]:
    concepts = _concept_map()
    result: list[str] = []
    current: str | None = class_gid
    while current and current not in result:
        result.append(current)
        row = concepts.get(current) or {}
        current = row.get("parent_stable_gid") or row.get("parent_gid")
    return result


def get_class_gid_for_node_type(node_type: str, _cur=None) -> Optional[str]:
    for row in active_projection()["concept"]:
        if row.get("node_type_binding") == node_type:
            return str(row["stable_gid"])
    return None


def get_inherited_properties(class_gid: str, _cur=None) -> list[dict]:
    projection = active_projection()
    ancestors = get_ancestor_gids(class_gid)
    order = {gid: index for index, gid in enumerate(ancestors)}
    rows = sorted(
        (
            row for row in projection["property"]
            if (row.get("class_stable_gid") or row.get("class_gid")) in order
        ),
        key=lambda row: (order.get(row.get("class_stable_gid") or row.get("class_gid"), 999), row.get("sort_order", 0)),
    )
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        name = str(row.get("name") or "")
        if name and name not in seen:
            seen.add(name)
            result.append(row)
    return result


def check_cardinality(entry_gid: str, node_type: str, cur) -> list[dict]:
    class_gid = get_class_gid_for_node_type(node_type)
    if not class_gid:
        return []
    projection = active_projection()
    ancestors = set(get_ancestor_gids(class_gid))
    concepts = {str(row["stable_gid"]): row for row in projection["concept"]}
    props = {str(row["stable_gid"]): row for row in projection["property"]}
    violations: list[dict] = []
    for axiom in projection["constraint"]:
        if (axiom.get("class_stable_gid") or axiom.get("class_gid")) not in ancestors:
            continue
        axiom_type = axiom.get("axiom_type")
        if axiom_type not in {"minCardinality", "maxCardinality", "exactCardinality"}:
            continue
        child = concepts.get(str(axiom.get("target_stable_gid") or axiom.get("target_gid"))) or {}
        child_type = child.get("node_type_binding")
        if not child_type:
            continue
        try:
            threshold = int(axiom.get("expression"))
        except (TypeError, ValueError):
            continue
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM workmanship_bop_bop_entries "
            "WHERE parent_gid=%s AND node_type=%s AND deleted_at IS NULL",
            (entry_gid, child_type),
        )
        count = int(dict(cur.fetchone())["cnt"])
        prop = props.get(str(axiom.get("property_stable_gid") or axiom.get("property_gid"))) or {}
        label = prop.get("label_zh") or child_type
        invalid = (
            (axiom_type == "minCardinality" and count < threshold)
            or (axiom_type == "maxCardinality" and count > threshold)
            or (axiom_type == "exactCardinality" and count != threshold)
        )
        if invalid:
            violations.append({
                "type": "cardinality",
                "message": f"{label} 基数约束 {axiom_type}={threshold} 未满足（当前 {count}）",
                "child_node_type": child_type,
                "required": threshold,
                "actual": count,
                "enforcement_level": "mandatory",
            })
    return violations


def consistency_check(entry_gid: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT node_type FROM workmanship_bop_bop_entries WHERE gid=%s AND deleted_at IS NULL",
                (entry_gid,),
            )
            row = cur.fetchone()
            if not row:
                return {"entry_gid": entry_gid, "valid": False, "violations": [{"message": "条目不存在"}], "warnings": []}
            node_type = dict(row)["node_type"]
            violations = check_cardinality(entry_gid, node_type, cur)
    return {"entry_gid": entry_gid, "node_type": node_type, "valid": not violations, "violations": violations, "warnings": []}


def build_agent_schema() -> dict:
    projection = active_projection()
    concepts = {str(row["stable_gid"]): row for row in projection["concept"]}
    schema: dict[str, dict] = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            for gid, concept in concepts.items():
                node_type = concept.get("node_type_binding")
                if not node_type:
                    continue
                ancestors = get_ancestor_gids(gid)
                placeholders = ",".join(["%s"] * len(ancestors))
                cur.execute(
                    f"SELECT name,enforcement_level,expression FROM workmanship_know_craft_rules "
                    f"WHERE context_class_gid IN ({placeholders}) AND status='active' AND expression IS NOT NULL",
                    ancestors,
                )
                rules = [dict(row) for row in cur.fetchall()]
                props = get_inherited_properties(gid)
                children = [
                    row.get("node_type_binding") for row in concepts.values()
                    if (row.get("parent_stable_gid") or row.get("parent_gid")) == gid and row.get("node_type_binding")
                ]
                parent = concepts.get(str(concept.get("parent_stable_gid") or concept.get("parent_gid"))) or {}
                schema[str(node_type)] = {
                    "label": concept.get("label_zh") or concept.get("name"),
                    "parent": parent.get("node_type_binding"),
                    "children": children,
                    "required_props": [row.get("name") for row in props if row.get("required")],
                    "optional_props": [row.get("name") for row in props if not row.get("required")],
                    "rules": [{"name": row["name"], "level": row["enforcement_level"], "expr": row["expression"]} for row in rules],
                }
    return schema
