"""
backend/ai_assistant/tool_handlers/knowledge_tools.py
──────────────────────────────────────────────────────
知识库 / 规则 / 相似案例 / 聚合统计 / 规则核查 / 最佳实践 工具处理器
"""
from __future__ import annotations
import datetime
from typing import Any

from backend.db.connection import get_conn

TOOL_NAMES: set[str] = {
    "search_knowledge",
    "get_knowledge_entry",
    "list_rules",
    "find_similar_cases",
    "aggregate_history",
    "check_rules",
    "recommend_practice",
    "get_ontology_schema",
    "audit_entry_rules",
    "get_entry_relations",
}


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    **_kwargs,
) -> Any:
    if tool_name == "search_knowledge":
        return _search_knowledge(**inputs)
    if tool_name == "get_knowledge_entry":
        return _get_knowledge_entry(inputs.get("gid", ""))
    if tool_name == "list_rules":
        return _list_rules(**inputs)
    if tool_name == "find_similar_cases":
        return _find_similar_cases(**inputs)
    if tool_name == "aggregate_history":
        return _aggregate_history(**inputs)
    if tool_name == "check_rules":
        return _check_rules(**inputs)
    if tool_name == "recommend_practice":
        return _recommend_practice(**inputs)
    if tool_name == "get_ontology_schema":
        return _get_ontology_schema(**inputs)
    if tool_name == "audit_entry_rules":
        return _audit_entry_rules(**inputs)
    if tool_name == "get_entry_relations":
        return _get_entry_relations(**inputs)
    return {"error": f"knowledge_tools: 未知工具 {tool_name}"}


# ── 原有工具 ───────────────────────────────────────────────────────────────────

