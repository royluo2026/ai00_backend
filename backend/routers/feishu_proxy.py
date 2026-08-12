"""
backend/routers/feishu_proxy.py
─────────────────────────────────
飞书 API 代理：客户端发请求到这里，本服务用 App Secret 调飞书。
客户端永远不接触 App Secret。
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.services.feishu_service import feishu_service
from backend.services import user_service, feishu_cache_service
from backend.routers.deps import get_current_user

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["feishu"])


class SendMessageBody(BaseModel):
    open_id: str
    text: str


@router.post("/message/send")
def send_message(
    body: SendMessageBody,
    _: dict = Depends(get_current_user),
):
    ok = feishu_service.send_message(body.open_id, body.text)
    return {"success": ok}


@router.get("/org/users")
def get_org_users(
    page_token: str = "",
    _: dict = Depends(get_current_user),
):
    data = feishu_service.get_org_users(page_token)
    return {"success": True, "data": data}


@router.get("/calendar/today")
def get_calendar_today(
    date: str = Query(None, description="YYYY-MM-DD，为空时使用今日"),
    current_user: dict = Depends(get_current_user),
):
    """返回当前用户指定日飞书日程列表（用存储的 user_access_token 代理查询）。"""
    token = user_service.get_feishu_token(current_user["gid"])
    if not token:
        return {"success": False, "error": "飞书 token 不可用，请重新登录", "data": []}
    try:
        events = feishu_service.get_calendar_today(token, date=date)
        return {"success": True, "data": events}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


class EventRsvpBody(BaseModel):
    rsvp_status: str  # accept | tentative | decline


@router.patch("/calendar/events/{event_id}/rsvp")
def update_event_rsvp(
    event_id: str,
    body: EventRsvpBody,
    current_user: dict = Depends(get_current_user),
):
    """更新当前用户对某飞书日程的 RSVP 状态。"""
    if body.rsvp_status not in ("accept", "tentative", "decline"):
        return {"success": False, "error": "无效的 rsvp_status"}
    token = user_service.get_feishu_token(current_user["gid"])
    if not token:
        return {"success": False, "error": "飞书 token 不可用"}
    # 从 DB 取当前用户 feishu_open_id（deps.py 故意排除了该字段）
    open_id = ""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT feishu_open_id FROM workmanship_auth_users WHERE gid=%s",
                            (current_user["gid"],))
                row = cur.fetchone()
                open_id = row["feishu_open_id"] if row else ""
    except Exception:
        pass
    if not open_id:
        return {"success": False, "error": "无法获取飞书用户 ID"}
    result = feishu_service.update_event_rsvp(token, event_id, open_id, body.rsvp_status)
    return result


@router.get("/calendar/events/{event_id}")
def get_event_detail(
    event_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取飞书日程详情（organizer 用于编辑表单）。"""
    token = user_service.get_feishu_token(current_user["gid"])
    if not token:
        return {"success": False, "error": "飞书 token 不可用"}
    return feishu_service.get_event_detail(token, event_id)


class EventUpdateBody(BaseModel):
    summary: str | None = None
    description: str | None = None


@router.patch("/calendar/events/{event_id}")
def update_event(
    event_id: str,
    body: EventUpdateBody,
    current_user: dict = Depends(get_current_user),
):
    """更新飞书日程（仅 organizer 可操作）。"""
    token = user_service.get_feishu_token(current_user["gid"])
    if not token:
        return {"success": False, "error": "飞书 token 不可用"}
    fields = {k: v for k, v in body.dict().items() if v is not None}
    if not fields:
        return {"success": False, "error": "无更新内容"}
    return feishu_service.update_event(token, event_id, fields)


# ── 全局搜索端点 ──────────────────────────────────────────────────────────────

def _get_token_or_none(current_user: dict) -> str:
    return user_service.get_feishu_token(current_user["gid"]) or ""


