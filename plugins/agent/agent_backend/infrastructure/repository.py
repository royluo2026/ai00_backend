from __future__ import annotations

import json
import hashlib
import secrets
import uuid
from backend.platform_sdk.ids import next_gid
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from ..data.connection import get_agent_conn


class AgentCapabilityRepository:
    @staticmethod
    def _token_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _json(value):
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        return json.loads(value) if isinstance(value, str) else value

    @classmethod
    def _canvas_invocation(cls, row) -> dict:
        value = dict(row)
        value["request"] = cls._json(value.pop("request_json"))
        value["result"] = cls._json(value.pop("result_json"))
        value["run_token"] = str(value["result"].get("run_token") or "")
        value["principal"] = {
            "actor_gid": str(value["actor_gid"]), "team_gid": str(value["team_gid"]),
        }
        value["reconcile"] = value.get("target_dispatched_at") is not None
        return value

    @staticmethod
    def _canvas_not_found() -> CapabilityBusinessError:
        return CapabilityBusinessError("resource_not_found", "Agent canvas execution was not found")

    @staticmethod
    def _canvas_audit(cur, row, *, status=None, error_code=None) -> None:
        cur.execute(
            "INSERT INTO workmanship_agent_canvas_audit_events "
            "(event_id,invocation_id,run_id,actor_gid,team_gid,status,revision,error_code) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                str(next_gid()), row["invocation_id"], row["run_id"], row["actor_gid"],
                row["team_gid"], status or row["status"], row["revision"], error_code,
            ),
        )

    @staticmethod
    def _duplicate_key(exc: Exception) -> bool:
        return bool(exc.args and exc.args[0] == 1062) or "duplicate" in str(exc).casefold()

    @classmethod
    def _select_canvas_idempotency(cls, cur, data, *, lock=False):
        cur.execute(
            "SELECT i.*,r.result_json AS run_result_json FROM workmanship_agent_canvas_invocations i "
            "JOIN workmanship_agent_canvas_runs r ON r.run_id=i.run_id "
            "WHERE i.actor_gid=%s AND i.team_gid=%s AND i.capability_id=%s AND i.idempotency_key=%s"
            + (" FOR UPDATE" if lock else ""),
            (data["actor_gid"], data["team_gid"], data["capability_id"], data["idempotency_key"]),
        )
        row = cur.fetchone()
        return cls._canvas_invocation(row) if row else None

    @staticmethod
    def _idempotent(existing, data):
        if existing["payload_hash"] != data["payload_hash"]:
            raise CapabilityBusinessError(
                "idempotency_conflict", "Agent canvas idempotency key conflicts with an earlier request",
            )
        return existing, True

    def _reload_canvas_idempotency(self, data, original):
        with get_agent_conn() as conn, conn.cursor() as cur:
            winner = self._select_canvas_idempotency(cur, data)
        if winner is None:
            raise RuntimeError("Agent canvas idempotency winner could not be reloaded") from original
        return self._idempotent(winner, data)

    def create_canvas_start(self, data):
        try:
            with get_agent_conn() as conn, conn.cursor() as cur:
                existing = self._select_canvas_idempotency(cur, data, lock=True)
                if existing is not None:
                    return self._idempotent(existing, data)
                request = data["request"]
                cur.execute(
                    "SELECT gid,revision FROM workmanship_app_skills WHERE gid=%s AND team_gid=%s "
                    "AND deleted_at IS NULL AND (owner_gid=%s OR scope='team' OR "
                    "(scope='global' AND status='active')) FOR UPDATE",
                    (request["skill_gid"], data["team_gid"], data["actor_gid"]),
                )
                skill = cur.fetchone()
                if skill is None:
                    raise self._canvas_not_found()
                if int(skill.get("revision") or 1) != int(request["expected_revision"]):
                    raise CapabilityBusinessError("version_conflict", "Agent canvas revision changed")
                result_json = json.dumps(data["result"], ensure_ascii=False, separators=(",", ":"))
                cur.execute(
                    "INSERT INTO workmanship_agent_canvas_runs "
                    "(run_id,run_token_hash,actor_gid,team_gid,skill_gid,skill_revision,status,revision,result_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'accepted',1,%s)",
                    (
                        data["run_id"], self._token_hash(data["run_token"]), data["actor_gid"],
                        data["team_gid"], request["skill_gid"], request["expected_revision"], result_json,
                    ),
                )
                row = {
                    **data, "status": "accepted", "revision": 1, "attempt_count": 0,
                    "lease_owner": None, "lease_token": None, "lease_expires_at": None,
                    "target_dispatched_at": None, "next_attempt_at": None,
                }
                cur.execute(
                    "INSERT INTO workmanship_agent_canvas_invocations "
                    "(invocation_id,run_id,actor_gid,team_gid,capability_id,idempotency_key,payload_hash,"
                    "target_state,request_json,status,revision,result_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'accepted',1,%s)",
                    (
                        data["invocation_id"], data["run_id"], data["actor_gid"], data["team_gid"],
                        data["capability_id"], data["idempotency_key"], data["payload_hash"],
                        data["target_state"], json.dumps(request, ensure_ascii=False), result_json,
                    ),
                )
                self._canvas_audit(cur, row)
                row["result"] = dict(data["result"])
                return row, False
        except Exception as exc:
            if not self._duplicate_key(exc):
                raise
            return self._reload_canvas_idempotency(data, exc)

    def create_canvas_resume(self, data):
        try:
            with get_agent_conn() as conn, conn.cursor() as cur:
                existing = self._select_canvas_idempotency(cur, data, lock=True)
                if existing is not None:
                    return self._idempotent(existing, data)
                request = data["request"]
                cur.execute(
                    "SELECT * FROM workmanship_agent_canvas_runs WHERE run_token_hash=%s "
                    "AND pause_token_hash=%s AND actor_gid=%s AND team_gid=%s AND status='paused' "
                    "AND revision=%s FOR UPDATE",
                    (
                        self._token_hash(request["run_token"]), self._token_hash(request["pause_token"]),
                        data["actor_gid"], data["team_gid"], request["expected_revision"],
                    ),
                )
                run = cur.fetchone()
                if run is None:
                    raise self._canvas_not_found()
                revision = int(request["expected_revision"]) + 1
                result_json = json.dumps(data["result"], ensure_ascii=False, separators=(",", ":"))
                cur.execute(
                    "UPDATE workmanship_agent_canvas_runs SET status='accepted',revision=%s,"
                    "pause_token_hash=NULL,result_json=%s WHERE run_id=%s AND status='paused' AND revision=%s",
                    (revision, result_json, run["run_id"], request["expected_revision"]),
                )
                if cur.rowcount != 1:
                    raise self._canvas_not_found()
                row = {
                    **data, "run_id": run["run_id"], "run_token": request["run_token"],
                    "status": "accepted", "revision": revision, "attempt_count": 0,
                    "lease_owner": None, "lease_token": None, "lease_expires_at": None,
                    "target_dispatched_at": None, "next_attempt_at": None,
                }
                cur.execute(
                    "INSERT INTO workmanship_agent_canvas_invocations "
                    "(invocation_id,run_id,actor_gid,team_gid,capability_id,idempotency_key,payload_hash,"
                    "target_state,request_json,status,revision,result_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'accepted',%s,%s)",
                    (
                        data["invocation_id"], run["run_id"], data["actor_gid"], data["team_gid"],
                        data["capability_id"], data["idempotency_key"], data["payload_hash"],
                        data["target_state"], json.dumps(request, ensure_ascii=False), revision, result_json,
                    ),
                )
                self._canvas_audit(cur, row)
                row["result"] = dict(data["result"])
                return row, False
        except Exception as exc:
            if not self._duplicate_key(exc):
                raise
            return self._reload_canvas_idempotency(data, exc)

    def claim_next_canvas_invocation(self, worker_id: str):
        lease_token = f"{str(worker_id).strip()}:{secrets.token_urlsafe(24)}"
        with get_agent_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT i.*,r.result_json AS run_result_json FROM workmanship_agent_canvas_invocations i "
                "JOIN workmanship_agent_canvas_runs r ON r.run_id=i.run_id WHERE "
                "i.status='accepted' OR "
                "(i.status='reconcile_pending' AND i.next_attempt_at<=NOW(6) AND i.attempt_count<3) OR "
                "(i.status='claimed' AND i.lease_expires_at<NOW(6)) "
                "ORDER BY i.created_at,i.invocation_id LIMIT 1 FOR UPDATE SKIP LOCKED"
            )
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                "UPDATE workmanship_agent_canvas_invocations SET status='claimed',lease_owner=%s,"
                "lease_token=%s,lease_expires_at=DATE_ADD(NOW(6),INTERVAL 30 SECOND) "
                "WHERE invocation_id=%s AND (status='accepted' OR status='reconcile_pending' OR "
                "(status='claimed' AND lease_expires_at<NOW(6)))",
                (worker_id, lease_token, row["invocation_id"]),
            )
            if cur.rowcount != 1:
                return None
        row = dict(row)
        row.update(status="claimed", lease_owner=worker_id, lease_token=lease_token)
        return self._canvas_invocation(row)

    def mark_canvas_invocation_dispatched(self, claim):
        with get_agent_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_agent_canvas_invocations SET target_dispatched_at=COALESCE("
                "target_dispatched_at,NOW(6)),attempt_count=attempt_count+1 WHERE invocation_id=%s "
                "AND status='claimed' AND lease_token=%s",
                (claim["invocation_id"], claim["lease_token"]),
            )
            if cur.rowcount != 1:
                raise CapabilityBusinessError("version_conflict", "Agent canvas invocation claim changed")

    def complete_canvas_invocation(self, claim, result):
        if isinstance(result, dict):
            result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            status, revision, pause_token = result["status"], result["revision"], result.get("pause_token")
        else:
            from dataclasses import asdict
            result_json = json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":"))
            status, revision, pause_token = result.status, result.revision, result.pause_token
        with get_agent_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_agent_canvas_invocations WHERE invocation_id=%s "
                "AND status='claimed' AND lease_token=%s FOR UPDATE",
                (claim["invocation_id"], claim["lease_token"]),
            )
            invocation = cur.fetchone()
            if invocation is None or int(invocation["revision"]) != int(revision):
                raise CapabilityBusinessError("version_conflict", "Agent canvas invocation claim changed")
            cur.execute(
                "UPDATE workmanship_agent_canvas_invocations SET status=%s,result_json=%s,error_code=NULL,"
                "lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,next_attempt_at=NULL "
                "WHERE invocation_id=%s AND status='claimed' AND lease_token=%s",
                (status, result_json, claim["invocation_id"], claim["lease_token"]),
            )
            pause_hash = self._token_hash(pause_token) if pause_token else None
            cur.execute(
                "UPDATE workmanship_agent_canvas_runs SET status=%s,revision=%s,pause_token_hash=%s,"
                "checkpoint_json=%s,result_json=%s WHERE run_id=%s",
                (status, revision, pause_hash, result_json, result_json, invocation["run_id"]),
            )
            row = dict(invocation)
            row.update(status=status, result=self._json(result_json))
            self._canvas_audit(cur, row, status=status)
        return row

    def record_canvas_uncertainty(self, claim, result, error_code):
        from dataclasses import asdict
        result_json = json.dumps(asdict(result), ensure_ascii=False, separators=(",", ":"))
        with get_agent_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_agent_canvas_invocations WHERE invocation_id=%s "
                "AND status='claimed' AND lease_token=%s FOR UPDATE",
                (claim["invocation_id"], claim["lease_token"]),
            )
            invocation = cur.fetchone()
            if invocation is None:
                raise CapabilityBusinessError("version_conflict", "Agent canvas invocation claim changed")
            attempts = max(1, int(invocation.get("attempt_count") or 0) + (1 if claim.get("reconcile") else 0))
            status = "outcome_unknown" if attempts >= 3 else "reconcile_pending"
            cur.execute(
                "UPDATE workmanship_agent_canvas_invocations SET status=%s,attempt_count=%s,result_json=%s,"
                "error_code=%s,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,"
                "next_attempt_at=DATE_ADD(NOW(6),INTERVAL %s SECOND) WHERE invocation_id=%s "
                "AND status='claimed' AND lease_token=%s",
                (
                    status, attempts, result_json, str(error_code)[:128], min(60, 2 ** attempts),
                    claim["invocation_id"], claim["lease_token"],
                ),
            )
            cur.execute(
                "UPDATE workmanship_agent_canvas_runs SET status='outcome_unknown',result_json=%s "
                "WHERE run_id=%s",
                (result_json, invocation["run_id"]),
            )
            row = dict(invocation)
            row.update(status=status, result=self._json(result_json), attempt_count=attempts)
            self._canvas_audit(cur, row, status=status, error_code=str(error_code)[:128])
        return row

    def load_canvas_execution_state(self, run_token: str, actor_gid: str, team_gid: str):
        with get_agent_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_agent_canvas_runs WHERE run_token_hash=%s "
                "AND actor_gid=%s AND team_gid=%s",
                (self._token_hash(run_token), actor_gid, team_gid),
            )
            row = cur.fetchone()
        if row is None:
            return None
        value = dict(row)
        value["checkpoint"] = self._json(value.pop("checkpoint_json"))
        value["result"] = self._json(value.pop("result_json"))
        return value

    def load_canvas_resource(
        self, kind: str, gid: str, actor_gid: str, team_gid: str,
    ) -> dict | None:
        if kind not in {"flow", "skill"}:
            raise ValueError("unsupported canvas resource kind")
        table = "workmanship_app_flows" if kind == "flow" else "workmanship_app_skills"
        if kind == "flow":
            visibility = "owner_user_gid=%s"
        else:
            visibility = "(owner_gid=%s OR scope='team' OR (scope='global' AND status='active'))"
        with get_agent_conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {table} WHERE gid=%s AND {visibility} AND team_gid=%s AND deleted_at IS NULL",
                (gid, actor_gid, team_gid),
            )
            row = cur.fetchone()
        return dict(row) if row else None

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
        team = data["tenant_gid"]
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "manifest":
                return {
                    "manifest": [],
                    "message": "Flow 节点必须从 Capability Catalog 选择；旧进程内 node_registry 已停用",
                }
            if operation == "list":
                cur.execute(
                    "SELECT * FROM workmanship_app_flows WHERE owner_user_gid=%s AND team_gid=%s AND deleted_at IS NULL ORDER BY updated_at DESC",
                    (owner, team),
                )
                return {"items": [self._flow_row(dict(row)) for row in cur.fetchall()]}
            if operation == "get":
                cur.execute(
                    "SELECT * FROM workmanship_app_flows WHERE gid=%s AND owner_user_gid=%s AND team_gid=%s AND deleted_at IS NULL",
                    (data["flow_gid"], owner, team),
                )
                row = cur.fetchone()
                if not row:
                    raise LookupError("flow 不存在")
                result = self._flow_row(dict(row))
                result["flowdef"] = row.get("flowdef") or ""
                return result
            if operation == "list_runs":
                cur.execute(
                    "SELECT r.* FROM workmanship_app_flow_runs r JOIN workmanship_app_flows f ON f.gid=r.flow_gid WHERE r.flow_gid=%s AND f.owner_user_gid=%s AND f.team_gid=%s ORDER BY r.started_at DESC LIMIT %s",
                    (data["flow_gid"], owner, team, min(max(int(data.get("limit", 10)), 1), 100)),
                )
                return {"items": [self._run_row(dict(row)) for row in cur.fetchall()]}
            if operation == "get_run":
                cur.execute(
                    "SELECT r.* FROM workmanship_app_flow_runs r JOIN workmanship_app_flows f ON f.gid=r.flow_gid WHERE r.gid=%s AND f.owner_user_gid=%s AND f.team_gid=%s",
                    (data["run_gid"], owner, team),
                )
                row = cur.fetchone()
                if not row:
                    raise LookupError("run_gid 不存在")
                return self._run_row(dict(row))
        raise ValueError("unsupported flow read operation")

    def flow_apply(self, data: dict) -> dict:
        operation = data.get("operation")
        owner = data["owner_gid"]
        team = data["tenant_gid"]
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "create":
                gid = str(data.get("resource_gid") or uuid.uuid4())
                cur.execute(
                    "INSERT INTO workmanship_app_flows (gid, owner_user_gid, team_gid, name, description, flowdef, status, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())",
                    (gid, owner, team, data.get("name", ""), data.get("description", ""), data.get("flowdef", ""), data.get("status", "draft")),
                )
                return {"gid": gid, "name": data.get("name", "")}
            if operation == "update":
                allowed = ("name", "description", "flowdef", "status")
                updates = {key: data[key] for key in allowed if key in data}
                if not updates:
                    return {"success": True}
                clause = ", ".join(f"{key}=%s" for key in updates)
                cur.execute(
                    f"UPDATE workmanship_app_flows SET {clause}, updated_at=NOW() WHERE gid=%s AND owner_user_gid=%s AND team_gid=%s AND deleted_at IS NULL",
                    [*updates.values(), data["flow_gid"], owner, team],
                )
                if cur.rowcount != 1:
                    raise LookupError("flow 不存在")
                return {"success": True}
            if operation == "delete":
                cur.execute(
                    "UPDATE workmanship_app_flows SET deleted_at=NOW() WHERE gid=%s AND owner_user_gid=%s AND team_gid=%s AND deleted_at IS NULL",
                    (data["flow_gid"], owner, team),
                )
                if cur.rowcount != 1:
                    raise LookupError("flow 不存在")
                return {"success": True}
            if operation == "run":
                run_gid = str(data.get("run_gid") or uuid.uuid4())
                cur.execute(
                    "INSERT INTO workmanship_app_flow_runs (gid, flow_gid, status, mode, started_at) SELECT %s, gid, 'running', %s, NOW() FROM workmanship_app_flows WHERE gid=%s AND owner_user_gid=%s AND team_gid=%s AND deleted_at IS NULL",
                    (run_gid, data.get("mode", "auto"), data["flow_gid"], owner, team),
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
        team = data["tenant_gid"]
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "list":
                cur.execute(
                    "SELECT * FROM workmanship_app_skills WHERE team_gid=%s AND deleted_at IS NULL AND (owner_gid=%s OR scope='team' OR (scope='global' AND status='active')) ORDER BY sort_order, created_at",
                    (team, owner),
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
                    "SELECT * FROM workmanship_app_skills WHERE gid=%s AND team_gid=%s AND deleted_at IS NULL AND (owner_gid=%s OR scope='team' OR (scope='global' AND status='active'))",
                    (data["skill_gid"], team, owner),
                )
                row = cur.fetchone()
                if not row:
                    raise LookupError("Skill 不存在")
                return self._skill_row(dict(row))
        raise ValueError("unsupported skill read operation")

    def skill_apply(self, data: dict) -> dict:
        operation = data.get("operation")
        owner = data["owner_gid"]
        team = data["tenant_gid"]
        is_admin = "super_admin" in set(data.get("active_roles", ()))
        with get_agent_conn() as conn, conn.cursor() as cur:
            if operation == "create":
                scope = data.get("scope", "private")
                if scope == "global" and not is_admin:
                    raise PermissionError("只有超级管理员可以创建全局 Skill")
                gid = str(data.get("resource_gid") or uuid.uuid4())
                cur.execute(
                    "INSERT INTO workmanship_app_skills (gid,name,title,description,skill_type,scope,status,owner_gid,team_gid,is_system,content,icon,tags,sort_order,is_pinned) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (gid, data["name"], data["title"], data.get("description", ""), data.get("skill_type", "prompt"), scope, "draft", owner, team, False, json.dumps(data.get("content", {}), ensure_ascii=False), data.get("icon", ""), json.dumps(data.get("tags", []), ensure_ascii=False), data.get("sort_order", 0), False),
                )
                return {"gid": gid, "success": True}
            if operation == "update":
                if data.get("scope") == "global" and not is_admin:
                    raise PermissionError("只有超级管理员可以发布全局 Skill")
                cur.execute("SELECT * FROM workmanship_app_skills WHERE gid=%s AND team_gid=%s AND deleted_at IS NULL", (data["skill_gid"], team))
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
                    cur.execute(f"UPDATE workmanship_app_skills SET {clause},revision=revision+1,updated_at=NOW() WHERE gid=%s AND team_gid=%s", [*updates.values(), data["skill_gid"], team])
                return {"success": True}
            if operation == "delete":
                cur.execute("SELECT is_system, owner_gid FROM workmanship_app_skills WHERE gid=%s AND team_gid=%s AND deleted_at IS NULL", (data["skill_gid"], team))
                row = cur.fetchone()
                if not row:
                    raise LookupError("Skill 不存在")
                if row["is_system"]:
                    raise PermissionError("系统预设 Skill 不可删除")
                if row["owner_gid"] != owner and not is_admin:
                    raise PermissionError("无权删除此 Skill")
                cur.execute("UPDATE workmanship_app_skills SET deleted_at=NOW() WHERE gid=%s AND team_gid=%s", (data["skill_gid"], team))
                return {"success": True}
            if operation == "seed_system":
                seeded = []
                for skill in data.get("system_skills", []):
                    content = skill.get("content", {})
                    tags = skill.get("tags", [])
                    cur.execute("SELECT gid FROM workmanship_app_skills WHERE name=%s AND team_gid=%s AND deleted_at IS NULL", (skill["name"], team))
                    existing = cur.fetchone()
                    if existing:
                        cur.execute("UPDATE workmanship_app_skills SET title=%s,description=%s,content=%s,icon=%s,tags=%s,sort_order=%s,is_system=TRUE,scope='global',status='active',revision=revision+1,updated_at=NOW() WHERE gid=%s AND team_gid=%s", (skill["title"], skill.get("description", ""), json.dumps(content, ensure_ascii=False), skill.get("icon", ""), json.dumps(tags, ensure_ascii=False), skill.get("sort_order", 0), existing["gid"], team))
                        seeded.append({"name": skill["name"], "action": "updated", "gid": existing["gid"]})
                    else:
                        gid = str(uuid.uuid4())
                        cur.execute("INSERT INTO workmanship_app_skills (gid,name,title,description,skill_type,scope,status,owner_gid,team_gid,is_system,content,icon,tags,sort_order) VALUES (%s,%s,%s,%s,%s,'global','active','__system__',%s,TRUE,%s,%s,%s,%s)", (gid, skill["name"], skill["title"], skill.get("description", ""), skill.get("skill_type", "prompt"), team, json.dumps(content, ensure_ascii=False), skill.get("icon", ""), json.dumps(tags, ensure_ascii=False), skill.get("sort_order", 0)))
                        seeded.append({"name": skill["name"], "action": "created", "gid": gid})
                return {"success": True, "seeded": seeded}
        raise ValueError("unsupported skill write operation")
