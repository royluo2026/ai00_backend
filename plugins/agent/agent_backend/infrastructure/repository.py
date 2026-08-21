from __future__ import annotations

import json
import uuid
from backend.platform_sdk.ids import next_gid
from ..data.connection import get_agent_conn


class AgentCapabilityRepository:
    def runtime_config(self, data: dict) -> dict:
        import os

        is_admin = "super_admin" in set(data.get("active_roles", ()))
        if os.getenv("AI00_AGENT_RUNTIME_MODE", "pi").strip().lower() == "pi":
            return {
                "source": "pi_runtime",
                "model": "由 Agent Runtime 管理",
                "has_key": True,
                "key_preview": "",
                "is_admin": is_admin,
            }
        key = os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        model = os.getenv("AI_MODEL", "anthropic/claude-sonnet-4-6")
        api_base = os.getenv("AI_API_BASE", "")
        key_preview = (key[:4] + "••••" + key[-4:]) if len(key) > 8 else ("•" * len(key))
        result = {
            "source": "env" if key else "none",
            "model": model if key else "",
            "has_key": bool(key),
            "key_preview": key_preview,
            "is_admin": is_admin,
        }
        if is_admin:
            result["api_base"] = api_base
        return result

    def generate_script(self, data: dict) -> dict:
        """Generate non-executed data-transform code through the deployment model secret."""
        import os

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "ANTHROPIC_API_KEY 未配置；模型密钥只能来自部署 Secret"}
        description = str(data.get("description") or "").strip()
        if not description or len(description) > 4000:
            return {"success": False, "error": "description must contain 1-4000 characters"}
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=os.getenv("AI_SCRIPT_MODEL", "claude-sonnet-4-6"),
                max_tokens=1024,
                system=(
                    "生成只操作 inputs/outputs 字典的受限 Python 数据处理代码；"
                    "禁止系统、网络和文件 API。只输出代码。"
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"需求：{description}\n"
                        f"inputs：{json.dumps(data.get('inputs_schema') or {}, ensure_ascii=False)}\n"
                        f"outputs：{json.dumps(data.get('outputs_schema') or {}, ensure_ascii=False)}"
                    ),
                }],
            )
            code = response.content[0].text if response.content else ""
            if code.startswith("```"):
                lines = code.splitlines()
                code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            if len(code) > 20000:
                return {"success": False, "error": "generated code exceeds the 20000 character limit"}
            return {"success": True, "code": code}
        except Exception as exc:
            return {"success": False, "error": str(exc)[:300]}

    def read(self, data: dict) -> dict:
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                if data.get("resource_gid"):
                    cur.execute("SELECT resource_gid,resource_type,version,status,content_json FROM workmanship_agent_capability_resources WHERE resource_gid=%s AND tenant_gid=%s AND owner_gid=%s", (data["resource_gid"], data["tenant_gid"], data["owner_gid"]))
                    row = cur.fetchone()
                    return dict(row) if row else {"resource_gid": data["resource_gid"], "version": 0, "status": "not_found", "content": {}}
                cur.execute("SELECT resource_gid,resource_type,version,status,content_json FROM workmanship_agent_capability_resources WHERE resource_type=%s AND tenant_gid=%s AND owner_gid=%s ORDER BY updated_at DESC LIMIT %s", (data["resource_type"], data["tenant_gid"], data["owner_gid"], min(int(data.get("limit", 100)), 200)))
                return {"items": [dict(row) for row in cur.fetchall()]}

    def apply(self, data: dict) -> dict:
        gid = str(data.get("resource_gid") or next_gid())
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_agent_capability_resources (resource_gid,resource_type,tenant_gid,owner_gid,version,status,content_json) VALUES (%s,%s,%s,%s,1,%s,%s) ON DUPLICATE KEY UPDATE version=version+1,status=VALUES(status),content_json=VALUES(content_json)", (gid, data["resource_type"], data["tenant_gid"], data["owner_gid"], data.get("status", "active"), json.dumps(data.get("content", {}))))
            conn.commit()
        return {"resource_gid": gid, "version": int(data.get("expected_version", 0)) + 1, "status": data.get("status", "active")}

    def request_interaction(self, data: dict) -> dict:
        return {"interaction_id": str(next_gid()), "status": "requested"}

    @staticmethod
    def _flow_row(row: dict) -> dict:
        return {
            "gid": row["gid"], "name": row["name"],
            "description": row.get("description") or "",
            "status": row.get("status") or "draft",
            "last_run_at": str(row["last_run_at"]) if row.get("last_run_at") else None,
            "created_at": str(row.get("created_at")),
            "updated_at": str(row.get("updated_at")),
        }

    @staticmethod
    def _run_row(row: dict) -> dict:
        return {
            "gid": row["gid"], "flow_gid": row["flow_gid"],
            "status": row.get("status") or "pending",
            "mode": row.get("mode") or "auto",
            "current_node_id": row.get("current_node_id"),
            "error_msg": row.get("error_msg"),
            "started_at": str(row["started_at"]) if row.get("started_at") else None,
            "completed_at": str(row["completed_at"]) if row.get("completed_at") else None,
        }

    def flow_read(self, data: dict) -> dict:
        operation = data.get("operation", "list")
        owner = data["owner_gid"]
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "manifest":
                return {
                    "manifest": [],
                    "message": "Flow 节点必须从 Capability Catalog 选择；旧进程内 node_registry 已停用",
                }
            if operation == "list":
                cur.execute(
                    "SELECT * FROM workmanship_app_flows WHERE owner_user_gid=%s AND deleted_at IS NULL ORDER BY updated_at DESC",
                    (owner,),
                )
                return {"items": [self._flow_row(dict(row)) for row in cur.fetchall()]}
            if operation == "get":
                cur.execute(
                    "SELECT * FROM workmanship_app_flows WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL",
                    (data["flow_gid"], owner),
                )
                row = cur.fetchone()
                if not row:
                    raise LookupError("flow 不存在")
                result = self._flow_row(dict(row))
                result["flowdef"] = row.get("flowdef") or ""
                return result
            if operation == "list_runs":
                cur.execute(
                    "SELECT r.* FROM workmanship_app_flow_runs r JOIN workmanship_app_flows f ON f.gid=r.flow_gid WHERE r.flow_gid=%s AND f.owner_user_gid=%s ORDER BY r.started_at DESC LIMIT %s",
                    (data["flow_gid"], owner, min(max(int(data.get("limit", 10)), 1), 100)),
                )
                return {"items": [self._run_row(dict(row)) for row in cur.fetchall()]}
            if operation == "get_run":
                cur.execute(
                    "SELECT r.* FROM workmanship_app_flow_runs r JOIN workmanship_app_flows f ON f.gid=r.flow_gid WHERE r.gid=%s AND f.owner_user_gid=%s",
                    (data["run_gid"], owner),
                )
                row = cur.fetchone()
                if not row:
                    raise LookupError("run_gid 不存在")
                return self._run_row(dict(row))
        raise ValueError("unsupported flow read operation")

    def flow_apply(self, data: dict) -> dict:
        operation = data.get("operation")
        owner = data["owner_gid"]
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "create":
                gid = str(data.get("resource_gid") or uuid.uuid4())
                cur.execute(
                    "INSERT INTO workmanship_app_flows (gid, owner_user_gid, name, description, flowdef, status, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW())",
                    (gid, owner, data.get("name", ""), data.get("description", ""), data.get("flowdef", ""), data.get("status", "draft")),
                )
                return {"gid": gid, "name": data.get("name", "")}
            if operation == "update":
                allowed = ("name", "description", "flowdef", "status")
                updates = {key: data[key] for key in allowed if key in data}
                if not updates:
                    return {"success": True}
                clause = ", ".join(f"{key}=%s" for key in updates)
                cur.execute(
                    f"UPDATE workmanship_app_flows SET {clause}, updated_at=NOW() WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL",
                    [*updates.values(), data["flow_gid"], owner],
                )
                if cur.rowcount != 1:
                    raise LookupError("flow 不存在")
                return {"success": True}
            if operation == "delete":
                cur.execute(
                    "UPDATE workmanship_app_flows SET deleted_at=NOW() WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL",
                    (data["flow_gid"], owner),
                )
                if cur.rowcount != 1:
                    raise LookupError("flow 不存在")
                return {"success": True}
            if operation == "run":
                run_gid = str(data.get("run_gid") or uuid.uuid4())
                cur.execute(
                    "INSERT INTO workmanship_app_flow_runs (gid, flow_gid, status, mode, started_at) SELECT %s, gid, 'running', %s, NOW() FROM workmanship_app_flows WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL",
                    (run_gid, data.get("mode", "auto"), data["flow_gid"], owner),
                )
                if cur.rowcount != 1:
                    raise LookupError("flow 不存在")
                return {"run_gid": run_gid}
        raise ValueError("unsupported flow write operation")

    @staticmethod
    def _skill_row(row: dict) -> dict:
        return {
            "gid": row["gid"], "name": row["name"], "title": row["title"],
            "description": row.get("description") or "", "skill_type": row["skill_type"],
            "scope": row.get("scope") or "private", "status": row.get("status") or "draft",
            "owner_gid": row.get("owner_gid") or "", "is_system": bool(row.get("is_system")),
            "content": json.dumps(row.get("content"), ensure_ascii=False) if isinstance(row.get("content"), (dict, list)) else (row.get("content") or "{}"),
            "icon": row.get("icon") or "", "tags": json.dumps(row.get("tags"), ensure_ascii=False) if isinstance(row.get("tags"), list) else (row.get("tags") or "[]"),
            "sort_order": row.get("sort_order", 0), "is_pinned": bool(row.get("is_pinned")),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    def skill_read(self, data: dict) -> dict:
        operation = data.get("operation", "list")
        owner = data["owner_gid"]
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "list":
                cur.execute(
                    "SELECT * FROM workmanship_app_skills WHERE deleted_at IS NULL AND (owner_gid=%s OR owner_gid='__system__' OR scope='global') ORDER BY sort_order, created_at",
                    (owner,),
                )
                rows = [self._skill_row(dict(row)) for row in cur.fetchall()]
                scope_filter = data.get("scope_filter", "all")
                if scope_filter == "mine":
                    rows = [row for row in rows if row["owner_gid"] in {owner, "__system__"}]
                elif scope_filter == "team":
                    rows = [row for row in rows if row["scope"] == "team"]
                elif scope_filter == "global":
                    rows = [row for row in rows if row["scope"] == "global"]
                return rows
            if operation == "get":
                cur.execute(
                    "SELECT * FROM workmanship_app_skills WHERE gid=%s AND deleted_at IS NULL AND (owner_gid=%s OR owner_gid='__system__' OR scope='global')",
                    (data["skill_gid"], owner),
                )
                row = cur.fetchone()
                if not row:
                    raise LookupError("Skill 不存在")
                return self._skill_row(dict(row))
        raise ValueError("unsupported skill read operation")

    def skill_apply(self, data: dict) -> dict:
        operation = data.get("operation")
        owner = data["owner_gid"]
        is_admin = "super_admin" in set(data.get("active_roles", ()))
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "create":
                scope = data.get("scope", "private")
                if scope == "team":
                    raise ValueError("团队 Skill 必须等待 team_gid/ACL 数据模型后启用")
                if scope == "global" and not is_admin:
                    raise PermissionError("只有超级管理员可以创建全局 Skill")
                gid = str(data.get("resource_gid") or uuid.uuid4())
                cur.execute(
                    "INSERT INTO workmanship_app_skills (gid,name,title,description,skill_type,scope,status,owner_gid,is_system,content,icon,tags,sort_order,is_pinned) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (gid, data["name"], data["title"], data.get("description", ""), data.get("skill_type", "prompt"), scope, "draft", owner, False, json.dumps(data.get("content", {}), ensure_ascii=False), data.get("icon", ""), json.dumps(data.get("tags", []), ensure_ascii=False), data.get("sort_order", 0), False),
                )
                return {"gid": gid, "success": True}
            if operation == "update":
                if data.get("scope") == "team":
                    raise ValueError("团队 Skill 必须等待 team_gid/ACL 数据模型后启用")
                if data.get("scope") == "global" and not is_admin:
                    raise PermissionError("只有超级管理员可以发布全局 Skill")
                cur.execute("SELECT * FROM workmanship_app_skills WHERE gid=%s AND deleted_at IS NULL", (data["skill_gid"],))
                row = cur.fetchone()
                if not row:
                    raise LookupError("Skill 不存在")
                if row["is_system"]:
                    raise PermissionError("系统预设 Skill 不可修改")
                if row["owner_gid"] != owner and not is_admin:
                    raise PermissionError("无权修改此 Skill")
                fields = ("title", "description", "scope", "status", "icon", "sort_order", "is_pinned")
                updates = {field: data[field] for field in fields if field in data}
                if "content" in data:
                    updates["content"] = json.dumps(data["content"], ensure_ascii=False)
                if "tags" in data:
                    updates["tags"] = json.dumps(data["tags"], ensure_ascii=False)
                if updates:
                    clause = ",".join(f"{field}=%s" for field in updates)
                    cur.execute(f"UPDATE workmanship_app_skills SET {clause},updated_at=NOW() WHERE gid=%s", [*updates.values(), data["skill_gid"]])
                return {"success": True}
            if operation == "delete":
                cur.execute("SELECT is_system, owner_gid FROM workmanship_app_skills WHERE gid=%s AND deleted_at IS NULL", (data["skill_gid"],))
                row = cur.fetchone()
                if not row:
                    raise LookupError("Skill 不存在")
                if row["is_system"]:
                    raise PermissionError("系统预设 Skill 不可删除")
                if row["owner_gid"] != owner and not is_admin:
                    raise PermissionError("无权删除此 Skill")
                cur.execute("UPDATE workmanship_app_skills SET deleted_at=NOW() WHERE gid=%s", (data["skill_gid"],))
                return {"success": True}
            if operation == "seed_system":
                seeded = []
                for skill in data.get("system_skills", []):
                    content = skill.get("content", {})
                    tags = skill.get("tags", [])
                    cur.execute("SELECT gid FROM workmanship_app_skills WHERE name=%s AND deleted_at IS NULL", (skill["name"],))
                    existing = cur.fetchone()
                    if existing:
                        cur.execute("UPDATE workmanship_app_skills SET title=%s,description=%s,content=%s,icon=%s,tags=%s,sort_order=%s,is_system=TRUE,scope='global',status='active',updated_at=NOW() WHERE gid=%s", (skill["title"], skill.get("description", ""), json.dumps(content, ensure_ascii=False), skill.get("icon", ""), json.dumps(tags, ensure_ascii=False), skill.get("sort_order", 0), existing["gid"]))
                        seeded.append({"name": skill["name"], "action": "updated", "gid": existing["gid"]})
                    else:
                        gid = str(uuid.uuid4())
                        cur.execute("INSERT INTO workmanship_app_skills (gid,name,title,description,skill_type,scope,status,owner_gid,is_system,content,icon,tags,sort_order) VALUES (%s,%s,%s,%s,%s,'global','active','__system__',TRUE,%s,%s,%s,%s)", (gid, skill["name"], skill["title"], skill.get("description", ""), skill.get("skill_type", "prompt"), json.dumps(content, ensure_ascii=False), skill.get("icon", ""), json.dumps(tags, ensure_ascii=False), skill.get("sort_order", 0)))
                        seeded.append({"name": skill["name"], "action": "created", "gid": gid})
                return {"success": True, "seeded": seeded}
        raise ValueError("unsupported skill write operation")
