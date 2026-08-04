"""
backend/rule_engine/graph.py
────────────────────────────
subClassOf 图遍历：从给定类向上遍历祖先链。
"""


def get_ancestor_gids(class_gid: str, class_map: dict) -> list[str]:
    """返回 class_gid 及其所有祖先类的 gid 列表（含自身，由近到远）。

    class_map: {gid: {"gid": ..., "parent_gid": ...}} —— 从 onto_classes 表加载。
    """
    result: list[str] = []
    current = class_gid
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        result.append(current)
        current = class_map.get(current, {}).get("parent_gid")
    return result


def get_applicable_rules(class_gid: str, all_rules: list[dict], class_map: dict) -> list[dict]:
    """返回适用于 class_gid（含祖先类）的所有含 expression 的规则。"""
    ancestors = set(get_ancestor_gids(class_gid, class_map))
    return [
        r for r in all_rules
        if r.get("context_class_gid") in ancestors and r.get("expression")
    ]