def _search_knowledge(keyword: str = "", limit: int = 10) -> dict:
    limit = min(int(limit or 10), 50)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT gid, title, tags
                    FROM knowledge.knowledge_entries
                    WHERE title ILIKE %s
                    ORDER BY created_at DESC LIMIT %s
                """, (f"%{keyword}%", limit))
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        text = f"知识库搜索「{keyword}」：{len(items)} 条\n" + "\n".join(
            f"  {r['title']} [{r['gid']}]" for r in items
        )
        return {"text": text, "items": items}
    except Exception as e:
        return {"error": str(e)}


def _get_knowledge_entry(gid: str) -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM knowledge.knowledge_entries WHERE gid=%s", (gid,)
                )
                row = cur.fetchone()
        if not row:
            return {"error": f"知识条目不存在：{gid}"}
        return {"text": f"知识条目：{row['title']}", "data": dict(row)}
    except Exception as e:
        return {"error": str(e)}


def _list_rules(status: str = "", rule_type: str = "", limit: int = 20) -> dict:
    conditions: list = []
    params: list = []
    if status:
        conditions.append("status=%s"); params.append(status)
    if rule_type:
        conditions.append("rule_type=%s"); params.append(rule_type)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    limit = min(int(limit or 20), 100)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT gid, title, status, rule_type FROM knowledge.craft_rules "
                    f"{where} ORDER BY created_at DESC LIMIT %s",
                    params + [limit],
                )
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        text = f"规则列表（{len(items)} 条）：\n" + "\n".join(
            f"  [{r.get('status', '')}] {r.get('title', '')} [{r.get('gid', '')}]"
            for r in items
        )
        return {"text": text, "items": items}
    except Exception as e:
        return {"error": str(e)}


# ── Phase 3：语义相似案例检索 ──────────────────────────────────────────────────

def _find_similar_cases(
    query: str = "",
    item_types: list | None = None,
    limit: int = 5,
) -> dict:
    """
    在任务/问题/知识库中搜索相似历史案例。
    无 pgvector 时退化为 ILIKE 多字段关键词搜索。
    返回含 similarity_score 字段（关键词匹配时固定0.7）。
    """
    if not query:
        return {"error": "query 不能为空"}

    types = item_types if item_types else ["issue", "task", "knowledge"]
    limit = min(int(limit or 5), 30)
    kw = f"%{query}%"
    results: list[dict] = []

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 问题库
                if "issue" in types:
                    cur.execute("""
                        SELECT gid, title, description, status, severity,
                               'issue' AS item_type
                        FROM work.issues
                        WHERE title ILIKE %s OR description ILIKE %s
                        ORDER BY created_at DESC LIMIT %s
                    """, (kw, kw, limit))
                    for r in cur.fetchall():
                        d = dict(r); d["similarity_score"] = 0.7
                        results.append(d)

                # 任务库
                if "task" in types:
                    cur.execute("""
                        SELECT gid, title, description, status, priority,
                               'task' AS item_type
                        FROM work.tasks
                        WHERE title ILIKE %s OR description ILIKE %s
                        ORDER BY created_at DESC LIMIT %s
                    """, (kw, kw, limit))
                    for r in cur.fetchall():
                        d = dict(r); d["similarity_score"] = 0.7
                        results.append(d)

                # 知识库
                if "knowledge" in types:
                    cur.execute("""
                        SELECT gid, title, entry_type, tags,
                               'knowledge' AS item_type
                        FROM knowledge.knowledge_entries
                        WHERE title ILIKE %s
                        ORDER BY created_at DESC LIMIT %s
                    """, (kw, kw, limit))
                    for r in cur.fetchall():
                        d = dict(r); d["similarity_score"] = 0.75
                        results.append(d)

        # 按 similarity_score 降序，总数截取 limit
        results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        results = results[:limit]

        text = f"相似案例检索「{query}」：{len(results)} 条\n" + "\n".join(
            f"  [{r['item_type']}] {r.get('title', '')} (score={r['similarity_score']:.2f})"
            for r in results
        )
        return {
            "text":        text,
            "items":       results,
            "total":       len(results),
            "search_mode": "keyword",
        }
    except Exception as e:
        return {"error": str(e)}


# ── Phase 3：历史聚合统计 ───────────────────────────────────────────────────────

def _aggregate_history(
    item_type: str = "task",
    group_by: str = "status",
    filter_status: str | None = None,
    date_range: str | None = None,
) -> dict:
    """
    对任务或问题做 GROUP BY 聚合统计。
    group_by: status|priority|severity|created_week
    """
    table_map = {"task": "work.tasks", "issue": "work.issues"}
    table = table_map.get(item_type)
    if not table:
        return {"error": f"item_type 必须是 task 或 issue"}

    # 分组字段
    valid_groups = {"status", "priority", "severity", "created_week"}
    if group_by not in valid_groups:
        group_by = "status"

    if group_by == "created_week":
        select_col = "date_trunc('week', created_at) AS group_key"
    else:
        select_col = f"{group_by} AS group_key"

    conditions: list[str] = []
    params: list = []

    if filter_status:
        conditions.append("status = %s")
        params.append(filter_status)

    if date_range:
        days_map = {"7d": 7, "30d": 30, "90d": 90}
        days = days_map.get(date_range, 30)
        conditions.append("created_at >= NOW() - INTERVAL '%s days'")
        params.append(days)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {select_col}, COUNT(*) AS cnt "
                    f"FROM {table} {where} "
                    f"GROUP BY group_key ORDER BY cnt DESC",
                    params,
                )
                rows = cur.fetchall()

        aggregates: dict[str, int] = {}
        total = 0
        for r in rows:
            key = r["group_key"]
            if hasattr(key, "isoformat"):
                key = key.isoformat()
            key = str(key) if key is not None else "null"
            cnt = int(r["cnt"])
            aggregates[key] = cnt
            total += cnt

        text = (
            f"{item_type} 按 {group_by} 聚合（共 {total} 条）：\n"
            + "\n".join(f"  {k}: {v}" for k, v in aggregates.items())
        )
        return {"text": text, "aggregates": aggregates, "total": total}
    except Exception as e:
        return {"error": str(e)}


# ── Phase 4：规则核查 ──────────────────────────────────────────────────────────

_MANDATORY_KEYWORDS = {"禁止", "必须", "强制", "不得", "严禁"}
_ADVISORY_KEYWORDS  = {"建议", "推荐", "宜", "应", "应当"}

def _infer_rule_strength(title: str, content: str = "") -> str:
    text = (title or "") + " " + (content or "")
    if any(kw in text for kw in _MANDATORY_KEYWORDS):
        return "mandatory"
    if any(kw in text for kw in _ADVISORY_KEYWORDS):
        return "advisory"
    return "reference"


def _check_rules(
    scenario: str = "",
    part_no: str | None = None,
    operation_type: str | None = None,
    limit: int = 10,
) -> dict:
    """
    检索适用于指定场景的工艺规则，推断 rule_strength，返回置信度。
    置信度基于匹配字段数量：场景命中+零件号命中+类型命中 → 越多越高。
    """
    if not scenario:
        return {"error": "scenario 不能为空"}

    limit = min(int(limit or 10), 50)
    kw = f"%{scenario}%"

    conditions = ["(title ILIKE %s OR rule_definition::text ILIKE %s)"]
    params: list = [kw, kw]

    if operation_type:
        conditions.append("rule_type ILIKE %s")
        params.append(f"%{operation_type}%")

    where = "WHERE " + " AND ".join(conditions)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT gid, title, status, rule_type, rule_definition, enforcement_level "
                    f"FROM knowledge.craft_rules {where} "
                    f"ORDER BY created_at DESC LIMIT %s",
                    params + [limit],
                )
                rows = cur.fetchall()

        rules = []
        max_conf = 0.0
        for r in rows:
            rd = dict(r)
            title   = rd.get("title", "")
            enf     = rd.get("enforcement_level", "")
            content = str(rd.get("rule_definition") or "")

            # 推断强度
            if enf == "mandatory":
                strength = "mandatory"
                conf = 0.95
            elif enf == "advisory":
                strength = "advisory"
                conf = 0.85
            else:
                strength = _infer_rule_strength(title, content)
                conf = 0.80 if strength != "reference" else 0.70

            # 零件号加分
            if part_no and part_no in content:
                conf = min(conf + 0.05, 1.0)

            max_conf = max(max_conf, conf)
            rules.append({
                "gid":          rd["gid"],
                "title":        title,
                "status":       rd.get("status", ""),
                "rule_type":    rd.get("rule_type", ""),
                "rule_strength": strength,
                "confidence":   round(conf, 2),
                "basis":        "rule_match",
            })

        text = f"场景「{scenario}」适用规则：{len(rules)} 条\n" + "\n".join(
            f"  [{r['rule_strength']}] {r['title']} (conf={r['confidence']})"
            for r in rules
        )
        return {
            "text":       text,
            "rules":      rules,
            "confidence": round(max_conf, 2) if rules else 0.0,
            "basis":      "rule_match",
        }
    except Exception as e:
        return {"error": str(e)}


# ── Phase 4：最佳实践推荐 ──────────────────────────────────────────────────────

def _recommend_practice(
    scenario: str = "",
    context: str | None = None,
    limit: int = 5,
) -> dict:
    """
    搜索 lesson_learned / guide 类型的知识条目，返回最佳实践推荐。
    """
    if not scenario:
        return {"error": "scenario 不能为空"}

    limit = min(int(limit or 5), 30)
    kw_scene = f"%{scenario}%"

    conditions = [
        "entry_type IN ('lesson_learned', 'guide', 'best_practice')",
        "(title ILIKE %s OR content_md ILIKE %s)",
    ]
    params: list = [kw_scene, kw_scene]

    if context:
        conditions.append("(title ILIKE %s)")
        kw_ctx = f"%{context}%"
        params.extend([kw_ctx])

    where = "WHERE " + " AND ".join(conditions)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT gid, title, entry_type, tags "
                    f"FROM knowledge.knowledge_entries {where} "
                    f"ORDER BY created_at DESC LIMIT %s",
                    params + [limit],
                )
                rows = cur.fetchall()

        practices = []
        for r in rows:
            rd = dict(r)
            practices.append({
                "gid":        rd["gid"],
                "title":      rd.get("title", ""),
                "entry_type": rd.get("entry_type", ""),
                "tags":       rd.get("tags") or [],
                "confidence": 0.78,
                "basis":      "soft_match",
            })

        text = f"场景「{scenario}」最佳实践：{len(practices)} 条\n" + "\n".join(
            f"  [{r['entry_type']}] {r['title']}" for r in practices
        )
        conf = 0.78 if practices else 0.0
        return {
            "text":       text,
            "practices":  practices,
            "confidence": conf,
            "basis":      "soft_match",
        }
    except Exception as e:
        return {"error": str(e)}


# ── 本体工具 ───────────────────────────────────────────────────────────────────

def _get_ontology_schema(node_type: str) -> dict:
    """返回某个 node_type 的本体字段定义 + 约束 + CEL 规则。"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 找绑定该 node_type 的类
                cur.execute(
                    "SELECT gid, name, label_zh, description FROM knowledge.onto_classes"
                    " WHERE node_type_binding = %s LIMIT 1",
                    (node_type,),
                )
                cls = cur.fetchone()
                if not cls:
                    return {"error": f"本体中未找到 node_type='{node_type}' 的类定义，请先执行 Seed"}

                # 递归获取祖先 gid 列表
                cur.execute("SELECT gid, parent_gid FROM knowledge.onto_classes")
                class_map = {r["gid"]: dict(r) for r in cur.fetchall()}

                def get_ancestors(gid):
                    result, seen = [], set()
                    cur_gid = gid
                    while cur_gid and cur_gid not in seen:
                        seen.add(cur_gid); result.append(cur_gid)
                        cur_gid = class_map.get(cur_gid, {}).get("parent_gid")
                    return result

                ancestor_gids = get_ancestors(cls["gid"])

                # 数据属性（含继承）
                cur.execute(
                    "SELECT p.name, p.label_zh, p.data_type, p.required,"
                    "       p.min_val, p.max_val, p.description, p.storage_hint,"
                    "       c.label_zh AS class_label"
                    " FROM knowledge.onto_properties p"
                    " JOIN knowledge.onto_classes c ON c.gid = p.class_gid"
                    " WHERE p.class_gid = ANY(%s) AND p.prop_kind='data'"
                    " ORDER BY p.sort_order",
                    (ancestor_gids,),
                )
                props = [dict(r) for r in cur.fetchall()]

                # CEL 规则
                cur.execute(
                    "SELECT name, expression, enforcement_level"
                    " FROM knowledge.craft_rules"
                    " WHERE context_class_gid = ANY(%s)"
                    "   AND expression IS NOT NULL AND status='active'",
                    (ancestor_gids,),
                )
                rules = [dict(r) for r in cur.fetchall()]

        # 格式化输出
        props_text = "\n".join(
            f"  - {p['label_zh']}（{p['name']}）: {p['data_type']}"
            + (f"，必填" if p['required'] else "")
            + (f"，范围 {p['min_val']}~{p['max_val']}" if p['min_val'] is not None or p['max_val'] is not None else "")
            + (f"，{p['description']}" if p['description'] else "")
            for p in props
        ) or "  （暂无定义）"

        rules_text = "\n".join(
            f"  - [{r['enforcement_level']}] {r['name']}: `{r['expression']}`"
            for r in rules
        ) or "  （暂无 CEL 规则）"

        return {
            "node_type":   node_type,
            "class_label": cls["label_zh"],
            "properties":  props,
            "rules":       rules,
            "summary": (
                f"**{cls['label_zh']}**（{node_type}）\n\n"
                f"**数据属性（{len(props)} 个）：**\n{props_text}\n\n"
                f"**工艺规则（{len(rules)} 条）：**\n{rules_text}"
            ),
        }
    except Exception as e:
        return {"error": str(e)}


