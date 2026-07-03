"""
backend/services/feishu_service.py
────────────────────────────────────
所有飞书 API 调用集中在这里。
App Secret 从环境变量读取，永远不出这个文件。
"""
import secrets
import time
import os
import requests
from typing import Optional

from backend.config import get_settings

FEISHU_API = "https://open.feishu.cn/open-apis"

# 飞书文档 Web URL 构造（用于 webview 打开）
FEISHU_WEB_DOMAIN = os.getenv("FEISHU_WEB_DOMAIN", "feishu.cn")
_DOC_TYPE_URL_PATH = {
    "doc":      "docs",
    "docx":     "docx",
    "sheet":    "sheets",
    "bitable":  "base",
    "mindnote": "mindnotes",
    "wiki":     "wiki",
    "slides":   "slides",
    "file":     "file",
}

def _build_doc_web_url(token: str, doc_type: str) -> str:
    """根据 token 和类型构造可在浏览器/webview 打开的 URL。"""
    path = _DOC_TYPE_URL_PATH.get(doc_type, "docs")
    return f"https://{FEISHU_WEB_DOMAIN}/{path}/{token}"


class FeishuService:

    def __init__(self):
        self._users_cache: list = []
        self._users_cache_at: float = 0.0
        self._USERS_TTL = 1800  # 30 分钟

    # ── OAuth ─────────────────────────────────────────────────────────────────

    def build_login_url(self, state: str) -> str:
        """生成飞书 OAuth 授权 URL（含 state，用于回调匹配）"""
        s = get_settings()
        # 显式申请所需 scope，确保 user_access_token 包含日历读写和搜索权限
        # calendar:calendar.event:reply  — 回复日程邀请（RSVP 专用 scope）
        # calendar:calendar.event:update — 编辑日程内容（organizer 用）
        # contact:user:search            — 全局搜索用户（GET /search/v1/user）
        # contact:user.base:readonly     — 读取用户基础信息
        # drive:drive.search:readonly    — 搜索云文档文件列表
        # docs:document.content:read     — 读取文档内容
        # im:chat:readonly               — 读取群聊列表
        # 空格编码为 %20，冒号编码为 %3A，点不编码
        scope = (
            "calendar%3Acalendar.event%3Areply"
            "%20calendar%3Acalendar.event%3Aupdate"
            "%20contact%3Auser%3Asearch"
            "%20contact%3Auser.base%3Areadonly"
            "%20drive%3Adrive.search%3Areadonly"
            "%20docs%3Adocument.content%3Aread"
            "%20im%3Achat%3Areadonly"
            "%20wiki%3Awiki%3Areadonly"
        )
        params = (
            f"?app_id={s.feishu_app_id}"
            f"&redirect_uri={s.feishu_redirect_uri}"
            f"&response_type=code"
            f"&state={state}"
            f"&scope={scope}"
        )
        return f"{FEISHU_API}/authen/v1/authorize{params}"

    def exchange_code(self, code: str) -> dict:
        """
        用 code 换取 user_access_token 及用户信息。
        App Secret 在这里使用，结果中不含 Secret。
        返回：{open_id, name, email, avatar_url, access_token, department_ids}
        """
        s = get_settings()

        # Step 1: code → user_access_token
        resp = requests.post(
            f"{FEISHU_API}/authen/v1/access_token",
            json={
                "grant_type":    "authorization_code",
                "code":          code,
                "app_id":        s.feishu_app_id,
                "app_secret":    s.feishu_app_secret,   # ← 只在这里
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"飞书换 token 失败: {data.get('msg')}")

        token_data = data["data"]
        access_token = token_data["access_token"]

        # Step 2: 用 user_access_token 取用户信息（含 department_ids）
        user_resp = requests.get(
            f"{FEISHU_API}/authen/v1/user_info",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()
        if user_data.get("code") != 0:
            raise ValueError(f"飞书取用户信息失败: {user_data.get('msg')}")

        info = user_data["data"]
        return {
            "open_id":         info.get("open_id", ""),
            "name":            info.get("name", ""),
            "email":           info.get("email", ""),
            "avatar_url":      info.get("avatar_url", ""),
            "access_token":    access_token,
            "refresh_token":   token_data.get("refresh_token", ""),
            "expires_in":      token_data.get("expires_in", 7200),
            "department_ids":  info.get("department_ids", []),
        }

    # ── 消息代理 ──────────────────────────────────────────────────────────────

    def _get_tenant_token(self) -> str:
        """获取 tenant_access_token（用 App ID + App Secret）"""
        s = get_settings()
        resp = requests.post(
            f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
            json={"app_id": s.feishu_app_id, "app_secret": s.feishu_app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"获取 tenant_token 失败: {data.get('msg')}")
        return data["tenant_access_token"]

    def send_message(self, open_id: str, text: str) -> bool:
        """发送飞书文本消息"""
        try:
            token = self._get_tenant_token()
            resp = requests.post(
                f"{FEISHU_API}/im/v1/messages?receive_id_type=open_id",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": open_id,
                    "msg_type":   "text",
                    "content":    f'{{"text":"{text}"}}',
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("code") == 0
        except Exception:
            return False

    def send_message_to_chat(self, chat_id: str, content: str, msg_type: str = "text") -> bool:
        """发送消息到飞书群聊"""
        import json as _json
        try:
            token = self._get_tenant_token()
            resp = requests.post(
                f"{FEISHU_API}/im/v1/messages?receive_id_type=chat_id",
                headers={"Authorization": f"Bearer {token}"},
                json={"receive_id": chat_id, "msg_type": msg_type, "content": content},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("code") == 0
        except Exception:
            return False

    def get_department(self, dept_id: str) -> Optional[dict]:
        """
        获取单个部门信息。
        dept_id 为 open_department_id 格式（/authen/v1/user_info 返回的 department_ids）。
        返回：{dept_id, name, parent_department_id} 或 None（失败时）
        """
        import logging
        _log = logging.getLogger(__name__)
        try:
            token = self._get_tenant_token()
            resp = requests.get(
                f"{FEISHU_API}/contact/v3/departments/{dept_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"department_id_type": "open_department_id"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                _log.warning("get_department(%s) 失败: code=%s msg=%s", dept_id, data.get("code"), data.get("msg"))
                return None
            d = data["data"]["department"]
            return {
                "dept_id":              d.get("open_department_id", dept_id),
                "department_id":        d.get("department_id", ""),
                "name":                 d.get("name", ""),
                "parent_department_id": d.get("parent_open_department_id", ""),
            }
        except Exception as e:
            _log.warning("get_department(%s) 异常: %s", dept_id, e)
            return None

    def get_org_users(self, page_token: str = "") -> dict:
        """获取根部门直属成员列表（单页）。仅用于 /org/users 端点展示，不用于搜索。"""
        token = self._get_tenant_token()
        params = {
            "page_size":          50,
            "department_id":      "0",
            "department_id_type": "department_id",
            "user_id_type":       "open_id",
        }
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"{FEISHU_API}/contact/v3/users",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
        return raw.get("data", {})

    def _get_all_dept_open_ids(self) -> list:
        """BFS 遍历整棵部门树，返回所有子部门的 open_department_id。
        注意：根部门（system id=0）第一层子部门必须用 parent_department_id=0
        + department_id_type=department_id；再往下才用 open_department_id。
        """
        token = self._get_tenant_token()
        ids = []
        queue = [("0", "department_id")]
        visited: set = set()
        safety = 0
        while queue and safety < 500:
            safety += 1
            parent_id, id_type = queue.pop(0)
            page_token = ""
            while True:
                params = {"page_size": 50}
                if id_type == "department_id":
                    params["parent_department_id"]  = parent_id
                    params["department_id_type"]    = "department_id"
                else:
                    params["parent_open_department_id"] = parent_id
                    params["department_id_type"]        = "open_department_id"
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = requests.get(
                        f"{FEISHU_API}/contact/v3/departments",
                        headers={"Authorization": f"Bearer {token}"},
                        params=params, timeout=8,
                    )
                    d = resp.json().get("data", {})
                    for dept in d.get("items", []):
                        oid = dept.get("open_department_id", "")
                        if oid and oid not in visited:
                            visited.add(oid)
                            ids.append(oid)
                            queue.append((oid, "open_department_id"))
                    if not d.get("has_more"):
                        break
                    page_token = d.get("page_token", "")
                except Exception as e:
                    break
        return ids

    def _get_users_in_dept(self, dept_id: str, dept_id_type: str = "open_department_id") -> list:
        """获取某个部门的直属成员。dept_id_type 默认 open_department_id，根部门传 department_id。"""
        token = self._get_tenant_token()
        results = []
        page_token = ""
        for _ in range(10):
            params = {
                "page_size":          50,
                "department_id":      dept_id,
                "department_id_type": dept_id_type,
                "user_id_type":       "open_id",
            }
            if page_token:
                params["page_token"] = page_token
            try:
                resp = requests.get(
                    f"{FEISHU_API}/contact/v3/users",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params, timeout=8,
                )
                data = resp.json().get("data", {})
                for u in data.get("items", []):
                    results.append({
                        "open_id":    u.get("open_id", ""),
                        "name":       u.get("name", ""),
                        "email":      u.get("email", ""),
                        "avatar_url": u.get("avatar", {}).get("avatar_240", ""),
                    })
                if not data.get("has_more"):
                    break
                page_token = data.get("page_token", "")
            except Exception:
                break
        return results

    def get_all_users(self, force_refresh: bool = False) -> list:
        """
        返回全量用户列表（根部门 + BFS 遍历所有子部门）。
        结果缓存 30 分钟，避免每次搜索都打大量 API 请求。
        """
        now = time.time()
        if (not force_refresh
                and self._users_cache
                and (now - self._users_cache_at) < self._USERS_TTL):
            return self._users_cache

        dept_ids = self._get_all_dept_open_ids()
        results = []
        seen: set = set()

        # 先拉根部门直属成员（未分配到子部门的员工，是最容易漏的一批）
        for u in self._get_users_in_dept("0", dept_id_type="department_id"):
            if u["open_id"] and u["open_id"] not in seen:
                seen.add(u["open_id"])
                results.append(u)

        # 再遍历所有子部门
        for dept_id in dept_ids:
            for u in self._get_users_in_dept(dept_id):
                if u["open_id"] and u["open_id"] not in seen:
                    seen.add(u["open_id"])
                    results.append(u)

        if results:
            self._users_cache = results
            self._users_cache_at = now
        return results

    def get_contacts_from_chats(self, user_access_token: str) -> list:
        """
        从用户 p2p 聊天的 owner_id 批量反查联系人姓名。
        不需要 contact:contact:readonly，只用 contact:user:readonly。
        """
        # Step1: 获取所有 p2p 聊天，收集对方 open_id（owner_id 字段）
        chats = self.get_chats_as_user(user_access_token, chat_type="p2p")
        open_ids = list({c.get("owner_id", "") for c in chats if c.get("owner_id")})

        # Step2: 批量查用户信息，50 个/批
        token = self._get_tenant_token()
        results = []
        seen: set = set()
        for i in range(0, len(open_ids), 50):
            batch = open_ids[i:i + 50]
            try:
                resp = requests.get(
                    f"{FEISHU_API}/contact/v3/users/batch",
                    headers={"Authorization": f"Bearer {token}"},
                    params=[("user_ids", oid) for oid in batch]
                          + [("user_id_type", "open_id")],
                    timeout=10,
                )
                data = resp.json()
                if data.get("code") == 0:
                    for u in (data.get("data", {}).get("items", []) or []):
                        oid = u.get("open_id", "")
                        if oid and oid not in seen:
                            seen.add(oid)
                            results.append({
                                "open_id":    oid,
                                "name":       u.get("name", ""),
                                "email":      u.get("email", ""),
                                "avatar_url": u.get("avatar", {}).get("avatar_240", ""),
                            })
            except Exception as e:
                pass

        return results

    def sync_org_structure(self) -> dict:
        """
        用 app tenant token 并行拉取飞书完整组织架构。
        返回：{departments: [...], users: [...]}
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        token = self._get_tenant_token()
        hdrs  = {"Authorization": f"Bearer {token}"}
        print(f"[sync_org] 开始，token={'ok' if token else 'EMPTY'}", flush=True)

        # ── Step 1: 并行 BFS 拉所有部门 ──────────────────────────────────────
        departments: list = []
        visited_lock = threading.Lock()
        visited: set = set()

        def _fetch_dept_children(parent_did: str, parent_open_id):
            """拉一个父部门的直接子部门（含分页），返回子部门列表。"""
            result = []
            page_token = ""
            while True:
                params = {"page_size": 50, "parent_department_id": parent_did,
                          "department_id_type": "department_id"}
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = requests.get(f"{FEISHU_API}/contact/v3/departments",
                                        headers=hdrs, params=params, timeout=10)
                    d = resp.json().get("data", {})
                    for dept in d.get("items", []):
                        oid = dept.get("open_department_id", "")
                        did = dept.get("department_id", "")
                        if not oid or not did:
                            continue
                        with visited_lock:
                            if oid in visited:
                                continue
                            visited.add(oid)
                        result.append({
                            "open_id":        oid,
                            "department_id":  did,
                            "name":           dept.get("name", ""),
                            "parent_open_id": parent_open_id,
                            "order":          dept.get("order", 0),
                            "member_count":   dept.get("member_count", 0),
                        })
                    if not d.get("has_more"):
                        break
                    page_token = d.get("page_token", "")
                except Exception as e:
                    print(f"[sync_org] dept exception parent={parent_did}: {e}", flush=True)
                    break
            return result

        # BFS 并行：每层的所有部门同时并发请求
        current_level = [("0", None)]  # (parent_did, parent_open_id)
        with ThreadPoolExecutor(max_workers=10) as pool:
            while current_level:
                futures = {pool.submit(_fetch_dept_children, did, poid): (did, poid)
                           for did, poid in current_level}
                next_level = []
                for fut in as_completed(futures):
                    children = fut.result()
                    departments.extend(children)
                    next_level.extend([(c["department_id"], c["open_id"]) for c in children])
                current_level = next_level
                if current_level:
                    print(f"[sync_org] 已拉 {len(departments)} 个部门，下一层 {len(current_level)} 个", flush=True)

        print(f"[sync_org] departments found: {len(departments)}", flush=True)

        # ── Step 2: 并行拉每个部门的用户 ──────────────────────────────────────
        user_map: dict = {}
        user_lock = threading.Lock()
        print(f"[sync_org] 开始拉用户，部门数={len(departments)}", flush=True)

        def _fetch_dept_users(dept: dict):
            dept_oid = dept["open_id"]
            local = []
            page_token = ""
            for _ in range(20):
                params = {"page_size": 50, "department_id": dept_oid,
                          "department_id_type": "open_department_id",
                          "user_id_type": "open_id"}
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = requests.get(f"{FEISHU_API}/contact/v3/users",
                                        headers=hdrs, params=params, timeout=10)
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[sync_org] 部门 {dept.get('name')!r} 拉用户失败: "
                              f"code={data.get('code')}", flush=True)
                        break
                    items = (data.get("data") or {}).get("items") or []
                    local.extend((dept_oid, u) for u in items if u.get("open_id"))
                    if not (data.get("data") or {}).get("has_more"):
                        break
                    page_token = (data.get("data") or {}).get("page_token", "")
                except Exception as e:
                    print(f"[sync_org] users exception dept={dept_oid}: {e}", flush=True)
                    break
            return local

        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(_fetch_dept_users, dept) for dept in departments]
            done = 0
            for fut in as_completed(futs):
                entries = fut.result()
                done += 1
                with user_lock:
                    for dept_oid, u in entries:
                        oid = u["open_id"]
                        if oid not in user_map:
                            user_map[oid] = {
                                "open_id":             oid,
                                "name":                u.get("name", ""),
                                "email":               u.get("email", ""),
                                "avatar_url":          (u.get("avatar") or {}).get("avatar_240", ""),
                                "department_open_ids": [],
                            }
                        if dept_oid not in user_map[oid]["department_open_ids"]:
                            user_map[oid]["department_open_ids"].append(dept_oid)
                if done % 20 == 0:
                    print(f"[sync_org] 已处理 {done}/{len(departments)} 个部门的用户", flush=True)

        users = list(user_map.values())
        print(f"[sync_org] total users: {len(users)}", flush=True)
        return {"departments": departments, "users": users}


        users = list(user_map.values())
        print(f"[sync_org] total users: {len(users)}", flush=True)
        return {"departments": departments, "users": users}

    def search_departments_by_name(self, query: str, page_size: int = 20,
                                    user_access_token: str = "") -> tuple:
        """
        本地缓存过滤。先确保 BFS 缓存已建好（或触发后台建缓存）。
        返回 (results: list, warming: bool)
        warming=True 表示缓存还在建，当前结果可能不全（前端可提示）。
        """
        import time
        cache_ready = (hasattr(self, '_dept_tree_cache')
                       and time.time() - getattr(self, '_dept_tree_cache_ts', 0) < 300)
        if not cache_ready:
            # 触发后台 BFS，不阻塞当前请求
            self._ensure_dept_cache_background()
            return [], True  # warming

        q = query.lower()
        results = [d for d in self._dept_tree_cache
                   if q in d.get("name", "").lower()][:page_size]
        return results, False

    def _ensure_dept_cache_background(self):
        """在后台线程里跑 BFS，只允许一个线程同时跑。"""
        import threading, time
        if not hasattr(self, '_dept_bfs_running'):
            self._dept_bfs_running = False
        if self._dept_bfs_running:
            return
        # 已有新鲜缓存则跳过
        if (hasattr(self, '_dept_tree_cache')
                and time.time() - getattr(self, '_dept_tree_cache_ts', 0) < 300):
            return
        self._dept_bfs_running = True
        def _run():
            try:
                self._do_dept_tree_bfs()
            finally:
                self._dept_bfs_running = False
        threading.Thread(target=_run, daemon=True, name="dept-bfs").start()
        print("[dept_search] 后台 BFS 已启动", flush=True)

    def get_dept_tree_flat(self) -> list:
        """
        BFS 整棵飞书部门树，只返回部门列表（不拉用户），用于前端部门选择器。
        结果缓存 5 分钟，避免并发搜索重复触发 BFS。
        返回：[{open_id, name, parent_open_id, member_count}]
        """
        import time, threading
        now = time.time()
        if hasattr(self, '_dept_tree_cache') and now - self._dept_tree_cache_ts < 300:
            return self._dept_tree_cache

        if not hasattr(self, '_dept_tree_lock'):
            self._dept_tree_lock = threading.Lock()
        if not self._dept_tree_lock.acquire(blocking=True, timeout=60):
            return getattr(self, '_dept_tree_cache', [])
        try:
            # Re-check after acquiring lock (another thread may have just populated the cache)
            now = time.time()
            if hasattr(self, '_dept_tree_cache') and now - self._dept_tree_cache_ts < 300:
                return self._dept_tree_cache
            return self._do_dept_tree_bfs()
        finally:
            self._dept_tree_lock.release()

    def _do_dept_tree_bfs(self) -> list:
        """
        按飞书专家方案：递归调 /contact/v3/departments/{dept_id}/children
        fetch_child=True（布尔），无 department_id_type 参数。
        在后台线程里执行，不阻塞 HTTP 请求。
        """
        import time
        token = self._get_tenant_token()
        departments = []

        def _fetch_children(dept_id: str):
            page_token = None
            while True:
                params = {"fetch_child": True, "page_size": 100}
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = requests.get(
                        f"{FEISHU_API}/contact/v3/departments/{dept_id}/children",
                        headers={"Authorization": f"Bearer {token}"},
                        params=params,
                        timeout=15,
                    )
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[dept_bfs] dept={dept_id} code={data.get('code')} "
                              f"msg={data.get('msg')!r}", flush=True)
                        return
                    items = (data.get("data") or {}).get("items") or []
                    for dept in items:
                        did = dept.get("department_id", "")
                        oid = dept.get("open_department_id", "")
                        departments.append({
                            "open_id":      oid,
                            "name":         dept.get("name", ""),
                            "member_count": dept.get("member_count", 0),
                        })
                        if did:
                            _fetch_children(did)
                    if not (data.get("data") or {}).get("has_more"):
                        break
                    page_token = (data.get("data") or {}).get("page_token")
                except Exception as e:
                    print(f"[dept_bfs] 异常 dept={dept_id}: {e}", flush=True)
                    return

        _fetch_children("0")
        print(f"[dept_bfs] 完成，共 {len(departments)} 个部门", flush=True)
        self._dept_tree_cache    = departments
        self._dept_tree_cache_ts = time.time()
        return departments

    def sync_departments_only(self, level_callback=None, max_depth: int = 0) -> list:
        """
        并行 BFS 拉全量部门（不拉用户），用于同步组织架构。
        level_callback(level_depts): 每层完成后回调，可用于增量写库。
        max_depth: 最大深度，0 = 不限制。
        返回：所有部门列表 [{open_id, department_id, name, parent_open_id, member_count}]
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        token = self._get_tenant_token()
        hdrs  = {"Authorization": f"Bearer {token}"}
        departments: list = []
        visited_lock = threading.Lock()
        visited: set = set()

        def _fetch_children(parent_did: str, parent_open_id):
            result = []
            page_token = ""
            while True:
                params = {"page_size": 50, "parent_department_id": parent_did,
                          "department_id_type": "department_id"}
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = requests.get(f"{FEISHU_API}/contact/v3/departments",
                                        headers=hdrs, params=params, timeout=10)
                    rj = resp.json()
                    if rj.get("code") not in (0, None):
                        print(f"[sync_depts] API error parent={parent_did} code={rj.get('code')} msg={rj.get('msg')!r}", flush=True)
                        break
                    d = rj.get("data") or {}
                    for dept in d.get("items", []):
                        oid = dept.get("open_department_id", "")
                        did = dept.get("department_id", "")
                        if not oid or not did:
                            continue
                        with visited_lock:
                            if oid in visited:
                                continue
                            visited.add(oid)
                        result.append({"open_id": oid, "department_id": did,
                                       "name": dept.get("name", ""),
                                       "parent_open_id": parent_open_id,
                                       "member_count": dept.get("member_count", 0)})
                    if not d.get("has_more"):
                        break
                    page_token = d.get("page_token", "")
                except Exception as e:
                    print(f"[sync_depts] exception parent={parent_did}: {e}", flush=True)
                    break
            return result

        current_level = [("0", None)]
        # 顶级部门黑名单：这两个部门及其全部子树不写入 DB
        _EXCLUDE_TOP = {"外援与外部合作", "暂存部门", "合作伙伴", "使命担当"}

        level_num = 0
        with ThreadPoolExecutor(max_workers=10) as pool:
            while current_level:
                level_num += 1
                print(f"[sync_depts] 第 {level_num} 层，并发请求 {len(current_level)} 个部门的子节点…", flush=True)
                futures = {pool.submit(_fetch_children, did, poid): (did, poid)
                           for did, poid in current_level}
                next_level = []
                for fut in as_completed(futures):
                    children = fut.result()
                    # 第 1 层（顶级部门）过滤黑名单，其子树不再递归
                    if level_num == 1:
                        excluded = [c["name"] for c in children if c["name"] in _EXCLUDE_TOP]
                        if excluded:
                            print(f"[sync_depts] 跳过顶级部门: {excluded}", flush=True)
                        children = [c for c in children if c["name"] not in _EXCLUDE_TOP]
                    departments.extend(children)
                    next_level.extend([(c["department_id"], c["open_id"]) for c in children])
                print(f"[sync_depts] 第 {level_num} 层完成，本层新增 {len(next_level)} 个，累计 {len(departments)} 个", flush=True)
                if level_callback and next_level:
                    try:
                        level_callback(departments[-len(next_level):])
                    except Exception as cb_err:
                        print(f"[sync_depts] level_callback 异常: {cb_err}", flush=True)
                if max_depth and level_num >= max_depth:
                    print(f"[sync_depts] 已达最大深度 {max_depth}，停止", flush=True)
                    break
                current_level = next_level

        print(f"[sync_depts] 完成，共 {len(departments)} 个部门", flush=True)
        return departments

    def get_top_level_departments(self) -> list:
        """只拉根部门的直接子部门（第一层），用于前端选择器。一次 API 调用即可。"""
        token = self._get_tenant_token()
        hdrs  = {"Authorization": f"Bearer {token}"}
        results = []
        page_token = ""
        while True:
            params = {"page_size": 50, "parent_department_id": "0",
                      "department_id_type": "department_id"}
            if page_token:
                params["page_token"] = page_token
            try:
                resp = requests.get(f"{FEISHU_API}/contact/v3/departments",
                                    headers=hdrs, params=params, timeout=10)
                d = resp.json().get("data", {})
                for dept in d.get("items", []):
                    oid = dept.get("open_department_id", "")
                    did = dept.get("department_id", "")
                    if oid:
                        results.append({"open_id": oid, "department_id": did,
                                        "name": dept.get("name", ""),
                                        "member_count": dept.get("member_count", 0)})
                if not d.get("has_more"):
                    break
                page_token = d.get("page_token", "")
            except Exception as e:
                print(f"[top_depts] exception: {e}", flush=True)
                break
        return results

    def sync_org_structure_subtree(self, root_dept_id: str) -> dict:
        """
        从指定根部门（open_department_id）开始，只同步该子树的部门和用户。
        BFS 全程用 department_id（数字型），兼容 contact:department.base:readonly。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        token = self._get_tenant_token()
        hdrs  = {"Authorization": f"Bearer {token}"}

        # 先拉根部门自身信息（用 open_department_id 查单个部门）
        root_info = self.get_department(root_dept_id)
        departments = [{
            "open_id":        root_dept_id,
            "name":           root_info["name"] if root_info else root_dept_id,
            "parent_open_id": None,
            "member_count":   0,
        }]

        # 根部门的 department_id（数字型），用于 BFS
        root_did = root_info.get("department_id", "") if root_info else ""
        print(f"[sync_subtree] root_dept_id={root_dept_id} root_did={root_did!r} name={root_info.get('name') if root_info else 'N/A'}", flush=True)
        if not root_did:
            print("[sync_subtree] 无法获取 department_id，BFS 将跳过", flush=True)

        visited_lock = threading.Lock()
        visited: set = {root_dept_id}

        def _fetch_children(parent_did: str, parent_open_id: str):
            result = []
            page_token = ""
            while True:
                params = {"page_size": 50, "parent_department_id": parent_did,
                          "department_id_type": "department_id"}
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = requests.get(f"{FEISHU_API}/contact/v3/departments",
                                        headers=hdrs, params=params, timeout=10)
                    d = resp.json().get("data", {})
                    for dept in d.get("items", []):
                        oid = dept.get("open_department_id", "")
                        did = dept.get("department_id", "")
                        if not oid or not did:
                            continue
                        with visited_lock:
                            if oid in visited:
                                continue
                            visited.add(oid)
                        result.append({"open_id": oid, "department_id": did,
                                       "name": dept.get("name", ""),
                                       "parent_open_id": parent_open_id,
                                       "member_count": dept.get("member_count", 0)})
                    if not d.get("has_more"):
                        break
                    page_token = d.get("page_token", "")
                except Exception as e:
                    print(f"[sync_subtree] exception parent={parent_did}: {e}", flush=True)
                    break
            return result

        # 并行 BFS（逐层展开）
        if root_did:
            current_level = [(root_did, root_dept_id)]
            with ThreadPoolExecutor(max_workers=10) as pool:
                while current_level:
                    futures = {pool.submit(_fetch_children, did, poid): (did, poid)
                               for did, poid in current_level}
                    next_level = []
                    for fut in as_completed(futures):
                        children = fut.result()
                        departments.extend(children)
                        next_level.extend([(c["department_id"], c["open_id"]) for c in children])
                    current_level = next_level

        print(f"[sync_subtree] root={root_dept_id} depts={len(departments)}", flush=True)

        # 并行拉用户
        user_map: dict = {}
        user_lock = threading.Lock()

        def _fetch_users(dept: dict):
            dept_oid = dept["open_id"]
            local = []
            page_token = ""
            for _ in range(20):
                params = {"page_size": 50, "department_id": dept_oid,
                          "department_id_type": "open_department_id",
                          "user_id_type": "open_id"}
                if page_token:
                    params["page_token"] = page_token
                try:
                    resp = requests.get(f"{FEISHU_API}/contact/v3/users",
                                        headers=hdrs, params=params, timeout=10)
                    data = resp.json()
                    if data.get("code") != 0:
                        break
                    items = (data.get("data") or {}).get("items") or []
                    local.extend((dept_oid, u) for u in items if u.get("open_id"))
                    if not (data.get("data") or {}).get("has_more"):
                        break
                    page_token = (data.get("data") or {}).get("page_token", "")
                except Exception as e:
                    print(f"[sync_subtree] users exception dept={dept_oid}: {e}", flush=True)
                    break
            return local

        with ThreadPoolExecutor(max_workers=10) as pool:
            for entries in pool.map(_fetch_users, departments):
                with user_lock:
                    for dept_oid, u in entries:
                        oid = u["open_id"]
                        if oid not in user_map:
                            user_map[oid] = {"open_id": oid, "name": u.get("name", ""),
                                             "email": u.get("email", ""),
                                             "avatar_url": (u.get("avatar") or {}).get("avatar_240", ""),
                                             "department_open_ids": []}
                        if dept_oid not in user_map[oid]["department_open_ids"]:
                            user_map[oid]["department_open_ids"].append(dept_oid)

        users = list(user_map.values())
        print(f"[sync_subtree] depts={len(departments)} users={len(users)}", flush=True)
        return {"departments": departments, "users": users}


    def refresh_user_token(self, refresh_token: str) -> dict:
        """
        用 refresh_token 换新的 user_access_token。
        返回 {access_token, refresh_token, expires_in} 或抛出异常。
        """
        s = get_settings()
        resp = requests.post(
            f"{FEISHU_API}/authen/v1/refresh_access_token",
            json={
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
                "app_id":        s.feishu_app_id,
                "app_secret":    s.feishu_app_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"刷新 token 失败: {data.get('msg')}")
        d = data["data"]
        return {
            "access_token":  d["access_token"],
            "refresh_token": d.get("refresh_token", refresh_token),
            "expires_in":    d.get("expires_in", 7200),
        }

    def get_doc_raw_content_as_user(self, doc_token: str, user_access_token: str) -> str:
        """以用户自己的 token 读取飞书文档纯文本（用户有阅读权限即可）。"""
        resp = requests.get(
            f"{FEISHU_API}/docx/v1/documents/{doc_token}/raw_content",
            headers={"Authorization": f"Bearer {user_access_token}"},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"读取文档失败(code={data.get('code')}): {data.get('msg')}")
        return data.get("data", {}).get("content", "")

    def get_doc_blocks_as_user(self, doc_token: str, user_access_token: str) -> list:
        """以用户 token 获取文档所有 block。"""
        resp = requests.get(
            f"{FEISHU_API}/docx/v1/documents/{doc_token}/blocks",
            headers={"Authorization": f"Bearer {user_access_token}"},
            params={"page_size": 500},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"获取文档 blocks 失败(code={data.get('code')}): {data.get('msg')}")
        return data.get("data", {}).get("items", [])

    def update_block_text_as_user(
        self, doc_token: str, block_id: str, text: str, user_access_token: str
    ) -> dict:
        """以用户 token 更新 block 文本（用户有编辑权限即可）。"""
        resp = requests.patch(
            f"{FEISHU_API}/docx/v1/documents/{doc_token}/blocks/{block_id}",
            headers={
                "Authorization": f"Bearer {user_access_token}",
                "Content-Type": "application/json",
            },
            json={
                "update_text_elements": {
                    "elements": [{"text_run": {"content": text}}]
                }
            },
            timeout=10,
        )
        return resp.json()

    def get_chats_as_user(
        self, user_access_token: str, chat_type: str = "group",
        page_size: int = 100, max_pages: int = 20,
    ) -> list:
        """以用户 token 分页获取该用户所在的全部群聊（按最近活跃时间倒序）。"""
        results = []
        page_token = ""
        for _ in range(max_pages):
            params: dict = {"page_size": page_size, "chat_type": chat_type,
                            "sort_type": "ByActiveTimeDesc"}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(
                f"{FEISHU_API}/im/v1/chats",
                headers={"Authorization": f"Bearer {user_access_token}"},
                params=params,
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise ValueError(f"获取聊天列表失败(code={data.get('code')}): {data.get('msg')}")
            page_data = data.get("data", {})
            results.extend(page_data.get("items", []))
            if not page_data.get("has_more"):
                break
            page_token = page_data.get("page_token", "")
        return results

    def search_chats(
        self, user_access_token: str, query: str,
        page_size: int = 20, max_pages: int = 5,
    ) -> list:
        """使用 /im/v1/chats/search 按群名关键词搜索（也会匹配成员名，需调用方过滤）。"""
        results = []
        page_token = ""
        for _ in range(max_pages):
            params: dict = {"query": query, "page_size": page_size,
                            "user_id_type": "open_id"}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(
                f"{FEISHU_API}/im/v1/chats/search",
                headers={"Authorization": f"Bearer {user_access_token}"},
                params=params,
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                break
            page_data = data.get("data", {})
            results.extend(page_data.get("items", []))
            if not page_data.get("has_more"):
                break
            page_token = page_data.get("page_token", "")
        return results

    def get_chat_messages_as_user(
        self, chat_id: str, user_access_token: str, page_size: int = 20
    ) -> list:
        """以用户 token 获取聊天消息（用户在该聊天中即可）。"""
        resp = requests.get(
            f"{FEISHU_API}/im/v1/messages",
            headers={"Authorization": f"Bearer {user_access_token}"},
            params={
                "container_id_type": "chat",
                "container_id":      chat_id,
                "page_size":         page_size,
                "sort_type":         "ByCreateTimeDesc",
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"获取消息失败(code={data.get('code')}): {data.get('msg')}")
        return data.get("data", {}).get("items", [])

    def search_users_by_name(self, name: str, page_size: int = 10,
                             user_access_token: str = "") -> list:
        """按姓名搜索飞书用户。
        先尝试 GET /search/v1/user（需 search:user scope，仅 user token）；
        再降级尝试 POST /contact/v3/users/search（需 contact:contact.base:readonly）。
        """
        # ── 方案 A：/search/v1/user（search:user scope）────────────────────────
        if user_access_token:
            resp_a = requests.get(
                f"{FEISHU_API}/search/v1/user",
                headers={"Authorization": f"Bearer {user_access_token}"},
                params={"query": name, "page_size": page_size, "user_id_type": "open_id"},
                timeout=10,
            )
            data_a = resp_a.json()
            if data_a.get("code") == 0:
                items = (data_a.get("data") or {}).get("users", [])
                return [
                    {
                        "open_id":    u.get("open_id") or u.get("user_id", ""),
                        "name":       u.get("name", ""),
                        "email":      u.get("email", ""),
                        "avatar_url": (u.get("avatar") or {}).get("avatar_240", "")
                                      or u.get("avatar_url", ""),
                    }
                    for u in items
                ]

        # ── 方案 B：POST /contact/v3/users/search（tenant token）────────────────
        token = self._get_tenant_token()
        resp = requests.post(
            f"{FEISHU_API}/contact/v3/users/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": name, "page_size": page_size, "user_id_type": "open_id"},
            timeout=10,
        )
        data = resp.json()
        # v3 users/search 返回字段在 data.items（不是 data.users）
        items = (data.get("data") or {}).get("items") or (data.get("data") or {}).get("users") or []
        return [
            {
                "open_id":    u.get("open_id", ""),
                "name":       u.get("name", ""),
                "email":      u.get("email", ""),
                "avatar_url": (u.get("avatar") or {}).get("avatar_240", ""),
            }
            for u in items
        ]

    def get_p2p_chats(self, page_size: int = 50) -> list:
        """获取机器人所在的单聊列表。"""
        token = self._get_tenant_token()
        resp = requests.get(
            f"{FEISHU_API}/im/v1/chats",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": page_size, "chat_type": "p2p"},
            timeout=10,
        )
        return resp.json().get("data", {}).get("items", [])

    # ── IM / 文档辅助方法 ─────────────────────────────────────────────────────

    def get_chats(self, page_size: int = 100) -> list:
        """获取机器人所在的群聊列表（tenant token）。"""
        token = self._get_tenant_token()
        resp = requests.get(
            f"{FEISHU_API}/im/v1/chats",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": page_size, "chat_type": "group"},
            timeout=10,
        )
        data = resp.json()
        return data.get("data", {}).get("items", [])

    def get_chat_messages(self, chat_id: str, page_size: int = 20) -> list:
        """获取某个群聊最近的消息（tenant token）。"""
        token = self._get_tenant_token()
        resp = requests.get(
            f"{FEISHU_API}/im/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "container_id_type": "chat",
                "container_id": chat_id,
                "page_size": page_size,
                "sort_type": "ByCreateTimeDesc",
            },
            timeout=10,
        )
        return resp.json().get("data", {}).get("items", [])

    def get_doc_raw_content(self, doc_token: str) -> str:
        """读取飞书文档纯文本内容（新版 docx，tenant token）。"""
        token = self._get_tenant_token()
        resp = requests.get(
            f"{FEISHU_API}/docx/v1/documents/{doc_token}/raw_content",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        data = resp.json()
        return data.get("data", {}).get("content", "")

    def get_doc_blocks(self, doc_token: str) -> list:
        """获取文档所有 block（用于定位表格行，tenant token）。"""
        token = self._get_tenant_token()
        resp = requests.get(
            f"{FEISHU_API}/docx/v1/documents/{doc_token}/blocks",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": 500},
            timeout=15,
        )
        return resp.json().get("data", {}).get("items", [])

    def update_block_text(self, doc_token: str, block_id: str, text: str) -> dict:
        """更新指定 block 的文本内容（tenant token）。"""
        token = self._get_tenant_token()
        resp = requests.patch(
            f"{FEISHU_API}/docx/v1/documents/{doc_token}/blocks/{block_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "update_text_elements": {
                    "elements": [{"text_run": {"content": text}}]
                }
            },
            timeout=10,
        )
        return resp.json()


    # ── 日历 ──────────────────────────────────────────────────────────────────

    # 用户主日历 ID 缓存 {token: calendar_id}（进程内，重启清空）
    _primary_cal_cache: dict = {}

    def _get_primary_cal_id(self, user_token: str) -> str:
        """获取用户主日历 ID，带内存缓存（进程内有效）。"""
        if user_token in self._primary_cal_cache:
            return self._primary_cal_cache[user_token]
        try:
            r = requests.get(
                f"{FEISHU_API}/calendar/v4/calendars",
                headers={"Authorization": f"Bearer {user_token}"},
                params={"page_size": 20},
                timeout=8,
            )
            items = r.json().get("data", {}).get("calendar_list", [])
            for item in items:
                cal = item.get("calendar", item)
                if cal.get("is_primary"):
                    cal_id = cal.get("calendar_id", "")
                    self._primary_cal_cache[user_token] = cal_id
                    return cal_id
        except Exception:
            pass
        return ""

    def get_calendar_today(self, user_token: str, date: str = None) -> list:
        """
        用用户的 feishu_access_token 拉取指定日期日程（实例视图，含重复日程展开）。
        date: "YYYY-MM-DD"，为 None 时使用今日（北京时间）。
        返回按开始时间升序的列表，每条：
          {event_id, summary, start, end, rsvp, meeting_url, organizer,
           is_organizer, description, start_ts, end_ts}
          start/end 为 "HH:MM" 或 "全天"
        """
        import datetime
        tz8 = datetime.timezone(datetime.timedelta(hours=8))
        if date:
            try:
                parts = date.split('-')
                target = datetime.datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=tz8)
            except Exception:
                target = datetime.datetime.now(tz8)
        else:
            now = datetime.datetime.now(tz8)
            target = datetime.datetime(now.year, now.month, now.day, tzinfo=tz8)
        start_ts = int(target.timestamp())
        end_ts   = start_ts + 86400  # 次日 00:00

        hdrs = {"Authorization": f"Bearer {user_token}"}
        cal_id = "primary"

        # 获取用户主日历 ID 用于判断 is_organizer
        user_cal_id = self._get_primary_cal_id(user_token)

        # 查询今日实例视图（含展开的重复日程）
        events = []
        try:
            r = requests.get(
                f"{FEISHU_API}/calendar/v4/calendars/{cal_id}/events/instance_view",
                headers=hdrs,
                params={"start_time": str(start_ts), "end_time": str(end_ts),
                        "page_size": 200},
                timeout=10,
            )
            items = r.json().get("data", {}).get("items", [])
        except Exception:
            return []

        for ev in items:
            # 过滤已取消
            if ev.get("status") == "cancelled":
                continue
            st = ev.get("start_time", {})
            et = ev.get("end_time", {})

            def _fmt(t):
                ts = t.get("timestamp")
                if ts:
                    try:
                        import datetime as _dt
                        tz8 = _dt.timezone(_dt.timedelta(hours=8))
                        d = _dt.datetime.fromtimestamp(int(ts), tz=tz8)
                        return f"{d.hour:02d}:{d.minute:02d}"
                    except Exception:
                        pass
                dt_str = t.get("datetime", "")
                if not dt_str:
                    return "全天"
                try:
                    import re
                    m = re.search(r'T(\d{2}):(\d{2})', dt_str)
                    if m:
                        return f"{m.group(1)}:{m.group(2)}"
                except Exception:
                    pass
                return "全天"

            organizer_cal_id = ev.get("organizer_calendar_id", "")
            is_organizer = bool(user_cal_id and organizer_cal_id and
                                user_cal_id == organizer_cal_id)
            events.append({
                "event_id":    ev.get("event_id", ""),
                "summary":     ev.get("summary") or "(无标题)",
                "description": ev.get("description", ""),
                "start":       _fmt(st),
                "end":         _fmt(et),
                "start_ts":    st.get("timestamp", ""),
                "end_ts":      et.get("timestamp", ""),
                "rsvp":        ev.get("self_rsvp_status", "needs_action"),
                "meeting_url": ev.get("vchat", {}).get("meeting_url", ""),
                "organizer":   organizer_cal_id,
                "is_organizer": is_organizer,
            })

        events.sort(key=lambda e: e["start"])
        return events

    def update_event_rsvp(self, user_token: str, event_id: str,
                          user_open_id: str, rsvp_status: str) -> dict:
        """更新当前用户对某日程的 RSVP 状态（accept / tentative / decline）。
        使用专用的 /reply 端点，所需 scope：calendar:calendar.event:reply
        """
        import logging
        _log = logging.getLogger(__name__)

        hdrs = {"Authorization": f"Bearer {user_token}",
                "Content-Type": "application/json; charset=utf-8"}

        cal_id = self._get_primary_cal_id(user_token) or "primary"

        r = requests.post(
            f"{FEISHU_API}/calendar/v4/calendars/{cal_id}/events/{event_id}/reply",
            headers=hdrs,
            json={"rsvp_status": rsvp_status},
            timeout=10,
        )
        data = r.json()
        _log.info("[RSVP] POST /reply cal=%s event=%s rsvp=%s code=%s msg=%s",
                  cal_id, event_id, rsvp_status, data.get("code"), data.get("msg"))
        return {"success": data.get("code", -1) == 0,
                "code": data.get("code"), "msg": data.get("msg", "")}

    def get_event_detail(self, user_token: str, event_id: str) -> dict:
        """获取日程详情（organizer 用于编辑表单）。"""
        hdrs = {"Authorization": f"Bearer {user_token}"}
        cal_id = self._get_primary_cal_id(user_token) or "primary"
        r = requests.get(
            f"{FEISHU_API}/calendar/v4/calendars/{cal_id}/events/{event_id}",
            headers=hdrs,
            timeout=10,
        )
        data = r.json()
        if data.get("code", -1) != 0:
            return {"success": False, "msg": data.get("msg", ""), "event": None}
        ev = data.get("data", {}).get("event", {})
        return {"success": True, "event": ev}

    def update_event(self, user_token: str, event_id: str, fields: dict) -> dict:
        """更新日程字段（仅 organizer 可操作）。fields 可含 summary/description。"""
        hdrs = {"Authorization": f"Bearer {user_token}",
                "Content-Type": "application/json"}
        cal_id = self._get_primary_cal_id(user_token) or "primary"
        r = requests.patch(
            f"{FEISHU_API}/calendar/v4/calendars/{cal_id}/events/{event_id}",
            headers=hdrs,
            json={**fields, "need_notification": False},
            timeout=10,
        )
        data = r.json()
        return {"success": data.get("code", -1) == 0,
                "code": data.get("code"), "msg": data.get("msg", "")}

    def search_docs(self, user_access_token: str, q: str, limit: int = 5) -> list:
        """
        使用用户 access_token 搜索飞书云文档。
        主力：POST /suite/docs-api/search/object（实测可用）
        补充：POST /wiki/v2/nodes/search（知识库，需 wiki:wiki:readonly）
        返回：[{name, url, type, owner_name}, ...]
        """
        import logging
        _log = logging.getLogger(__name__)

        def _fix_url(url: str, token: str, doc_type: str) -> str:
            if not url or url.startswith("https://applink/") or url.startswith("feishu://"):
                return _build_doc_web_url(token, doc_type) if token else ""
            return url

        title_hits: list = []
        content_hits: list = []
        seen_urls: set = set()

        def _add(item: dict):
            url = item.get("url", "")
            if not url or url in seen_urls:
                return
            seen_urls.add(url)
            if q.lower() in (item.get("name") or "").lower():
                title_hits.append(item)
            else:
                content_hits.append(item)

        # ── 主力：suite/docs-api/search/object ───────────────────────────────
        try:
            resp_b = requests.post(
                f"{FEISHU_API}/suite/docs-api/search/object",
                headers={"Authorization": f"Bearer {user_access_token}",
                         "Content-Type": "application/json"},
                json={"search_key": q, "count": 50, "offset": 0,
                      "docs_types": ["doc", "docx", "sheet", "bitable", "mindnote", "file"]},
                timeout=10,
            )
            data_b = resp_b.json()
            if data_b.get("code") == 0:
                for e in ((data_b.get("data") or {}).get("docs_entities", []) or []):
                    token_ = e.get("docs_token", "")
                    doc_type = e.get("docs_type", "")
                    url = _fix_url(e.get("url", ""), token_, doc_type)
                    if url:
                        _add({"name": e.get("title", ""), "url": url, "type": doc_type,
                              "owner_name": e.get("owner_id", "")})
            else:
                _log.warning("[search_docs] suite/docs-api 失败: code=%s msg=%s",
                             data_b.get("code"), data_b.get("msg"))
        except Exception as e:
            _log.warning("[search_docs] suite/docs-api 异常: %s", e)

        # ── 补充：Wiki 知识库（未授权时静默跳过）────────────────────────────────
        try:
            resp_w = requests.post(
                f"{FEISHU_API}/wiki/v2/nodes/search",
                headers={"Authorization": f"Bearer {user_access_token}",
                         "Content-Type": "application/json"},
                json={"query": q, "search_limit": 20},
                timeout=10,
            )
            data_w = resp_w.json()
            if data_w.get("code") == 0:
                for n in ((data_w.get("data") or {}).get("items", []) or []):
                    token_ = n.get("node_token", "")
                    url = f"https://{FEISHU_WEB_DOMAIN}/wiki/{token_}" if token_ else ""
                    if url:
                        creator = n.get("creator", {})
                        _add({"name": n.get("title", ""), "url": url, "type": "wiki",
                              "owner_name": creator.get("id", "") if isinstance(creator, dict) else ""})
        except Exception as e:
            _log.warning("[search_docs] wiki 异常: %s", e)

        return (title_hits + content_hits)[:limit]


feishu_service = FeishuService()