@router.get("/search/users")
def search_feishu_users(
    q: str = Query(""),
    limit: int = Query(8),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
):
    if not q:
        return {"success": True, "data": [], "category": "feishu_user"}

    user_gid   = current_user["gid"]
    user_token = _get_token_or_none(current_user)
    if not user_token:
        return {"success": True, "data": [], "category": "feishu_user"}

    q_lower = q.lower()

    # ── 1. DB 缓存搜索（最快，服务重启后也有效）────────────────────────────────
    cached = feishu_cache_service.search(user_gid, ["contact"], q_lower, limit * 2)
    if cached:
        # 优先返回有 open_id 的真实联系人；没有时才用 p2p 聊天名兜底
        real = [c for c in cached if c.get("open_id")]
        p2p  = [c for c in cached if not c.get("open_id")]
        result = (real or p2p)[:limit]
        # 后台刷新（缓存过期时）
        if feishu_cache_service.needs_refresh(user_gid, "contact") and background_tasks:
            background_tasks.add_task(feishu_cache_service.refresh_contacts, user_gid, user_token)
        return {"success": True, "data": result, "category": "feishu_user"}

    # ── 2. 触发后台建缓存（首次搜索时）──────────────────────────────────────────
    if feishu_cache_service.needs_refresh(user_gid, "contact") and background_tasks:
        background_tasks.add_task(feishu_cache_service.refresh_contacts, user_gid, user_token)

    # ── 3. 实时兜底1：直接调飞书搜索 API（fast，不需要 BFS）──────────────────────
    try:
        live = feishu_service.search_users_by_name(q, page_size=limit, user_access_token=user_token)
        if live:
            to_cache = []
            for u in live:
                oid = u.get("open_id", "")
                if not oid:
                    continue
                to_cache.append({
                    "entity_id":  oid,
                    "name":       u.get("name", "") or "",
                    "search_ext": u.get("email", "") or "",
                    **u,
                })
            if to_cache:
                feishu_cache_service.upsert_many(user_gid, "contact", to_cache)
            return {"success": True, "data": live[:limit], "category": "feishu_user"}
    except Exception as e:
        _log.warning("search_feishu_users live fallback A: %s", e)

    # ── 4. 实时兜底2：从内存全员列表过滤（与 refresh_contacts 同路，30min 内存缓存）──
    try:
        all_users = feishu_service.get_all_users()
        if all_users:
            matched = [u for u in all_users
                       if q_lower in (u.get("name") or "").lower()
                       or q_lower in (u.get("email") or "").lower()]
            if matched:
                return {"success": True, "data": matched[:limit], "category": "feishu_user"}
    except Exception as e:
        _log.warning("search_feishu_users live fallback B: %s", e)

    return {"success": True, "data": [], "category": "feishu_user"}


@router.get("/search/chats")
def search_feishu_chats(
    q: str = Query(""),
    limit: int = Query(8),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
):
    """搜索飞书群聊（使用 /im/v1/chats/search 正式搜索端点）。"""
    if not q:
        return {"success": True, "data": [], "category": "feishu_chat"}

    user_gid   = current_user["gid"]
    user_token = _get_token_or_none(current_user)
    if not user_token:
        return {"success": True, "data": [], "category": "feishu_chat"}

    q_lower = q.lower()
    import re as _re
    # 按中文/英数边界拆 token：'AI00主力' → ['ai00', '主力']
    tokens = []
    for t in q_lower.split():
        parts = _re.findall(r'[a-z0-9_\-]+|[\u4e00-\u9fff]+', t)
        tokens.extend([p for p in parts if len(p) >= 2])
    if not tokens:
        tokens = [q_lower]

    try:
        # /im/v1/chats/search 会同时匹配群名和成员名，需按群名过滤
        chats = feishu_service.search_chats(user_token, query=q, page_size=20, max_pages=3)
        name_hits = [c for c in chats
                     if any(tok in (c.get("name") or "").lower() for tok in tokens)]
        return {"success": True, "data": name_hits[:limit], "category": "feishu_chat"}
    except Exception as e:
        _log.warning("search_feishu_chats: %s", e)
        return {"success": True, "data": [], "category": "feishu_chat"}


