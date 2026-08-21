"""Bounded, read-only VPPS validation for PBOM snapshots."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn


OPERATIONS = ("check",)
MAX_ERRORS = 500
_log = logging.getLogger(__name__)

_PART_COLS = (
    "gid, snapshot_gid, part_no, title AS name, quantity, unit, material, parent_gid, "
    "vpps, vpps_desc, parent_vpps, parent_vpps_name, bom_row, bom_row_label, component_id, "
    "component_type, component_version_status, purchase_status, variable_formula, torque, "
    "torque_importance, ownership_user, level, home, configuration, parent_bom_row, remark, "
    "temp_vpps, catia_occurrence_name, catia_file_name, catia_uuid, default_matrix, abs_matrix, "
    "rel_matrix, local_bbox, ecn, fna, geo_main_part, ref_main_vpps_desc, ref_main_vpps, "
    "main_part_consistency, geo_evidence, lr_side, meta, created_at"
)


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _bounded(items: list[Any], label: str) -> None:
    if len(items) > MAX_ERRORS:
        raise CapabilityBusinessError("invalid_input", f"{label} exceeds the bounded response limit", details={"limit": MAX_ERRORS, "count": len(items)})


def _norm_desc(value: str) -> str:
    value = (value or "").strip()
    dash = value.find("-")
    if dash != -1:
        value = value[dash + 1:]
    return re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbf]", "", value)


def _parse_mat(value: str) -> list[float] | None:
    if not value:
        return None
    try:
        result = list(map(float, value.split()))
    except (TypeError, ValueError):
        return None
    return result if len(result) == 16 else None


def _parse_bbox(value: str) -> list[float] | None:
    if not value:
        return None
    try:
        result = list(map(float, value.split(",")))
    except (TypeError, ValueError):
        return None
    return result if len(result) == 6 else None


def _world_bbox(matrix: list[float], bbox: list[float]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    corners = [(xmin, ymin, zmin), (xmax, ymin, zmin), (xmin, ymax, zmin), (xmax, ymax, zmin),
               (xmin, ymin, zmax), (xmax, ymin, zmax), (xmin, ymax, zmax), (xmax, ymax, zmax)]
    xs, ys, zs = [], [], []
    for x, y, z in corners:
        xs.append(x * matrix[0] + y * matrix[4] + z * matrix[8] + matrix[12])
        ys.append(x * matrix[1] + y * matrix[5] + z * matrix[9] + matrix[13])
        zs.append(x * matrix[2] + y * matrix[6] + z * matrix[10] + matrix[14])
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _overlap(min1: tuple[float, float, float], max1: tuple[float, float, float], min2: tuple[float, float, float], max2: tuple[float, float, float]) -> float:
    dx = max(0.0, min(max1[0], max2[0]) - max(min1[0], min2[0]))
    dy = max(0.0, min(max1[1], max2[1]) - max(min1[1], min2[1]))
    dz = max(0.0, min(max1[2], max2[2]) - max(min1[2], min2[2]))
    return dx * dy * dz


def _extract_ab(value: str) -> tuple[str | None, str | None, str | None]:
    if not value:
        return None, None, None
    value = re.sub(r"\(.*?\)", "", value).strip()
    dash = value.find("-")
    if dash == -1:
        return None, None, None
    after = value[dash + 1:].strip()
    for separator in ("到", "与"):
        if separator in after:
            first, second = after.split(separator, 1)
            return first.strip(), second.strip(), separator
    return after.strip(), None, None


def _lr(name: str) -> str:
    return "左" if "左" in name else ("右" if "右" in name else "")


def _similarity(query: str, part_name: str, threshold: float = 0.60) -> int:
    if not query or not part_name:
        return 0
    if query == part_name:
        return len(query) * 10
    best = 0
    for start in range(len(query)):
        for end in range(start + 2, len(query) + 1):
            sub = query[start:end]
            if sub in part_name and len(sub) > best:
                best = len(sub)
    return best if best > 0 and best / len(part_name) >= threshold else 0


def _match(query: str | None, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not query or not candidates:
        return None
    eligible = [candidate for candidate in candidates if not ("支架" not in query and "支架" in (candidate.get("name") or ""))]
    best, best_score = None, 0
    for candidate in eligible:
        score = _similarity(query, candidate.get("name") or "")
        if score > best_score:
            best_score, best = score, candidate
    return best


def _match_ab(first: str | None, second: str | None, separator: str | None, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    first_match = _match(first, candidates)
    if separator != "与" or not second:
        return first_match
    second_match = _match(second, candidates)
    if not first_match:
        return second_match
    if not second_match:
        return first_match
    return first_match if _similarity(first or "", first_match.get("name") or "") >= _similarity(second or "", second_match.get("name") or "") else second_match


def check_vpps(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    if str(payload.get("operation") or "check") not in OPERATIONS:
        raise ValueError("unsupported VPPS check operation")
    snapshot_gid = _required_text(payload, "snapshot_gid")
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, version_tag, name FROM workmanship_bop_pbom_versions WHERE gid=%s", (snapshot_gid,))
            version = cur.fetchone()
            if not version:
                raise CapabilityBusinessError("resource_not_found", f"PBOM snapshot {snapshot_gid} does not exist")
            cur.execute(f"SELECT {_PART_COLS} FROM workmanship_bop_pbom WHERE snapshot_gid=%s ORDER BY level, bom_row", (snapshot_gid,))
            parts = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT gid, vpps, vpps_description, vpps_desc_cn, alias FROM workmanship_tpl_vpps_parts")
            reference_rows = cur.fetchall()
            try:
                cur.execute("SELECT pbom_row_gid FROM vpps_operations WHERE pbom_version_gid=%s AND operation_type='rule4_bulk_ignore' AND is_active=TRUE", (snapshot_gid,))
                ignored_rule4_gids = {row["pbom_row_gid"] for row in cur.fetchall()}
            except Exception:
                _log.warning("VPPS check: failed to read rule4 concessions", exc_info=True)
                ignored_rule4_gids = set()

    _bounded(parts, "parts")
    reference_map: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, dict[str, Any]] = {}
    for row in reference_rows:
        vpps = (row["vpps"] or "").strip()
        if vpps:
            reference_map[vpps] = row
        raw_alias = row["alias"] or []
        if isinstance(raw_alias, str):
            try:
                raw_alias = json.loads(raw_alias)
            except (TypeError, ValueError):
                raw_alias = []
        for alias in raw_alias:
            alias = (alias or "").strip()
            if alias:
                alias_map[alias] = {"vpps_part_gid": row["gid"], "canonical_vpps": vpps}

    errors: list[dict[str, Any]] = []
    alias_matches: list[dict[str, Any]] = []
    by_bom_row = {(part.get("bom_row") or "").strip(): part for part in parts if (part.get("bom_row") or "").strip()}
    for index, part in enumerate(parts):
        if part.get("level") is not None and part.get("level") != 3:
            continue
        vpps = (part.get("vpps") or "").strip()
        desc = (part.get("vpps_desc") or "").strip()
        parent_vpps = (part.get("parent_vpps") or "").strip()
        if not vpps:
            continue
        reference = reference_map.get(vpps)
        if not reference:
            errors.append({"rule": 1, "vpps": vpps, "row": index + 1, "msg": f'VPPS "{vpps}" 在主数据中不存在'})
        elif desc:
            ref_en, ref_cn = (reference["vpps_description"] or "").strip(), (reference["vpps_desc_cn"] or "").strip()
            desc_norm, en_norm, cn_norm = _norm_desc(desc), _norm_desc(ref_en), _norm_desc(ref_cn)
            matched = bool(desc_norm and (desc_norm == en_norm or desc_norm == cn_norm)) or desc == ref_en or desc == ref_cn
            alias_hit = alias_map.get(desc)
            if not matched and alias_hit and alias_hit["canonical_vpps"] == vpps:
                alias_matches.append({"vpps": vpps, "row": index + 1, "desc": desc})
            elif not matched:
                errors.append({"rule": 1, "vpps": vpps, "row": index + 1, "msg": f'描述不一致: "{desc}" ≠ 主数据"{ref_cn or ref_en}"'})
        if parent_vpps:
            prefix = parent_vpps.rstrip(".")
            if not (vpps.startswith(prefix + ".") or vpps == prefix):
                errors.append({"rule": 3, "vpps": vpps, "row": index + 1, "msg": f'层级不匹配: "{vpps}" 不以父级 "{parent_vpps}" 开头'})

    by_gid = {part["gid"]: part for part in parts if part.get("gid")}
    for index, part in enumerate(parts):
        if part.get("level") is not None and part.get("level") != 3:
            continue
        parent_vpps, parent_bom_row, parent_gid = (part.get("parent_vpps") or "").strip(), (part.get("parent_bom_row") or "").strip(), (part.get("parent_gid") or "").strip()
        if not parent_vpps:
            continue
        parent = by_bom_row.get(parent_bom_row) or (by_gid.get(parent_gid) if parent_gid else None)
        if parent is not None:
            actual = (parent.get("vpps") or "").strip()
            if actual and actual != parent_vpps:
                label = (part.get("vpps") or part.get("part_no") or "-").strip()
                errors.append({"rule": 2, "vpps": label, "row": index + 1, "msg": f'父级VPPS字段"{parent_vpps}" ≠ 父级零件实际VPPS"{actual}"'})

    structural_types, fastener_types = {"零部件"}, {"标准件", "非标件"}
    parent_to_struct: dict[str, list[dict[str, Any]]] = {}
    for part in parts:
        if (part.get("component_type") or "").strip() in structural_types:
            parent_to_struct.setdefault((part.get("parent_bom_row") or "").strip(), []).append(part)

    rule4_errors: list[dict[str, Any]] = []
    rule4_ignored: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        if (part.get("component_type") or "").strip() not in fastener_types:
            continue
        if part.get("gid") and part["gid"] in ignored_rule4_gids:
            rule4_ignored.append({"vpps": (part.get("vpps") or "").strip(), "row": index + 1})
            continue
        siblings = list(parent_to_struct.get((part.get("parent_bom_row") or "").strip(), []))
        if not siblings:
            continue
        first, second, separator = _extract_ab(part.get("vpps_desc") or "")
        geo_siblings = siblings
        side = _lr(part.get("name") or "")
        if side and len(siblings) > 1:
            same_side = [sibling for sibling in siblings if _lr(sibling.get("name") or "") == side]
            if same_side:
                geo_siblings = same_side
        geo_main = None
        matrix, bbox = _parse_mat(part.get("abs_matrix") or ""), _parse_bbox(part.get("local_bbox") or "")
        if matrix and bbox:
            part_min, part_max = _world_bbox(matrix, bbox)
            best_volume = 0.0
            for sibling in geo_siblings:
                sibling_matrix, sibling_bbox = _parse_mat(sibling.get("abs_matrix") or ""), _parse_bbox(sibling.get("local_bbox") or "")
                if not sibling_matrix or not sibling_bbox:
                    continue
                sibling_min, sibling_max = _world_bbox(sibling_matrix, sibling_bbox)
                volume = _overlap(part_min, part_max, sibling_min, sibling_max)
                if volume > best_volume:
                    best_volume, geo_main = volume, sibling
        vpps_main = _match_ab(first, second, separator, siblings)
        label = (part.get("vpps") or part.get("name") or "").strip()
        if geo_main and vpps_main:
            geo_id = (geo_main.get("catia_file_name") or geo_main.get("name") or "").strip()
            vpps_id = (vpps_main.get("catia_file_name") or vpps_main.get("name") or "").strip()
            if geo_id and vpps_id and geo_id != vpps_id:
                ref = f'VPPS描述AB="{first}与{second}"→最佳匹配"{vpps_main.get("name")}"' if separator == "与" else f'VPPS描述A="{first}"→"{vpps_main.get("name")}"'
                rule4_errors.append({"rule": 4, "vpps": label, "row": index + 1, "gid": part.get("gid", ""), "vpps_desc": part.get("vpps_desc", ""), "msg": f'主件不一致: 几何主件="{geo_main.get("name")}" vs {ref}'})
        elif not geo_main and first:
            consistency = (part.get("main_part_consistency") or "").strip()
            if "⚠" in consistency:
                rule4_errors.append({"rule": 4, "vpps": label, "row": index + 1, "gid": part.get("gid", ""), "vpps_desc": part.get("vpps_desc", ""), "msg": f"主件不一致(无几何): {consistency}"})

    _bounded(errors, "validation errors")
    _bounded(rule4_errors, "rule4 errors")
    _bounded(alias_matches, "alias matches")
    _bounded(rule4_ignored, "rule4 concessions")
    all_errors = errors + rule4_errors
    rule_errors = {str(rule): [item for item in errors if item["rule"] == rule] for rule in (1, 2, 3)}
    return CapabilityOutput(data={
        "snapshot": {"gid": snapshot_gid, "version_tag": version["version_tag"], "name": version["name"] or ""},
        "summary": {
            "total_parts": len(parts), "parts_with_vpps": sum(1 for part in parts if (part.get("vpps") or "").strip()),
            "rule1_errors": len(rule_errors["1"]), "rule2_errors": len(rule_errors["2"]), "rule3_errors": len(rule_errors["3"]),
            "rule4_errors": len(rule4_errors), "rule4_ignored": len(rule4_ignored), "alias_matches": len(alias_matches), "ok": not all_errors,
        },
        "errors": {"rule1": rule_errors["1"], "rule2": rule_errors["2"], "rule3": rule_errors["3"], "rule4": rule4_errors},
        "alias_matches": alias_matches,
        "rule4_ignored": rule4_ignored,
    })


def register_vpps_check_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.ebom.vpps_check.read", owner="craft",
        description="Run the bounded four-rule VPPS validation projection for a PBOM snapshot.",
        use_when="A governed Craft consumer needs deterministic VPPS validation results for one snapshot.",
        do_not_use_when="The request mutates PBOM data, changes concessions, or publishes a validation policy.",
        risk="read", permissions=("craft.read",),
        input_schema={"type": "object", "required": ["operation", "snapshot_gid"], "properties": {"operation": {"type": "string", "enum": list(OPERATIONS)}, "snapshot_gid": {"type": "string"}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["snapshot", "summary", "errors", "alias_matches", "rule4_ignored"], "properties": {"snapshot": {"type": "object", "additionalProperties": True}, "summary": {"type": "object", "additionalProperties": True}, "errors": {"type": "object", "additionalProperties": True}, "alias_matches": {"type": "array", "maxItems": MAX_ERRORS, "items": {"type": "object", "additionalProperties": True}}, "rule4_ignored": {"type": "array", "maxItems": MAX_ERRORS, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False},
        tags=("craft", "ebom", "vpps", "read"),
    ), check_vpps)


__all__ = ["MAX_ERRORS", "OPERATIONS", "check_vpps", "register_vpps_check_capability"]
