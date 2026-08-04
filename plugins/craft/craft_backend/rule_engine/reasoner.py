"""
backend/rule_engine/reasoner.py
────────────────────────────────
轻量本体推理器。

与 checker.py 分工：
  checker.py  → 属性值约束（required/min/max）+ CEL 业务规则执行
  reasoner.py → 结构性推理（继承/基数约束/一致性/Agent schema）
"""
from __future__ import annotations
from typing import Optional
from ..data.connection import get_conn


def get_ancestor_gids(class_gid: str, cur) -> list[str]:
    """返回 [self, parent, grandparent...] gid 列表，自身在前。"""
    cur.execute("""
        WITH RECURSIVE anc AS (
            SELECT gid, parent_gid FROM workmanship_onto_classes WHERE gid=%s
            UNION ALL
            SELECT c.gid, c.parent_gid
            FROM workmanship_onto_classes c JOIN anc a ON c.gid=a.parent_gid
        ) SELECT gid FROM anc
    """, (class_gid,))
    seen, result = set(), []
    for row in cur.fetchall():
        g = dict(row)['gid']
        if g not in seen:
            seen.add(g); result.append(g)
    return result


def get_class_gid_for_node_type(node_type: str, cur) -> Optional[str]:
    cur.execute(
        "SELECT gid FROM workmanship_onto_classes WHERE node_type_binding=%s LIMIT 1",
        (node_type,)
    )
    row = cur.fetchone()
    return dict(row)['gid'] if row else None


def get_inherited_properties(class_gid: str, cur) -> list[dict]:
    """返回该类及所有父类的全部 onto_properties，子类同名属性优先。"""
    ancestors = get_ancestor_gids(class_gid, cur)
    if not ancestors:
        return []
    ph = ','.join(['%s'] * len(ancestors))
    cur.execute(
        f"SELECT p.* FROM workmanship_onto_properties p"
        f" WHERE p.class_gid IN ({ph})"
        f" ORDER BY p.sort_order",
        ancestors
    )
    seen, result = set(), []
    for row in [dict(r) for r in cur.fetchall()]:
        if row['name'] not in seen:
            seen.add(row['name']); result.append(row)
    return result


def check_cardinality(entry_gid: str, node_type: str, cur) -> list[dict]:
    """检查 BOP 条目的子节点基数是否满足 onto_axioms 约束。"""
    class_gid = get_class_gid_for_node_type(node_type, cur)
    if not class_gid:
        return []
    ancestors = get_ancestor_gids(class_gid, cur)
    ph = ','.join(['%s'] * len(ancestors))
    cur.execute(
        f"SELECT a.*, p.name AS prop_name, p.label_zh AS prop_label,"
        f" tc.node_type_binding AS child_nt"
        f" FROM workmanship_onto_axioms a"
        f" LEFT JOIN workmanship_onto_properties p ON p.gid=a.property_gid"
        f" LEFT JOIN workmanship_onto_classes tc ON tc.gid=a.target_gid"
        f" WHERE a.class_gid IN ({ph})"
        f" AND a.axiom_type IN ('minCardinality','maxCardinality','exactCardinality')",
        ancestors
    )
    axioms = [dict(r) for r in cur.fetchall()]
    violations = []
    for ax in axioms:
        child_nt = ax.get('child_nt')
        if not child_nt:
            continue
        try:
            threshold = int(ax['expression'])
        except (TypeError, ValueError):
            continue
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM workmanship_bop_bop_entries"
            " WHERE parent_gid=%s AND node_type=%s AND deleted_at IS NULL",
            (entry_gid, child_nt)
        )
        count = dict(cur.fetchone())['cnt']
        msg = None
        if ax['axiom_type'] == 'minCardinality' and count < threshold:
            msg = f"{ax.get('prop_label') or child_nt} 至少需要 {threshold} 个（当前 {count}）"
        elif ax['axiom_type'] == 'maxCardinality' and count > threshold:
            msg = f"{ax.get('prop_label') or child_nt} 最多允许 {threshold} 个（当前 {count}）"
        elif ax['axiom_type'] == 'exactCardinality' and count != threshold:
            msg = f"{ax.get('prop_label') or child_nt} 必须恰好 {threshold} 个（当前 {count}）"
        if msg:
            violations.append({
                "type": "cardinality", "message": msg,
                "child_node_type": child_nt, "required": threshold,
                "actual": count, "enforcement_level": "mandatory",
            })
    return violations


def consistency_check(entry_gid: str) -> dict:
    """对 BOP 条目执行结构性一致性检查。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT node_type FROM workmanship_bop_bop_entries WHERE gid=%s AND deleted_at IS NULL",
                (entry_gid,)
            )
            row = cur.fetchone()
            if not row:
                return {"entry_gid": entry_gid, "valid": False,
                        "violations": [{"message": "条目不存在"}], "warnings": []}
            node_type = dict(row)['node_type']
            violations = check_cardinality(entry_gid, node_type, cur)
    return {
        "entry_gid": entry_gid, "node_type": node_type,
        "valid": len(violations) == 0,
        "violations": violations, "warnings": [],
    }


def build_agent_schema() -> dict:
    """构建供 Agent session 注入的紧凑世界模型 JSON。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.gid, c.name, c.label_zh, c.node_type_binding, c.parent_gid,
                       c.entity_table, c.is_abstract, c.ai00_level,
                       pc.node_type_binding AS parent_nt
                FROM workmanship_onto_classes c
                LEFT JOIN workmanship_onto_classes pc ON pc.gid=c.parent_gid
                WHERE c.node_type_binding IS NOT NULL ORDER BY c.ai00_level, c.sort_order
            """)
            classes = [dict(r) for r in cur.fetchall()]
            schema = {}
            for cls in classes:
                nt = cls['node_type_binding']
                props = get_inherited_properties(cls['gid'], cur)
                ancestors = get_ancestor_gids(cls['gid'], cur)
                ph = ','.join(['%s'] * len(ancestors))
                cur.execute(
                    f"SELECT name, enforcement_level, expression FROM workmanship_know_craft_rules"
                    f" WHERE context_class_gid IN ({ph}) AND status='active'"
                    f" AND expression IS NOT NULL",
                    ancestors
                )
                rules = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    "SELECT node_type_binding FROM workmanship_onto_classes"
                    " WHERE parent_gid=%s AND node_type_binding IS NOT NULL",
                    (cls['gid'],)
                )
                child_types = [dict(r)['node_type_binding'] for r in cur.fetchall()]
                schema[nt] = {
                    "label":          cls['label_zh'],
                    "parent":         cls.get('parent_nt'),
                    "children":       child_types,
                    "entity_table":   cls.get('entity_table'),
                    "required_props": [p['name'] for p in props if p.get('required')],
                    "optional_props": [p['name'] for p in props if not p.get('required')],
                    "rules": [{"name": r['name'], "level": r['enforcement_level'],
                               "expr": r['expression']} for r in rules],
                }
    return schema
