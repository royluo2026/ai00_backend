"""
backend/services/feishu_cache_service.py
────────────────────────────────────────
飞书搜索缓存服务：联系人/群聊/文档/日程/会议 持久化到 PG，服务重启后缓存不丢失。

TTL（超过则后台刷新）：
  contact / chat  : 6h
  doc / meeting   : 1h
  event           : 30min
"""
import json
import logging
import time
from typing import Optional

import requests

from backend.db.connection import get_conn

_log = logging.getLogger(__name__)

# TTL（秒）
_TTL = {
    "contact": 6 * 3600,
    "chat":    6 * 3600,
    "doc":     1 * 3600,
    "event":   30 * 60,
    "meeting": 1 * 3600,
}

FEISHU_API = "https://open.feishu.cn/open-apis"


# ─────────────────────────────────────────────────────────────────────────────
# DDL（由 main.py lifespan 调用）
# ─────────────────────────────────────────────────────────────────────────────

def ensure_table():
    """幂等建表：workmanship_app_feishu_search_cache。同时清理超过 7 天未刷新的过期行。"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS workmanship_app_feishu_search_cache (
                        user_gid    CHAR(36)    NOT NULL,
                        entity_type VARCHAR(64) NOT NULL,
                        entity_id   VARCHAR(255) NOT NULL,
                        name        TEXT        NOT NULL DEFAULT '',
                        search_ext  TEXT        NOT NULL DEFAULT '',
                        data        JSON        NOT NULL DEFAULT (JSON_OBJECT()),
                        updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
                        PRIMARY KEY (user_gid, entity_type, entity_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feishu_cache_name
                    ON workmanship_app_feishu_search_cache (user_gid, entity_type, name(191))
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feishu_cache_updated
                    ON workmanship_app_feishu_search_cache (user_gid, entity_type, updated_at)
                """)
                # 清理超过 7 天未刷新的行（防长期堆积）
                cur.execute("""
                    DELETE FROM workmanship_app_feishu_search_cache
                    WHERE updated_at < NOW() - INTERVAL 7 DAY
                """)
                # 清理历史遗留的 p2p 单聊（entity_type='chat' 且 open_id 字段为空字符串）
                cur.execute("""
                    DELETE FROM workmanship_app_feishu_search_cache
                    WHERE entity_type = 'chat'
                      AND JSON_UNQUOTE(JSON_EXTRACT(data, '$.open_id')) = ''
                """)
            conn.commit()
    except Exception as e:
        _log.warning("feishu_cache_service.ensure_table: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# 核心读写
# ─────────────────────────────────────────────────────────────────────────────

def search(user_gid: str, entity_types: list, q: str, limit: int = 8) -> list:
    """从 DB 搜索缓存，返回 [{entity_type, ...data_fields}, ...]。"""
    if not q or not entity_types:
        return []
    q_like = f"%{q.lower()}%"
    results = []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(entity_types))
                cur.execute(f"""
                    SELECT entity_type, data
                    FROM workmanship_app_feishu_search_cache
                    WHERE user_gid = %s
                      AND entity_type IN ({placeholders})
                      AND (name LIKE %s OR search_ext LIKE %s)
                    ORDER BY updated_at DESC
                    LIMIT %s
                """, [user_gid] + entity_types + [q_like, q_like, limit])
                rows = cur.fetchall()
                for row in rows:
                    item = dict(row["data"]) if row["data"] else {}
                    item["_entity_type"] = row["entity_type"]
                    results.append(item)
    except Exception as e:
        _log.warning("feishu_cache search: %s", e)
    return results


