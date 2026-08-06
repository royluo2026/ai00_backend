"""
backend/ai_assistant/tool_handlers/craft_tools.py
───────────────────────────────────────────────────
工艺相关工具处理器：BOP / PBOM / VPPS 核对 / Auto-Link 等

全部通过云端 REST 调用 backend 自身接口（httpx 直连 127.0.0.1:8080）。
"""
from __future__ import annotations
import os
from typing import Any
from urllib.parse import urlencode
from backend.config import get_settings


from .capability_tools import dispatch_bop_structure


_BASE_URL = os.getenv("AI00_BASE_API_URL", get_settings().internal_backend_base_url).rstrip("/")

TOOL_NAMES: set[str] = {
    "search_parts",
    "list_pbom_snapshots",
    "pbom_vpps_check",
    "apply_rule4_concession",
    "compare_list",
    "list_bop_versions",
    "list_gbop_versions",
    "list_asm_lines",
    "get_bop_entries",
    "search_bop_entries",
    "preview_auto_link",
    "get_bop_link_status",
    "fork_bop_version",
    "run_auto_link",
    "global_search",
}



def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    user_gid: str = "",
    **_kwargs,
) -> Any:
    if tool_name == "search_parts":
        return _search_parts(inputs, auth_token)
    if tool_name == "list_pbom_snapshots":
        return _list_pbom_snapshots(inputs, auth_token)
    if tool_name == "pbom_vpps_check":
        return _pbom_vpps_check(inputs, auth_token)
    if tool_name == "apply_rule4_concession":
        return _apply_rule4_concession(inputs, auth_token)
    if tool_name == "compare_list":
        return _compare_list(inputs, auth_token)
    if tool_name == "list_bop_versions":
        return _list_bop_versions(inputs, auth_token)
    if tool_name == "list_gbop_versions":
        return _list_gbop_versions(inputs, auth_token)
    if tool_name == "list_asm_lines":
        return _list_asm_lines(inputs, user_gid=user_gid, auth_mode=auth_mode)
    if tool_name == "get_bop_entries":
        return _get_bop_entries(inputs, user_gid=user_gid, auth_mode=auth_mode)
    if tool_name == "search_bop_entries":
        return _search_bop_entries(inputs, auth_token)
    if tool_name == "preview_auto_link":
        return _preview_auto_link(inputs, auth_token)
    if tool_name == "get_bop_link_status":
        return _get_bop_link_status(inputs, auth_token)
    if tool_name == "fork_bop_version":
        return _fork_bop_version(inputs, auth_token)
    if tool_name == "run_auto_link":
        return _run_auto_link(inputs, auth_token)
    if tool_name == "global_search":
        return _global_search(inputs, auth_token)
    return {"error": f"craft_tools: 未知工具 {tool_name}"}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(path: str, auth_token: str) -> dict | None:
    try:
        import httpx
        headers = {"X-AI00-Token": auth_token} if auth_token else {}
        resp = httpx.get(f"{_BASE_URL}{path}", headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return None


def _post(path: str, body: dict, auth_token: str) -> dict:
    try:
        import httpx
        headers = {
            "Content-Type": "application/json",
            **({"X-AI00-Token": auth_token} if auth_token else {}),
        }
        resp = httpx.post(f"{_BASE_URL}{path}", json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ── 实现 ───────────────────────────────────────────────────────────────────────

def _search_parts(inputs: dict, auth_token: str) -> dict:
    keyword      = inputs.get("keyword", "")
    limit        = int(inputs.get("limit", 50))
    snapshot_gid = inputs.get("snapshot_gid")
    qs_params: dict = {"limit": limit}
    if keyword:      qs_params["q"] = keyword
    if snapshot_gid: qs_params["snapshot_gid"] = snapshot_gid
    cloud_data = _get(f"/api/bop/pbom/search?{urlencode(qs_params)}", auth_token)
    if cloud_data is None:
        return {"error": "查询云端 PBOM 失败，请检查后端服务是否运行或 snapshot_gid 是否正确"}
    rows = cloud_data.get("data") or []
    return {"parts": rows, "total": len(rows)}


def _list_pbom_snapshots(inputs: dict, auth_token: str) -> dict:
    limit       = int(inputs.get("limit", 20))
    project_gid = inputs.get("project_gid")
    qs_params: dict = {"limit": limit}
    if project_gid: qs_params["project_gid"] = project_gid
    cloud_data = _get(f"/api/bop/pbom-snapshots?{urlencode(qs_params)}", auth_token)
    if cloud_data is None:
        return {"error": "获取 PBOM 快照失败，请检查云端连接"}
    rows = cloud_data.get("data") or []
    return {"snapshots": rows, "total": len(rows)}


def _pbom_vpps_check(inputs: dict, auth_token: str) -> dict:
    snapshot_gid = (inputs.get("snapshot_gid") or "").strip()
    if not snapshot_gid:
        return {"error": "请提供 snapshot_gid（可先调用 list_pbom_snapshots 查询可用快照）"}
    result = _get(f"/api/ebom/vpps_check?{urlencode({'snapshot_gid': snapshot_gid})}", auth_token)
    if result is None:
        return {"error": "VPPS 核对请求失败，请检查后端服务或 snapshot_gid 是否正确"}
    summary  = result.get("summary", {})
    snap     = result.get("snapshot", {})
    r4_ign   = summary.get("rule4_ignored", 0)
    r4_ign_s = f"，已让步 {r4_ign} 条" if r4_ign else ""
    critical_errors = (
        summary.get("rule1_errors", 0) + summary.get("rule2_errors", 0) + summary.get("rule3_errors", 0)
    )
    lines = [
        f"**PBOM 快照**：{snap.get('version_tag','')} {snap.get('name','')}",
        f"总零件数：{summary.get('total_parts',0)}，有VPPS：{summary.get('parts_with_vpps',0)}",
        f"规则1（主数据）：{summary.get('rule1_errors',0)} 个错误",
        f"规则2（父级一致性）：{summary.get('rule2_errors',0)} 个错误",
        f"规则3（层级前缀）：{summary.get('rule3_errors',0)} 个错误",
        f"规则4（紧固件主件）：{summary.get('rule4_errors',0)} 个错误{r4_ign_s}",
        f"核对结果：{'✅ 全部通过' if summary.get('ok') else '⚠️ 存在问题，见下方错误列表'}",
    ]
    for rule_key, rule_errors in result.get("errors", {}).items():
        if rule_errors:
            lines.append(f"\n**{rule_key.upper()} 错误（{len(rule_errors)} 条）**：")
            for e in rule_errors[:20]:
                lines.append(f"  行{e.get('row','')} [{e.get('vpps','')}] {e.get('msg','')}")
            if len(rule_errors) > 20:
                lines.append(f"  …（共 {len(rule_errors)} 条，仅展示前 20）")
    total_errors = sum(
        summary.get(k, 0) for k in ("rule1_errors", "rule2_errors", "rule3_errors", "rule4_errors")
    )
    rule4_flag = "yes" if summary.get("rule4_errors", 0) > 0 else ""
    nok_items = []
    for rule_key, rule_errors in result.get("errors", {}).items():
        for e in rule_errors[:30]:
            nok_items.append({
                "level": "error" if rule_key != "rule4" else "warn",
                "label": f"[{e.get('vpps','')}] {e.get('msg','')}",
                "desc":  f"行{e.get('row','')} · {rule_key.upper()}",
            })
    return {
        "text":              "\n".join(lines),
        "errors":            total_errors,
        "critical_errors":   critical_errors,
        "ok":                bool(summary.get("ok", False)),
        "nok_items":         nok_items,
        "snapshot_gid":      snapshot_gid,
        "rule4_flag":        rule4_flag,
        "rule4_errors_count": summary.get("rule4_errors", 0),
    }


def _apply_rule4_concession(inputs: dict, auth_token: str) -> dict:
    action = (inputs.get("rule4_action") or "apply").strip()
    if action == "skip":
        return {"text": "已选择跳过规则4处理，继续流程（rule4 错误未写入让步表）", "skipped": True, "created": 0}
    snapshot_gid = (inputs.get("snapshot_gid") or "").strip()
    if not snapshot_gid:
        return {"error": "缺少 snapshot_gid"}
    check = _get(f"/api/ebom/vpps_check?{urlencode({'snapshot_gid': snapshot_gid})}", auth_token)
    if check is None:
        return {"error": "获取规则4错误列表失败，请确认后端服务运行中"}
    rule4_errors = check.get("errors", {}).get("rule4", [])
    rows = [
        {"pbom_row_gid": e["gid"], "original_vpps_desc": e.get("vpps_desc", "")}
        for e in rule4_errors if e.get("gid")
    ]
    if not rows:
        return {"text": "当前无规则4错误（或所有错误行已让步），无需写入让步表", "created": 0}
    body = {"pbom_version_gid": snapshot_gid, "rows": rows}
    res  = _post("/api/vpps-operations/rule4-bulk-ignore", body, auth_token)
    if "error" in res:
        return res
    created = res.get("created", 0)
    return {"text": f"规则4让步完成：{created} 条记录已写入让步表", "created": created}


def _compare_list(inputs: dict, auth_token: str) -> dict:
    list_type  = inputs.get("list_type", "").strip()
    base_gid   = inputs.get("base_gid", "").strip()
    target_gid = inputs.get("target_gid", "").strip()
    if not base_gid or not target_gid:
        return {"error": "请提供 base_gid 和 target_gid"}
    qs = urlencode({"base_gid": base_gid, "target_gid": target_gid})
    if list_type == "pbom":
        result = _get(f"/api/ebom/diff?{qs}", auth_token)
    elif list_type == "bop":
        result = _get(f"/api/bop/diff?{qs}", auth_token)
    else:
        return {"error": f"不支持的清单类型: {list_type}，可选 pbom / bop"}
    if result is None:
        return {"error": "对比请求失败，请检查版本 GID 是否正确"}
    return result


def _list_bop_versions(inputs: dict, auth_token: str) -> dict:
    params: dict = {}
    if inputs.get("project_gid"):        params["project_gid"] = inputs["project_gid"]
    if inputs.get("factory_gid"):        params["factory_gid"] = inputs["factory_gid"]
    if inputs.get("include_archived"):   params["include_archived"] = "true"
    qs = ("?" + urlencode(params)) if params else ""
    result = _get(f"/api/bop/versions{qs}", auth_token)
    if result is None:
        return {"error": "BOP 版本列表查询失败，请确认已登录飞书模式"}
    versions = result.get("data", [])
    if not versions:
        return {"text": "当前没有 BOP 工艺版本记录。", "data": []}
    lines = [f"共 {len(versions)} 个 BOP 版本：\n"]
    for v in versions:
        status_map = {"active": "活动", "baseline": "基线", "M": "发布", "archived": "归档"}
        status = status_map.get(v.get("status", ""), v.get("status", ""))
        takt   = v.get("takt_time")
        takt_s = f"  节拍 {takt}s" if takt else ""
        lines.append(
            f"- **{v.get('bop_name','')}** `{v.get('version_tag','')}` [{status}]{takt_s}  \n"
            f"  GID: `{v.get('gid','')}`"
        )
    return {"text": "\n".join(lines), "data": versions}


def _list_gbop_versions(inputs: dict, auth_token: str) -> dict:
    params: dict = {}
    if inputs.get("factory_gid"):      params["factory_gid"] = inputs["factory_gid"]
    if inputs.get("include_archived"): params["include_archived"] = "true"
    qs = ("?" + urlencode(params)) if params else ""
    result = _get(f"/api/gbop/versions{qs}", auth_token)
    if result is None:
        return {"error": "GBOP 版本列表查询失败，请确认已登录飞书模式"}
    versions = result.get("data", [])
    return {"text": f"共 {len(versions)} 个GBOP版本", "data": versions}


def _list_asm_lines(inputs: dict, *, user_gid: str, auth_mode: str) -> dict:
    if not user_gid:
        return {"error": "用户身份缺失，不能访问 BOP 能力"}
    result = dispatch_bop_structure(inputs, user_gid=user_gid, auth_mode=auth_mode)
    if result.get("error"):
        return result
    nodes = result.get("data", {}).get("nodes", [])
    lines = [node for node in nodes if node.get("kind") == "line_process"]
    return {"text": f"共 {len(lines)} 条线体", "data": lines, "evidence": result.get("evidence", []), "source": "capability"}


def _get_bop_entries(inputs: dict, *, user_gid: str, auth_mode: str) -> dict:
    if not user_gid:
        return {"error": "用户身份缺失，不能访问 BOP 能力"}
    try:
        return dispatch_bop_structure(inputs, user_gid=user_gid, auth_mode=auth_mode)
    except Exception as exc:
        return {"error": str(exc), "source": "capability"}


def _search_bop_entries(inputs: dict, auth_token: str) -> dict:
    q = inputs.get("q", "").strip()
    if not q:
        return {"error": "请提供搜索关键词 q"}
    params: dict = {"q": q, "limit": inputs.get("limit", 50)}
    if inputs.get("node_types"): params["node_types"] = inputs["node_types"]
    result = _get(f"/api/bop/entries/search?{urlencode(params)}", auth_token)
    if result is None:
        return {"error": "BOP 条目搜索失败"}
    entries = result.get("data", [])
    if not entries:
        return {"text": f"未找到与「{q}」相关的 BOP 工艺条目。", "data": []}
    lines = [f"搜索「{q}」，找到 {len(entries)} 条结果：\n"]
    for e in entries:
        vpps_str = f" `{e['vpps']}`" if e.get("vpps") else ""
        version  = (e.get("bop_version_gid") or "")[:8]
        lines.append(f"- [{e.get('node_type','')}]{vpps_str} {e.get('title','')}  _(版本 {version}...)_")
    return {"text": "\n".join(lines), "data": entries}


def _preview_auto_link(inputs: dict, auth_token: str) -> dict:
    version_gid = inputs.get("version_gid", "").strip()
    if not version_gid:
        return {"error": "请提供 version_gid"}
    result = _get(f"/api/bop/versions/{version_gid}/auto-link-preview", auth_token)
    if result is None:
        return {"error": "Auto-Link 预览失败，请确认已登录飞书模式且版本 GID 正确"}
    data    = result.get("data", {})
    summary = {k: data.get(k, 0) for k in ("total", "pending", "skip", "warn")}
    text    = (
        f"共 {summary['total']} 个待匹配条目："
        f"待匹配 {summary['pending']}，跳过 {summary['skip']}，警告 {summary['warn']}"
    )
    return {"text": text, "summary": summary, "items": data.get("items", []),
            "warn_count": summary["warn"], "pending": summary["pending"]}


def _get_bop_link_status(inputs: dict, auth_token: str) -> dict:
    version_gid = inputs.get("version_gid", "").strip()
    if not version_gid:
        return {"error": "请提供 version_gid"}
    summary_result = _get(f"/api/bop/versions/{version_gid}/link-summary", auth_token)
    if summary_result is None:
        return {"error": "关联状态查询失败"}
    raw_data = summary_result.get("data", [])
    items    = raw_data if isinstance(raw_data, list) else list(raw_data.values())
    linked   = sum(1 for it in items if it.get("is_valid"))
    stale    = sum(1 for it in items if not it.get("is_valid"))
    preview  = _get(f"/api/bop/versions/{version_gid}/auto-link-preview", auth_token)
    missing  = (preview or {}).get("data", {}).get("pending", 0)
    text     = f"关联状态：linked {linked}，stale {stale}，missing {missing}"
    return {"text": text, "stats": {"linked": linked, "stale": stale, "missing": missing}, "items": items[:50]}


def _fork_bop_version(inputs: dict, auth_token: str) -> dict:
    source_gid = inputs.get("source_gid", "").strip()
    if not source_gid:
        return {"error": "请提供 source_gid（工厂模板版本 GID）"}
    body: dict = {"target_version_tag": inputs.get("target_version_tag", "v1.0")}
    if inputs.get("target_bop_name"): body["target_bop_name"] = inputs["target_bop_name"]
    if inputs.get("project_gid"):     body["project_gid"]     = inputs["project_gid"]
    result  = _post(f"/api/bop/versions/{source_gid}/fork", body, auth_token)
    if "error" in result:
        return result
    new_ver = result.get("data", result)
    return {
        "text":        f"Fork 成功，新版本 GID: {new_ver.get('gid', '')}",
        "gid":         new_ver.get("gid", ""),
        "version_tag": new_ver.get("version_tag", ""),
        "bop_name":    new_ver.get("bop_name", ""),
    }


def _run_auto_link(inputs: dict, auth_token: str) -> dict:
    version_gid = inputs.get("version_gid", "").strip()
    if not version_gid:
        return {"error": "请提供 version_gid"}
    body   = {"step": inputs.get("step", "all"), "mode": inputs.get("mode", "incremental")}
    result = _post(f"/api/bop/versions/{version_gid}/auto-link", body, auth_token)
    if "error" in result:
        return result
    data  = result.get("data", {})
    stats = data.get("stats", {})
    text  = (
        f"Auto-Link 完成："
        f"ok {stats.get('ok',0)}，skip {stats.get('skip',0)}，"
        f"warn {stats.get('warn',0)}，error {stats.get('error',0)}"
    )
    return {"text": text, "stats": stats, "items": (data.get("items") or [])[:20]}


def _global_search(inputs: dict, auth_token: str) -> dict:
    """全局搜索：对齐 Ctrl+O 的搜索范围，同时查 BOP/任务/问题/知识库/规则。"""
    q = inputs.get("q", "").strip()
    if not q:
        return {"error": "请提供搜索关键词 q"}
    cats = [c.strip() for c in inputs.get("categories", "").split(",") if c.strip()] \
           or ["bop", "task", "issue", "knowledge", "rule"]
    limit = min(int(inputs.get("limit") or 5), 20)
    results: dict[str, list] = {}

    if "bop" in cats:
        r = _get(f"/api/bop/versions?q={urlencode({'q': q, 'limit': limit})}", auth_token)
        results["bop_versions"] = r.get("data", []) if r else []
        # 同时搜 BOP 工序条目
        r = _get(f"/api/bop/entries/search?q={q}&limit={limit}", auth_token)
        results["bop_entries"] = r.get("data", []) if r else []

    if "task" in cats:
        r = _get(f"/api/tasks?q={q}&page_size={limit}", auth_token)
        results["tasks"] = r.get("data", []) if r else []

    if "issue" in cats:
        r = _get(f"/api/issues?q={q}&page_size={limit}", auth_token)
        results["issues"] = r.get("data", []) if r else []

    if "knowledge" in cats:
        r = _get(f"/api/knowledge_hub/items?q={q}&limit={limit}", auth_token)
        results["knowledge"] = r if isinstance(r, list) else (r.get("data", []) if r else [])

    if "rule" in cats:
        r = _get(f"/api/rules?q={q}&limit={limit}", auth_token)
        results["rules"] = r.get("data", []) if r else []

    if "feishu" in cats:
        # 飞书联系人/群/文档 — 后端会自动用当前用户的飞书 token
        for path, key in [
            (f"/feishu/search/users?q={q}&limit={limit}", "feishu_users"),
            (f"/feishu/search/chats?q={q}&limit={limit}", "feishu_chats"),
            (f"/feishu/search/docs?q={q}&limit={limit}",  "feishu_docs"),
        ]:
            r = _get(path, auth_token)
            results[key] = r.get("data", []) if r else []

    total = sum(len(v) for v in results.values())
    lines = [f"全局搜索「{q}」共 {total} 条结果："]
    for cat, items in results.items():
        if not items:
            continue
        lines.append(f"\n**{cat}**（{len(items)} 条）")
        for it in items[:limit]:
            title = it.get("title") or it.get("name") or it.get("bop_name") or ""
            gid   = it.get("gid", "")
            lines.append(f"  - {title}  `{gid}`")
    return {"text": "\n".join(lines), "data": results, "total": total}

