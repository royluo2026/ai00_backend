"""
backend/rule_engine/checker.py
──────────────────────────────
BOP 条目规则检验入口。

check_entry_rules(node_type, entry_gid) → list[dict]
  • 两阶段校验：
    阶段1 - 属性约束：从 onto_properties 读取 required/min_val/max_val，直接校验
    阶段2 - CEL 规则：从 craft_rules 读取 expression，用 CEL 引擎执行
  • 若 onto_classes 表尚未建立或无绑定类，静默返回 []
  • 返回结果只含 FAIL / WARN，PASS / SKIP 不返回
"""
import logging

from plugins.ontology.public import active_projection

from ..data.connection import get_conn
from ..table_names import craft_entity_table_name
from .executor import RuleResult, check_rule
from .graph import get_ancestor_gids


def _resolve_mysql_table(pg_entity_table: str) -> str:
    """将 PG schema.tablename 格式转换为 MySQL 实际表名。
    优先查 TABLE_MAP，找不到时取 tablename 部分（降级）。
    """
    return craft_entity_table_name(pg_entity_table)

_log = logging.getLogger(__name__)

# node_type → (is_primary link_type, entity table, readable columns)
_ENTITY_TABLE_MAP: dict[str, tuple[str, str, list[str]]] = {
    "line_process":      ("asm_line_process",     "workmanship_bop_bop_line",               ["name", "version_no"]),
    "station_process":   ("asm_station_process",  "workmanship_bop_bop_station",            ["name", "version_no"]),
    "operator_process":  ("asm_operator_process", "workmanship_bop_bop_operator",           ["headcount", "operator_code"]),
    "operation":         ("asm_operation",         "workmanship_bop_bop_steps",             ["vd_time", "total_time", "floor_height_need", "op_req_height"]),
    "project_equipment": ("project_equipment",    "workmanship_bop_bop_equipments",         ["spec", "quantity", "status"]),
    "project_tooling":   ("project_tooling",      "workmanship_bop_bop_fixtures",           ["spec", "quantity", "status"]),
    "project_tools":     ("project_tools",        "workmanship_bop_bop_tools",              ["spec", "quantity", "status"]),
    "project_roles":     ("project_roles",        "workmanship_bop_project_roles",          ["headcount", "role_type"]),
    "physical_station":  ("physical_station",     "factory.factory_stations",   ["takt_time", "height_mm"]),
    "physical_equipment":("physical_equipment",   "factory.factory_equipments", ["asset_no", "status"]),
    "physical_tool":     ("physical_tool",        "factory.factory_tools",      ["asset_no", "status"]),
    "physical_fixture":  ("physical_fixture",     "factory.factory_fixtures",   ["asset_no", "status"]),
}


def _get_entity_table_from_db(cur, node_type: str):
    """Entity storage is Craft-owned and never supplied by Ontology metadata."""
    return _ENTITY_TABLE_MAP.get(node_type)


def check_entry_rules(node_type: str, entry_gid: str) -> list[dict]:
    """检验单个 BOP 条目是否满足本体属性约束 + CEL 规则。"""
    try:
        return _do_check(node_type, entry_gid)
    except Exception as e:
        _log.debug("check_entry_rules failed silently: %s", e)
        return []