@router.get("/search/docs")
def search_feishu_docs(
    q: str = Query(""),
    limit: int = Query(5),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
):
    """搜索飞书云文档（先走 DB 缓存，缓存过期则后台刷新 + 实时搜索）。"""
    if not q:
        return {"success": True, "data": [], "category": "feishu_doc"}

    user_gid   = current_user["gid"]
    user_token = _get_token_or_none(current_user)
    _log.warning("[DOC_SEARCH] q=%r user_gid=%s has_token=%s", q, user_gid[:8] if user_gid else None, bool(user_token))
    if not user_token:
        _log.warning("[DOC_SEARCH] 无 user_token，返回空")
        return {"success": True, "data": [], "category": "feishu_doc"}

    q_lower = q.lower()

    # 有查询词时：始终调飞书实时搜索（缓存 50 条覆盖面太窄，易漏目标文档）
    realtime: list = []
    try:
        realtime = feishu_service.search_docs(user_token, q, limit)
        _log.warning("[DOC_SEARCH] realtime=%d", len(realtime))
    except Exception as e:
        _log.warning("[DOC_SEARCH] search_docs 异常: %s", e)

    # 后台刷新缓存（fire-and-forget，不阻塞响应）
    if feishu_cache_service.needs_refresh(user_gid, "doc") and background_tasks:
        background_tasks.add_task(feishu_cache_service.refresh_docs, user_gid, user_token)

    if realtime:
        return {"success": True, "data": realtime[:limit], "category": "feishu_doc"}

    # 实时搜索无结果时降级到缓存（离线 / scope 缺失场景）
    cached = feishu_cache_service.search(user_gid, ["doc"], q_lower, limit)
    _log.warning("[DOC_SEARCH] cache_fallback=%d", len(cached))
    return {"success": True, "data": cached, "category": "feishu_doc"}


@router.get("/search/events")
def search_feishu_events(
    q: str = Query(""),
    limit: int = Query(5),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
):
    """搜索飞书日程（DB 缓存，TTL 30min）。"""
    if not q:
        return {"success": True, "data": [], "category": "feishu_event"}

    user_gid   = current_user["gid"]
    user_token = _get_token_or_none(current_user)
    if not user_token:
        return {"success": True, "data": [], "category": "feishu_event"}

    q_lower = q.lower()

    cached = feishu_cache_service.search(user_gid, ["event"], q_lower, limit)
    stale  = feishu_cache_service.needs_refresh(user_gid, "event")

    if cached:
        if stale and background_tasks:
            background_tasks.add_task(feishu_cache_service.refresh_events, user_gid, user_token)
        return {"success": True, "data": cached, "category": "feishu_event"}

    # 无缓存 → 同步刷新一次（日程数据量小，直接等）
    feishu_cache_service.refresh_events(user_gid, user_token)
    cached = feishu_cache_service.search(user_gid, ["event"], q_lower, limit)
    return {"success": True, "data": cached, "category": "feishu_event"}


@router.get("/search/meetings")
def search_feishu_meetings(
    q: str = Query(""),
    limit: int = Query(5),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
):
    """搜索飞书会议记录（DB 缓存，TTL 1h）。"""
    if not q:
        return {"success": True, "data": [], "category": "feishu_meeting"}

    user_gid   = current_user["gid"]
    user_token = _get_token_or_none(current_user)
    if not user_token:
        return {"success": True, "data": [], "category": "feishu_meeting"}

    q_lower = q.lower()

    cached = feishu_cache_service.search(user_gid, ["meeting"], q_lower, limit)
    stale  = feishu_cache_service.needs_refresh(user_gid, "meeting")

    if cached:
        if stale and background_tasks:
            background_tasks.add_task(feishu_cache_service.refresh_meetings, user_gid, user_token)
        return {"success": True, "data": cached, "category": "feishu_meeting"}

    # 无缓存 → 后台建缓存（历史会议拉取较慢，不阻塞）
    if background_tasks:
        background_tasks.add_task(feishu_cache_service.refresh_meetings, user_gid, user_token)
    return {"success": True, "data": [], "category": "feishu_meeting"}