def upsert_many(user_gid: str, entity_type: str, items: list):
    """
    批量 upsert 缓存条目。
    items: [{entity_id, name, search_ext(可选), ...其他字段}]
    """
    if not items:
        return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for item in items:
                    entity_id  = item.get("entity_id", "")
                    name       = item.get("name", "") or ""
                    search_ext = item.get("search_ext", "") or ""
                    data_json  = json.dumps(item, ensure_ascii=False)
                    cur.execute("""
                        INSERT INTO workmanship_app_feishu_search_cache
                            (user_gid, entity_type, entity_id, name, search_ext, data)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            name       = VALUES(name),
                            search_ext = VALUES(search_ext),
                            data       = VALUES(data),
                            updated_at = NOW()
                    """, (user_gid, entity_type, entity_id, name, search_ext, data_json))
            conn.commit()
        _log.debug("feishu_cache upsert_many: type=%s count=%d user=%s",
                   entity_type, len(items), user_gid[:8])
    except Exception as e:
        _log.warning("feishu_cache upsert_many: %s", e)


def needs_refresh(user_gid: str, entity_type: str) -> bool:
    """
    判断该用户的某类缓存是否需要刷新（空或超 TTL）。
    """
    ttl = _TTL.get(entity_type, 3600)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT TIMESTAMPDIFF(SECOND, MAX(updated_at), NOW()) AS age_seconds,
                           COUNT(*) AS cnt
                    FROM workmanship_app_feishu_search_cache
                    WHERE user_gid = %s AND entity_type = %s
                """, (user_gid, entity_type))
                row = cur.fetchone()
                if not row or row["cnt"] == 0:
                    return True  # 没有缓存
                age = row["age_seconds"] or 0
                return float(age) > ttl
    except Exception as e:
        _log.warning("feishu_cache needs_refresh: %s", e)
        return True


def cache_count(user_gid: str, entity_type: str) -> int:
    """返回某类缓存条目数量。"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM workmanship_app_feishu_search_cache
                    WHERE user_gid = %s AND entity_type = %s
                """, (user_gid, entity_type))
                row = cur.fetchone()
                return int(row["cnt"]) if row else 0
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 各类型刷新逻辑（后台任务调用）
# ─────────────────────────────────────────────────────────────────────────────

def refresh_contacts(user_gid: str, user_token: str):
    """用 BFS 全员列表（contact:contact.base:readonly）建联系人缓存。"""
    from backend.services.feishu_service import feishu_service
    try:
        users = feishu_service.get_all_users()
        items = []
        for u in users:
            oid = u.get("open_id", "")
            if not oid:
                continue
            items.append({
                "entity_id":  oid,
                "name":       u.get("name", "") or "",
                "search_ext": u.get("email", "") or "",
                **u,
            })
        if items:
            upsert_many(user_gid, "contact", items)
        _log.debug("refresh_contacts done: %d users for %s", len(items), user_gid[:8])
    except Exception as e:
        _log.warning("refresh_contacts: %s", e)


def refresh_chats(user_gid: str, user_token: str):
    """拉取用户所有群聊写入 DB 缓存。"""
    from backend.services.feishu_service import feishu_service
    try:
        chats = feishu_service.get_chats_as_user(user_token)
        items = []
        for c in chats:
            chat_id = c.get("chat_id", "")
            name    = c.get("name", "") or ""
            items.append({
                "entity_id":  chat_id,
                "name":       name,
                "search_ext": "",
                **c,
            })
        if items:
            upsert_many(user_gid, "chat", items)
    except Exception as e:
        _log.warning("refresh_chats: %s", e)


def refresh_docs(user_gid: str, user_token: str):
    """拉取用户最近访问的云文档写入 DB 缓存（drive/v1/files 不传 search_key 则返回最近文件）。"""
    try:
        resp = requests.get(
            f"{FEISHU_API}/drive/v1/files",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"page_size": 50},
            timeout=15,
        )
        data = resp.json()
        files = data.get("data", {}).get("files", []) if data.get("code") == 0 else []
        items = []
        for f in files:
            token = f.get("token", "") or f.get("file_token", "")
            name  = f.get("name", "") or ""
            items.append({
                "entity_id":  token,
                "name":       name,
                "search_ext": f.get("owner_id", ""),
                "url":        f.get("url", ""),
                "type":       f.get("type", ""),
                "owner_name": f.get("owner_id", ""),
            })
        if items:
            upsert_many(user_gid, "doc", items)
    except Exception as e:
        _log.warning("refresh_docs: %s", e)


def refresh_events(user_gid: str, user_token: str):
    """拉取今天前后 7 天的日程写入 DB 缓存。"""
    import datetime
    try:
        tz8 = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(tz8)
        today = datetime.datetime(now.year, now.month, now.day, tzinfo=tz8)
        start_ts = int((today - datetime.timedelta(days=1)).timestamp())
        end_ts   = int((today + datetime.timedelta(days=7)).timestamp())

        resp = requests.get(
            f"{FEISHU_API}/calendar/v4/calendars/primary/events/instance_view",
            headers={"Authorization": f"Bearer {user_token}"},
            params={"start_time": str(start_ts), "end_time": str(end_ts), "page_size": 200},
            timeout=15,
        )
        data = resp.json()
        evs  = data.get("data", {}).get("items", []) if data.get("code") == 0 else []
        items = []
        for ev in evs:
            if ev.get("status") == "cancelled":
                continue
            ev_id   = ev.get("event_id", "") or ev.get("uid", "")
            summary = ev.get("summary", "") or "(无标题)"
            # 格式化开始时间
            st = ev.get("start_time", {})
            ts = st.get("timestamp")
            start_str = ""
            if ts:
                try:
                    d = datetime.datetime.fromtimestamp(int(ts), tz=tz8)
                    start_str = d.strftime("%m-%d %H:%M")
                except Exception:
                    pass
            items.append({
                "entity_id":   ev_id,
                "name":        summary,
                "search_ext":  ev.get("organizer_calendar_id", ""),
                "start":       start_str,
                "end":         st.get("timestamp", ""),
                "meeting_url": ev.get("vchat", {}).get("meeting_url", ""),
                "rsvp":        ev.get("self_rsvp_status", "needs_action"),
            })
        if items:
            upsert_many(user_gid, "event", items)
    except Exception as e:
        _log.warning("refresh_events: %s", e)


def refresh_meetings(user_gid: str, user_token: str):
    """拉取近 30 天 VC 会议记录写入 DB 缓存。"""
    import datetime
    try:
        tz8  = datetime.timezone(datetime.timedelta(hours=8))
        now  = datetime.datetime.now(tz8)
        end_ts   = int(now.timestamp())
        start_ts = int((now - datetime.timedelta(days=30)).timestamp())

        hdrs = {"Authorization": f"Bearer {user_token}"}
        items = []
        page_token = None
        pages = 0

        while pages < 5:
            params = {
                "start_time": str(start_ts),
                "end_time":   str(end_ts),
                "page_size":  100,
            }
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(
                f"{FEISHU_API}/vc/v1/meeting_list",
                headers=hdrs,
                params=params,
                timeout=15,
            )
            data = resp.json()
            if data.get("code") != 0:
                break

            meetings = data.get("data", {}).get("meeting_briefs", []) or []
            for m in meetings:
                mid   = m.get("id", "") or m.get("meeting_no", "")
                topic = m.get("topic", "") or "(无主题)"
                items.append({
                    "entity_id":    mid,
                    "name":         topic,
                    "search_ext":   m.get("meeting_no", ""),
                    "meeting_no":   m.get("meeting_no", ""),
                    "start_time":   m.get("start_time", ""),
                    "end_time":     m.get("end_time", ""),
                    "meeting_url":  m.get("join_meeting_url", ""),
                })

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data.get("data", {}).get("page_token")
            pages += 1

        if items:
            upsert_many(user_gid, "meeting", items)
    except Exception as e:
        _log.warning("refresh_meetings: %s", e)