def _do_check(node_type: str, entry_gid: str) -> list[dict]:
    projection = active_projection()
    class_map = {
        str(row["stable_gid"]): {**row, "parent_gid": row.get("parent_stable_gid") or row.get("parent_gid")}
        for row in projection["concept"]
    }
    cls_row = next((row for row in class_map.values() if row.get("node_type_binding") == node_type), None)
    if not cls_row:
        return []
    ancestor_gids = get_ancestor_gids(str(cls_row["stable_gid"]), class_map)
    props = [
        dict(row) for row in projection["property"]
        if (row.get("class_stable_gid") or row.get("class_gid")) in ancestor_gids
        and row.get("prop_kind", "data") == "data"
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 加载含 expression 的激活规则（含继承）
            _ph2 = ','.join(['%s'] * len(ancestor_gids))
            cur.execute(
                f"SELECT gid, name, expression, enforcement_level"
                f" FROM workmanship_know_craft_rules"
                f" WHERE context_class_gid IN ({_ph2})"
                f"   AND expression IS NOT NULL AND TRIM(expression) <> ''"
                f"   AND status = 'active'",
                ancestor_gids,
            )
            rules = [dict(r) for r in cur.fetchall()]

            # bop_entries 基础字段 + meta
            cur.execute("SELECT * FROM workmanship_bop_bop_entries WHERE gid = %s", (entry_gid,))
            entry_row = cur.fetchone()
            if not entry_row:
                return []

            # 实体表字段
            entity_vals: dict = {}
            mapping = _get_entity_table_from_db(cur, node_type)
            if mapping:
                link_type, table, cols = mapping
                mysql_table = _resolve_mysql_table(table)
                cur.execute(
                    "SELECT target_gid FROM workmanship_bop_bop_entry_links"
                    " WHERE bop_entry_gid=%s AND link_type=%s AND is_primary=TRUE LIMIT 1",
                    (entry_gid, link_type),
                )
                link_row = cur.fetchone()
                if link_row:
                    col_str = ", ".join(cols)
                    cur.execute(f"SELECT {col_str} FROM `{mysql_table}` WHERE gid=%s", (link_row["target_gid"],))
                    entity_row = cur.fetchone()
                    if entity_row:
                        entity_vals = {k: v for k, v in dict(entity_row).items() if v is not None}

    # 合并 context：bop_entries 基础字段 + 实体表字段 + meta JSONB
    context: dict = {}
    for k, v in dict(entry_row).items():
        if v is not None and isinstance(v, (int, float, str, bool)):
            context[k] = v
    context.update(entity_vals)
    meta = entry_row.get("meta") or {}
    if isinstance(meta, dict):
        for k, v in meta.items():
            if v is not None and isinstance(v, (int, float, str, bool)):
                context[k] = v

    violations: list[dict] = []

    # ── 阶段1：属性约束校验 ────────────────────────────────────────────────────
    for prop in props:
        name      = prop["name"]
        val       = context.get(name)
        data_type = prop["data_type"]
        required  = prop["required"]
        min_val   = prop["min_val"]
        max_val   = prop["max_val"]

        if required and (val is None or val == ""):
            violations.append({
                "rule_gid":          None,
                "rule_name":         f"必填约束：{name}",
                "result":            "fail",
                "message":           f"字段「{name}」为必填项，当前值为空",
                "enforcement_level": "mandatory",
                "source":            "property_constraint",
            })
            continue

        if val is None:
            continue

        try:
            num = float(val)
            if min_val is not None and num < float(min_val):
                violations.append({
                    "rule_gid":          None,
                    "rule_name":         f"范围约束：{name} >= {min_val}",
                    "result":            "fail",
                    "message":           f"字段「{name}」值 {val} 小于最小值 {min_val}",
                    "enforcement_level": "mandatory",
                    "source":            "property_constraint",
                })
            if max_val is not None and num > float(max_val):
                violations.append({
                    "rule_gid":          None,
                    "rule_name":         f"范围约束：{name} <= {max_val}",
                    "result":            "fail",
                    "message":           f"字段「{name}」值 {val} 大于最大值 {max_val}",
                    "enforcement_level": "mandatory",
                    "source":            "property_constraint",
                })
        except (TypeError, ValueError):
            pass  # 非数值字段跳过范围校验

    # ── 阶段2：CEL 规则校验 ─────────────────────────────────────────────────────
    for rule in rules:
        result, msg = check_rule(rule["expression"], context)
        if result in (RuleResult.FAIL, RuleResult.WARN):
            violations.append({
                "rule_gid":          rule["gid"],
                "rule_name":         rule["name"],
                "result":            result.value,
                "message":           msg or f"规则「{rule['name']}」未通过",
                "enforcement_level": rule.get("enforcement_level", "advisory"),
                "source":            "cel_rule",
            })

    return violations


def validate_with_proposed(
    node_type: str,
    entry_gid: str,
    proposed: dict,
    conn=None,
) -> list[dict]:
    """
    用 proposed 值覆盖当前实体值后执行 CEL 规则校验（仅 stage2）。
    属性约束（required/min/max/enum）由调用方 patch_entity_props 已校验，此处只跑规则。
    返回 violations 列表（格式同 check_entry_rules）。
    conn 参数可传入已有连接（在同一事务中）。
    """
    try:
        return _do_validate_with_proposed(node_type, entry_gid, proposed, conn)
    except Exception as e:
        _log.debug("validate_with_proposed failed silently: %s", e)
        return []


def _do_validate_with_proposed(
    node_type: str,
    entry_gid: str,
    proposed: dict,
    ext_conn=None,
) -> list[dict]:
    projection = active_projection()
    class_map = {
        str(row["stable_gid"]): {**row, "parent_gid": row.get("parent_stable_gid") or row.get("parent_gid")}
        for row in projection["concept"]
    }
    cls_row = next((row for row in class_map.values() if row.get("node_type_binding") == node_type), None)
    if not cls_row:
        return []
    ancestor_gids = get_ancestor_gids(str(cls_row["stable_gid"]), class_map)

    def _run(cur):
        # 只加载含 expression 的激活规则
        _ph = ','.join(['%s'] * len(ancestor_gids))
        cur.execute(
            f"SELECT gid, name, expression, enforcement_level"
            f" FROM workmanship_know_craft_rules"
            f" WHERE context_class_gid IN ({_ph})"
            f"   AND expression IS NOT NULL AND TRIM(expression) <> ''"
            f"   AND status = 'active'",
            ancestor_gids,
        )
        rules = [dict(r) for r in cur.fetchall()]
        if not rules:
            return []

        # 构建 context：bop_entries 字段 + 实体表字段（DB 驱动）+ meta
        cur.execute("SELECT * FROM workmanship_bop_bop_entries WHERE gid = %s", (entry_gid,))
        entry_row = cur.fetchone()
        if not entry_row:
            return []

        context: dict = {}
        for k, v in dict(entry_row).items():
            if v is not None and isinstance(v, (int, float, str, bool)):
                context[k] = v
        meta = entry_row.get("meta") or {}
        if isinstance(meta, dict):
            for k, v in meta.items():
                if v is not None and isinstance(v, (int, float, str, bool)):
                    context[k] = v

        # 用 proposed 值覆盖 context
        for k, v in proposed.items():
            if v is not None:
                context[k] = v
            elif k in context:
                del context[k]

        # 执行 CEL 规则
        violations: list[dict] = []
        for rule in rules:
            result, msg = check_rule(rule["expression"], context)
            if result in (RuleResult.FAIL, RuleResult.WARN):
                violations.append({
                    "rule_gid":          rule["gid"],
                    "rule_name":         rule["name"],
                    "result":            result.value,
                    "message":           msg or f"规则「{rule['name']}」未通过",
                    "enforcement_level": rule.get("enforcement_level", "advisory"),
                    "source":            "cel_rule",
                })
        return violations

    if ext_conn is not None:
        with ext_conn.cursor() as cur:
            return _run(cur)
    else:
        with get_conn() as conn:
            with conn.cursor() as cur:
                return _run(cur)