@router.get("/cache/debug")
def debug_feishu_cache(
    entity_type: str = Query("chat"),
    q: str = Query(""),
    current_user: dict = Depends(get_current_user),
):
    """调试：查看缓存里有哪些数据，以及搜索词匹配结果。"""
    from backend.db.connection import get_conn
    user_gid = current_user["gid"]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT entity_id, name, search_ext, data, updated_at
                    FROM workmanship_app_feishu_search_cache
                    WHERE user_gid = %s AND entity_type = %s
                    ORDER BY updated_at DESC LIMIT 30
                """, (user_gid, entity_type))
                rows = cur.fetchall()
        items = [{"entity_id": r["entity_id"], "name": r["name"],
                  "open_id_in_data": dict(r["data"]).get("open_id", "ABSENT"),
                  "chat_type_in_data": dict(r["data"]).get("chat_type", "ABSENT"),
                  "updated_at": str(r["updated_at"])} for r in rows]
        matched = [i for i in items if q.lower() in i["name"].lower()] if q else items
        return {"total": len(items), "matched": len(matched), "items": matched[:20]}
    except Exception as e:
        return {"error": str(e)}


@router.post("/cache/refresh")
def refresh_feishu_cache(
    background_tasks: BackgroundTasks,
    entity_type: str = Query("all", description="contact|chat|doc|event|meeting|all"),
    current_user: dict = Depends(get_current_user),
):
    """手动触发缓存刷新（后台异步执行）。"""
    user_gid   = current_user["gid"]
    user_token = _get_token_or_none(current_user)
    if not user_token:
        return {"success": False, "error": "飞书 token 不可用"}

    types = (["contact", "chat", "doc", "event", "meeting"]
             if entity_type == "all" else [entity_type])

    dispatch = {
        "contact": feishu_cache_service.refresh_contacts,
        "chat":    feishu_cache_service.refresh_chats,
        "doc":     feishu_cache_service.refresh_docs,
        "event":   feishu_cache_service.refresh_events,
        "meeting": feishu_cache_service.refresh_meetings,
    }
    for t in types:
        if t in dispatch:
            background_tasks.add_task(dispatch[t], user_gid, user_token)

    return {"success": True, "refreshing": types}


@router.get("/org/dept-search")
def search_feishu_departments(q: str = "", _: dict = Depends(get_current_user)):
    """
    返回飞书部门列表供前端选择器使用。
    无查询词时返回顶级部门；有查询词时在本地 DB teams 表过滤。
    """
    try:
        if not q or not q.strip():
            # 直接返回第一层部门，一次 API 调用，无 BFS
            depts = feishu_service.get_top_level_departments()
            return {"success": True, "data": depts, "warming": False}
        # 有查询词：搜本地 DB
        q_like = f"%{q.strip()}%"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT gid, name, feishu_dept_id FROM workmanship_auth_teams t
                    WHERE name LIKE %s AND feishu_dept_id IS NOT NULL
                    ORDER BY name LIMIT 20
                """, (q_like,))
                rows = cur.fetchall()
        data = [{"open_id": r["feishu_dept_id"], "name": r["name"]} for r in rows]
        return {"success": True, "data": data, "warming": False}
    except Exception as e:
        return {"success": False, "error": str(e), "data": [], "warming": False}


# ── 飞书组织架构同步 ───────────────────────────────────────────────────────────

@router.post("/sync/org/structure")
def sync_feishu_org_structure(_: dict = Depends(get_current_user)):
    """
    仅同步飞书部门（不同步用户），用于第一阶段快速建立部门树。
    用 daemon 线程执行，避免阻塞 uvicorn reload/shutdown。
    """
    import threading
    threading.Thread(target=_do_sync_org_structure, daemon=True, name="sync-org-structure").start()
    return {"success": True, "status": "syncing"}


@router.post("/sync/org")
def sync_feishu_org(_: dict = Depends(get_current_user)):
    """
    将飞书组织架构（部门树 + 成员）同步到 AI00 teams 表。
    用 daemon 线程执行，uvicorn reload/shutdown 不等待。
    """
    import threading
    threading.Thread(target=_do_sync_org, daemon=True, name="sync-org").start()
    return {"success": True, "status": "syncing"}