def _audit_entry_rules(entry_gid: str, node_type: str = "") -> dict:
    """对 BOP 条目执行全量规则审计，返回未通过的规则。"""
    try:
        # 若未传 node_type，从数据库查
        if not node_type:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT node_type FROM bop.bop_entries WHERE gid=%s", (entry_gid,)
                    )
                    row = cur.fetchone()
                    if not row:
                        return {"error": f"未找到 bop_entry gid={entry_gid}"}
                    node_type = row["node_type"]

        from backend.rule_engine.checker import check_entry_rules
        violations = check_entry_rules(node_type, entry_gid)

        if not violations:
            return {
                "entry_gid": entry_gid,
                "node_type": node_type,
                "passed":    True,
                "summary":   f"✅ 条目 {entry_gid}（{node_type}）所有规则均通过",
                "violations": [],
            }

        lines = [f"  - [{v['enforcement_level']}] {v['rule_name']}：{v['message']}" for v in violations]
        return {
            "entry_gid":  entry_gid,
            "node_type":  node_type,
            "passed":     False,
            "violations": violations,
            "summary": (
                f"⚠️ 条目 {entry_gid}（{node_type}）有 {len(violations)} 条规则未通过：\n"
                + "\n".join(lines)
            ),
        }
    except Exception as e:
        return {"error": str(e)}