@router.get("/sync/org/status")
def get_org_sync_status(_: dict = Depends(get_current_user)):
    """返回最近一次组织同步的统计。"""
    try:
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) AS team_count FROM workmanship_auth_teams
                    WHERE feishu_dept_id IS NOT NULL
                """)
                team_count = cur.fetchone()["team_count"]
                cur.execute("""
                    SELECT COUNT(*) AS user_count FROM workmanship_auth_users
                    WHERE feishu_open_id IS NOT NULL AND feishu_open_id != ''
                """)
                user_count = cur.fetchone()["user_count"]
        return {"success": True, "team_count": team_count, "user_count": user_count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/org/users/search")
def search_org_users(
    q: str = Query(""),
    current_user: dict = Depends(get_current_user),
):
    """按姓名搜索飞书用户，结果标注是否已注册到系统（用于组织管理成员选择器）。"""
    if not q.strip():
        return {"success": True, "data": []}
    user_token = user_service.get_feishu_token(current_user["gid"])
    users = feishu_service.search_users_by_name(
        q.strip(), page_size=15, user_access_token=user_token or ""
    )
    if not users:
        return {"success": True, "data": []}
    open_ids = [u["open_id"] for u in users if u.get("open_id")]
    db_map: dict = {}
    if open_ids:
        with get_conn() as conn:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(open_ids))
                cur.execute(
                    f"SELECT gid, feishu_open_id FROM workmanship_auth_users "
                    f"WHERE feishu_open_id IN ({placeholders})",
                    open_ids,
                )
                for r in cur.fetchall():
                    db_map[r["feishu_open_id"]] = r["gid"]
    for u in users:
        u["db_gid"] = db_map.get(u.get("open_id", ""))
    return {"success": True, "data": users}


class ShareListBody(BaseModel):
    chat_id: str
    list_name: str
    share_url: str


@router.post("/chat-message/share-list")
def share_list_to_chat(
    body: ShareListBody,
    current_user: dict = Depends(get_current_user),
):
    """分享清单链接到飞书群"""
    import json as _json
    sender = current_user.get("name", "用户")
    text = f"{sender} 分享了问题清单【{body.list_name}】\n点击查看：{body.share_url}"
    content = _json.dumps({"text": text}, ensure_ascii=False)
    ok = feishu_service.send_message_to_chat(body.chat_id, content)
    return {"success": ok}


def _do_sync_org():
    """后台任务：调用 org_sync_service.sync_all_from_feishu()。"""
    import traceback
    print("[sync_org] 后台任务启动", flush=True)
    try:
        from backend.services.org_sync_service import sync_all_from_feishu
        stats = sync_all_from_feishu()
        print(f"[sync_org] 完成: {stats}", flush=True)
    except Exception as e:
        print(f"[sync_org] 失败: {e}\n{traceback.format_exc()}", flush=True)


def _do_sync_org_structure():
    """后台任务：仅同步飞书部门到 workmanship_auth_teams（不拉用户）。"""
    import traceback
    print("[sync_org_structure] 后台任务启动", flush=True)
    try:
        from backend.services.org_sync_service import sync_depts_only_to_db
        stats = sync_depts_only_to_db()
        print(f"[sync_org_structure] 完成: {stats}", flush=True)
    except Exception as e:
        print(f"[sync_org_structure] 失败: {e}\n{traceback.format_exc()}", flush=True)


# ── 飞书多维表格 Webhook ───────────────────────────────────────────────────────

from fastapi import Request as _Request


@router.post("/webhook/bitable")
async def bitable_webhook(request: _Request):
    """
    接收飞书多维表格事件推送。
    飞书首次推送时会发 url_verification 事件，需直接返回 challenge。
    真实事件在后台线程处理，立即返回 200。
    """
    import json as _json

    body_bytes = await request.body()
    try:
        payload = _json.loads(body_bytes)
    except Exception:
        return {"code": 0}

    # 飞书 URL 验证握手
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # 加密消息暂不处理（需飞书后台配置 Encrypt Key）
    if payload.get("encrypt"):
        _log.debug("bitable_webhook: encrypted payload, skipping")
        return {"code": 0}

    return {"code": 1, "msg": "legacy Bitable webhook retired; use Integration sync capabilities"}