def _get_entry_relations(entry_gid: str, rel_type: str = "") -> dict:
    """通过本体语义查询 BOP 条目的所有实例级关联。"""

    _TITLE_QUERY: dict[str, str] = {
        "physical_station":   "SELECT gid, name AS title FROM factory.factory_stations WHERE gid=ANY(%s)",
        "physical_equipment": "SELECT gid, asset_no AS title FROM factory.factory_equipments WHERE gid=ANY(%s)",
        "physical_tool":      "SELECT gid, asset_no AS title FROM factory.factory_tools WHERE gid=ANY(%s)",
        "physical_fixture":   "SELECT gid, asset_no AS title FROM factory.factory_fixtures WHERE gid=ANY(%s)",
        "project_equipment":  "SELECT gid, name AS title FROM bop.bop_equipments WHERE gid=ANY(%s)",
        "project_tooling":    "SELECT gid, name AS title FROM bop.bop_fixtures WHERE gid=ANY(%s)",
        "project_tools":      "SELECT gid, name AS title FROM bop.bop_tools WHERE gid=ANY(%s)",
        "project_roles":      "SELECT gid, name AS title FROM bop.project_roles WHERE gid=ANY(%s)",
        "pbom_part":          "SELECT gid, COALESCE(title,'') AS title FROM bop.bop_entries WHERE gid=ANY(%s)",
        "issue":              "SELECT gid, title FROM proj.issues WHERE gid=ANY(%s)",
        "task_std":           "SELECT gid, title FROM proj.tasks WHERE gid=ANY(%s)",
        "task_custom":        "SELECT gid, title FROM proj.tasks WHERE gid=ANY(%s)",
        "knowledge":          "SELECT gid, title FROM knowledge.knowledge_entries WHERE gid=ANY(%s)",
        "rule_std":           "SELECT gid, name AS title FROM knowledge.craft_rules WHERE gid=ANY(%s)",
        "rule_custom":        "SELECT gid, name AS title FROM knowledge.craft_rules WHERE gid=ANY(%s)",
        "asm_operation":      "SELECT gid, name AS title FROM bop.bop_steps WHERE gid=ANY(%s)",
    }

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT node_type, title FROM bop.bop_entries WHERE gid=%s", (entry_gid,))
                entry = cur.fetchone()
                if not entry:
                    return {"error": f"未找到 bop_entry gid={entry_gid}"}
                node_type = entry["node_type"]
                entry_title = entry["title"] or entry_gid

                # 通过本体获取对象属性（含 link_type_binding）
                cur.execute(
                    "SELECT r.name, r.label_zh, r.link_type_binding"
                    " FROM knowledge.onto_relations r"
                    " JOIN knowledge.onto_classes c ON c.gid = r.domain_class_gid"
                    " WHERE c.node_type_binding = %s AND r.link_type_binding IS NOT NULL",
                    (node_type,),
                )
                onto_rels = [dict(r) for r in cur.fetchall()]

                if not onto_rels:
                    return {
                        "entry_gid": entry_gid, "entry_title": entry_title,
                        "node_type": node_type, "relations": {},
                        "summary": f"本体中未找到 {node_type} 的对象属性定义，请先执行 Seed",
                    }

                if rel_type:
                    onto_rels = [r for r in onto_rels if r["name"] == rel_type or r["link_type_binding"] == rel_type]

                all_link_types = list({r["link_type_binding"] for r in onto_rels})
                cur.execute(
                    "SELECT link_type, target_gid FROM bop.bop_entry_links"
                    " WHERE bop_entry_gid=%s AND link_type=ANY(%s) AND is_primary=FALSE",
                    (entry_gid, all_link_types),
                )
                links = cur.fetchall()

                from collections import defaultdict
                grouped: dict[str, list[str]] = defaultdict(list)
                for lk in links:
                    grouped[lk["link_type"]].append(lk["target_gid"])

                entity_names: dict[str, str] = {}
                for lt, gids in grouped.items():
                    sql = _TITLE_QUERY.get(lt)
                    if not sql or not gids:
                        continue
                    cur.execute(sql, (gids,))
                    for row in cur.fetchall():
                        entity_names[row["gid"]] = row["title"] or row["gid"]

        lt_to_label = {r["link_type_binding"]: r["label_zh"] for r in onto_rels}
        relations: dict[str, list[dict]] = {}
        for lt, gids in grouped.items():
            label = lt_to_label.get(lt, lt)
            relations[label] = [{"gid": g, "title": entity_names.get(g, g)} for g in gids]

        if not relations:
            summary = f"条目「{entry_title}」（{node_type}）暂无关联实体。"
        else:
            lines = [f"  - **{label}**：" + "、".join(e["title"] for e in items)
                     for label, items in relations.items()]
            summary = f"条目「{entry_title}」（{node_type}）的关联实体：\n" + "\n".join(lines)

        return {
            "entry_gid": entry_gid, "entry_title": entry_title,
            "node_type": node_type, "relations": relations, "summary": summary,
        }
    except Exception as e:
        return {"error": str(e)}