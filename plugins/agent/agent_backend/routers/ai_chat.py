"""
backend/routers/ai_chat.py
───────────────────────────
AI 对话云端 API

POST /api/ai/chat/stream    — SSE 流式对话（主路径）
POST /api/ai/chat           — 同步对话（降级路径）
POST /api/ai/confirm        — 确认写操作
GET  /api/ai/sessions       — 列出会话
DELETE /api/ai/sessions/{gid} — 删除会话
GET  /api/ai/tools          — 工具列表
GET  /api/ai/admin-config   — 全局配置（超管可写，所有登录用户可读）
POST /api/ai/admin-config   — 保存全局配置（超管）
POST /api/ai/test-connection — 测试 AI 连接
POST /api/ai/abort          — 中断流式对话
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.platform_sdk.auth import get_current_user, require_role
from ..ai_assistant.session_store import _store
from ..ai_assistant import tool_executor as _te
from ..ai_assistant import system_prompt as _sp
from . import agent_runtime_proxy_next as _pi_proxy
from ..ai_assistant.tool_registry import (
    catalog_tools_openai,
)
from ..api.compatibility import invoke_agent_capability
from ..application.interaction_state import consume_abort
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.auth import get_authenticated_principal
from backend.capability_v2.web_compatibility import build_trusted_web_envelope, invoke_trusted_web_compatibility

router = APIRouter(prefix="/api/ai", tags=["ai_chat"])
_log = __import__('logging').getLogger(__name__)

# ── 流式中断标志（session_gid → True）────────────────────────────────────────
_DEFAULT_MODEL    = "anthropic/claude-sonnet-4-6"
_MAX_ITER         = 30
_TOKEN_BUDGET     = 200_000
_WRAP_UP_ITER     = 8
_TOOL_MAX_CALLS   = 3


async def _invoke_interaction_chat(request, user, principal, gateway, payload):
    request_id = request.headers.get("X-Request-ID") or f"agent_interaction_chat_{uuid.uuid4().hex}"
    result = await invoke_trusted_web_compatibility(gateway, build_trusted_web_envelope(
        gateway, capability_id="agent.interaction.chat.change.apply", payload=_normalize_interaction_payload(payload),
        current_user=user, principal=principal, consumer_id="ai00.web.agent", request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
        major_version=2,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"invalid_input": 400, "permission_denied": 403, "resource_not_found": 404}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return await _project_interaction_response(
        payload, result.data.get("data", result.data), gateway=gateway,
    )


async def _invoke_confirmed_catalog_tool(request, user, principal, gateway, body):
    session_gid = str(body.get("session_gid") or body.get("session_id") or "")
    request_id = request.headers.get("X-Request-ID") or f"agent_confirm_{uuid.uuid4().hex}"
    envelope = build_trusted_web_envelope(
        gateway, capability_id="agent.catalog_tool.confirm.apply", major_version=1,
        payload={
            "confirm_token": str(body.get("confirm_token") or ""),
            "tool_name": str(body.get("tool_name") or ""),
            "session_gid": session_gid,
            "tool_use_id": str(body.get("tool_use_id") or ""),
        }, current_user=user, principal=principal,
        consumer_id="ai00.web.agent", request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
    )
    result = await invoke_trusted_web_compatibility(gateway, envelope)
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(
            status_code={"invalid_input": 400, "permission_denied": 403, "resource_not_found": 404}.get(code, 422),
            detail=result.error.model_dump(mode="json") if result.error else None,
        )
    return await _invoke_interaction_chat(
        request, user, principal, gateway,
        {"operation": "chat_stream" if body.get("stream", True) else "chat_sync", "body": {"message": "", "session_gid": session_gid}},
    )
_TOOL_RESULT_MAX  = 12_000

_CHJ_GATEWAY_HOST     = "api-hub.inner.chj.cloud"
_CHJ_BASE_COMPLETIONS = "http://api-hub.inner.chj.cloud/llm-gateway/v1/chat/completions"

# ── Config helpers ────────────────────────────────────────────────────────────

def _get_ai_config(user_gid: str | None = None) -> dict:
    """Model credentials are deployment secrets, never business-database records."""
    key = os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
    if key:
        return {
            "model": os.getenv("AI_MODEL", _DEFAULT_MODEL),
            "api_key": key,
            "api_base": os.getenv("AI_API_BASE", ""),
            "source": "env",
        }
    return {"model": "", "api_key": "", "api_base": "", "source": "none"}


def _get_admin_config_raw() -> dict:
    return _get_ai_config()

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "••••" + key[-4:]
    return "•" * len(key)


def _sanitize_error(e: Exception) -> str:
    """截断异常信息，防止 httpx 把含 Authorization header 的 request dump 出来。"""
    msg = str(e)
    if len(msg) > 300:
        msg = msg[:300] + "…[truncated]"
    return msg


def _is_chj(model: str, api_base: str = "") -> bool:
    return (
        (model or "").lower().startswith("kivy-")
        or _CHJ_GATEWAY_HOST in (api_base or "").lower()
    )


def _normalize_model(model: str, api_base: str) -> str:
    if _is_chj(model, api_base):
        return model
    if "/" not in model:
        return f"openai/{model}"
    return model


def _serialize_result(result: dict) -> str:
    s = json.dumps(result, ensure_ascii=False)
    if len(s) <= _TOOL_RESULT_MAX:
        return s
    if isinstance(result, dict) and "text" in result:
        slim = {"text": result["text"], "_truncated": True}
        s2 = json.dumps(slim, ensure_ascii=False)
        if len(s2) <= _TOOL_RESULT_MAX:
            return s2
    suffix = '…（结果过长已截断）"}'
    return s[:_TOOL_RESULT_MAX - len(suffix)] + suffix


def _build_messages(turns: list[dict]) -> list[dict]:
    messages = []
    for t in turns:
        role    = t["role"]
        content = t["content"]
        tcs     = t.get("tool_calls", [])

        if role == "summary":
            messages.append({"role": "user", "content": f"[早期对话摘要]\n{content}"})
        elif role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
        elif role == "tool_result" and tcs:
            ast_tcs, tool_msgs = [], []
            for tc in tcs:
                tid = tc.get("tool_use_id", tc.get("name", ""))
                ast_tcs.append({
                    "id": tid, "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("input", {}), ensure_ascii=False),
                    },
                })
                tool_msgs.append({
                    "role": "tool", "tool_call_id": tid,
                    "content": _serialize_result(tc.get("result", {})),
                })
            messages.append({"role": "assistant", "content": None, "tool_calls": ast_tcs})
            messages.extend(tool_msgs)
    return messages


def _chj_completion(messages, model_id, api_key, tools=None, max_tokens=4096):
    import httpx, json as _json
    url = f"{_CHJ_BASE_COMPLETIONS}/{model_id}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-CHJ-GWToken": api_key,
        "BCS-APIHub-RequestId": str(uuid.uuid4()),
    }
    body: dict = {"model": model_id, "messages": messages, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"CHJ gateway HTTP {exc.response.status_code}") from None
    except Exception as exc:
        raise RuntimeError(f"CHJ gateway error: {_sanitize_error(exc)}") from None
    # 容错解码：UTF-8 → GBK → Latin-1
    raw = resp.content
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return _json.loads(raw.decode(enc))
        except Exception:
            continue
    raise RuntimeError("CHJ gateway: 响应无法解码")


def _http_completion_tolerant(
    url: str, api_key: str, model: str,
    messages: list, tools: list | None = None,
    max_tokens: int = 4096, extra_headers: dict | None = None,
) -> dict:
    """直接 httpx 请求，兼容 GBK/Latin-1 响应。用于 litellm 编码失败时的降级。"""
    import httpx, json as _json
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        **(extra_headers or {}),
    }
    body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    resp = httpx.post(url, headers=headers, json=body, timeout=120)
    raw = resp.content
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            data = _json.loads(raw.decode(enc))
            break
        except Exception:
            continue
    else:
        data = _json.loads(raw.decode("latin-1", errors="replace"))
    if not resp.is_success:
        err = data.get("error") or (data.get("errors") or [{}])[0]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise RuntimeError(f"HTTP {resp.status_code}: {msg or raw[:200].decode('latin-1','replace')}")
    return data


# ── SSE 流式对话 ──────────────────────────────────────────────────────────────

def _chat_stream_gen(
    message: str,
    session_gid: str | None,
    user_gid: str,
    auth_mode: str,
    auth_token: str,
    context: dict | None,
    canvas_context: dict | None = None,
    catalog_runtime: dict | None = None,
):
    """生成 SSE 事件的生成器函数。"""
    ai_cfg = _get_ai_config(user_gid)
    if not ai_cfg["api_key"]:
        yield f'data: {json.dumps({"type":"error","message":"未配置 AI API Key，请在「AI 设置」中配置"})}\n\n'
        return

    is_new = not session_gid
    if is_new:
        session_gid = _store.create_session(user_gid=user_gid)

    _store.add_turn(session_gid, "user", message)
    turns    = _store.get_turns(session_gid)
    messages = _build_messages(turns)
    system   = _sp.build(
        user_name=user_gid or "工程师",
        user_role="member",
        auth_mode=auth_mode,
        context=context,
        owner_gid=user_gid,
    )

    try:
        import litellm
        litellm.set_verbose = False
    except ImportError:
        yield f'data: {json.dumps({"type":"error","message":"litellm 未安装，请执行 pip install litellm"})}\n\n'
        return

    model    = _normalize_model(ai_cfg["model"], ai_cfg.get("api_base", ""))
    api_key  = ai_cfg["api_key"]
    api_base = ai_cfg.get("api_base") or None
    is_chj   = _is_chj(model, api_base or "")

    # ── Phase 0 任务分类 + Orchestrator 检查 ─────────────────────────────────
    from ..ai_assistant.orchestrator import should_orchestrate, OrchestratorRunner
    from ..ai_assistant.task_classifier import classify_task

    orch_cfg = {
        "model":   model,
        "api_key": api_key,
        **({"api_base": api_base} if api_base else {}),
    }

    task_cls = classify_task(message, ai_cfg=orch_cfg)

    # needs_decompose → Orchestrator（优先用 task_cls.sub_tasks 跳过 Phase 1 规划）
    # 降级：task_cls 失败 → 旧关键词启发式
    should_orch = (
        (task_cls is not None and task_cls["complexity"] == "needs_decompose")
        or (task_cls is None and should_orchestrate(message))
    )

    if should_orch:
        orch_result = OrchestratorRunner().run(
            session_gid=session_gid,
            user_msg=message,
            ai_cfg=orch_cfg,
            auth_mode=auth_mode,
            auth_token=auth_token,
            user_gid=user_gid,
            system=system,
            task_cls=task_cls,
        )
        if not orch_result.get("_fallback"):
            answer = orch_result.get("answer", "")
            agents = orch_result.get("agents", [])
            if answer:
                yield f'data: {json.dumps({"type":"token","content":answer})}\n\n'
            if agents:
                yield f'data: {json.dumps({"type":"orchestrator_result","agents":agents})}\n\n'
            yield f'data: {json.dumps({"type":"done","session_id":session_gid,"orchestrator":True})}\n\n'
            return
        # fallback → 继续走普通单 Agent 路径

    # multi_step：在 system prompt 末尾追加步骤提示
    if task_cls and task_cls["complexity"] == "multi_step":
        system = system + "\n\n【任务规划提示】请按步骤逐一使用工具，每步完成后输出中间结论，最后综合输出最终答案。"

    if not catalog_runtime:
        raise CapabilityBusinessError(
            "catalog_release_unavailable", "Pinned Agent Catalog runtime is unavailable",
            retryable=True,
        )
    catalog_registry = catalog_runtime["registry"]
    identity_factory = catalog_runtime.get("identity_factory")
    def identity_for(tool, inputs):
        identity = (
            identity_factory(session_gid, tool, inputs)
            if identity_factory else catalog_runtime.get("identity")
        )
        if identity is None:
            raise CapabilityBusinessError(
                "delegation_expired", "Agent run identity is unavailable",
            )
        return identity
    all_tools = catalog_tools_openai(catalog_registry)
    msgs      = [{"role": "system", "content": system}] + list(messages)

    answer               = ""
    seen_calls:      set = set()
    tool_call_counts: dict = {}
    wrap_up_injected = False
    _total_tokens    = 0
    _iter_count      = 0

    for _iter in range(_MAX_ITER):
        _iter_count = _iter + 1
        # 中断检查
        if consume_abort(session_gid):
            yield f'data: {json.dumps({"type":"done","session_id":session_gid,"total_tokens":_total_tokens,"model":model,"iter_count":_iter_count})}\n\n'
            return

        if _iter >= _WRAP_UP_ITER and not wrap_up_injected:
            msgs.append({
                "role": "user",
                "content": "【系统提示】请综合已获取的信息直接给出最终答案，不要再调用更多工具。",
            })
            wrap_up_injected = True

        if is_chj:
            try:
                resp_data = _chj_completion(
                    messages=msgs, model_id=model, api_key=api_key,
                    tools=all_tools, max_tokens=4096,
                )
            except Exception as e:
                yield f'data: {json.dumps({"type":"error","message":_sanitize_error(e)})}\n\n'
                return
            _total_tokens += resp_data.get("usage", {}).get("total_tokens", 0)
            choice = resp_data["choices"][0]
            answer = choice["message"].get("content") or ""
            raw_tcs = choice["message"].get("tool_calls") or []
            if answer:
                yield f'data: {json.dumps({"type":"token","content":answer})}\n\n'

            class _FakeFn:
                def __init__(self, n, a): self.name = n; self.arguments = a
            class _FakeTC:
                def __init__(self, i, f): self.id = i; self.function = f

            tool_calls = [
                _FakeTC(tc.get("id", ""), _FakeFn(
                    tc.get("function", {}).get("name", ""),
                    tc.get("function", {}).get("arguments", "{}"),
                ))
                for tc in raw_tcs
            ]
        else:
            call_kwargs: dict = {
                "model": model, "messages": msgs,
                "tools": all_tools, "max_tokens": 4096,
                "api_key": api_key, "stream": True,
                "stream_options": {"include_usage": True},
            }
            if api_base:
                call_kwargs["api_base"] = api_base

            try:
                stream_resp = litellm.completion(**call_kwargs)
            except Exception as e:
                yield f'data: {json.dumps({"type":"error","message":_sanitize_error(e)})}\n\n'
                return

            answer = ""
            partial_tcs: dict[int, dict] = {}

            try:
              for chunk in stream_resp:
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    answer += delta.content
                    yield f'data: {json.dumps({"type":"token","content":delta.content})}\n\n'
                if getattr(delta, "tool_calls", None):
                    for tc_d in delta.tool_calls:
                        idx = getattr(tc_d, "index", 0) or 0
                        if idx not in partial_tcs:
                            partial_tcs[idx] = {"id": getattr(tc_d, "id", "") or "", "name": "", "arguments": ""}
                        fn = getattr(tc_d, "function", None)
                        if fn:
                            if getattr(fn, "name", None):
                                partial_tcs[idx]["name"] += fn.name
                            if getattr(fn, "arguments", None):
                                partial_tcs[idx]["arguments"] += fn.arguments
                # 最后一个 chunk 可能携带 usage（stream_options include_usage）
                if getattr(chunk, "usage", None) and getattr(chunk.usage, "total_tokens", None):
                    _total_tokens += chunk.usage.total_tokens
            except UnicodeDecodeError:
                # 流式响应含非 UTF-8 字节，降级为同步 httpx 请求（容错解码）
                try:
                    if is_chj:
                        fallback_url = f"{_CHJ_BASE_COMPLETIONS}/{model}"
                        extra_h = {"X-CHJ-GWToken": api_key, "BCS-APIHub-RequestId": str(uuid.uuid4())}
                    else:
                        fallback_url = f"{(api_base or 'https://api.openai.com').rstrip('/')}/v1/chat/completions"
                        extra_h = {}
                    resp_data = _http_completion_tolerant(
                        url=fallback_url, api_key=api_key, model=model,
                        messages=msgs, tools=all_tools or None, max_tokens=4096,
                        extra_headers=extra_h,
                    )
                    answer = resp_data["choices"][0]["message"].get("content") or answer
                    if answer:
                        yield f'data: {json.dumps({"type":"token","content":answer})}\n\n'
                except Exception as fallback_e:
                    yield f'data: {json.dumps({"type":"error","message":f"编码降级失败: {_sanitize_error(fallback_e)}"})}\n\n'
                    return
            except Exception as e:
                yield f'data: {json.dumps({"type":"error","message":_sanitize_error(e)})}\n\n'
                return

            class _FakeFn2:
                def __init__(self, n, a): self.name = n; self.arguments = a
            class _FakeTC2:
                def __init__(self, i, f): self.id = i; self.function = f

            tool_calls = [
                _FakeTC2(v["id"], _FakeFn2(v["name"], v["arguments"]))
                for v in partial_tcs.values()
                if v["name"]
            ]

        # ── 无工具调用：完成 ──────────────────────────────────────────────────
        if not tool_calls:
            _store.add_turn(session_gid, "assistant", answer)
            if is_new:
                _store.update_title(session_gid, message[:30])
            else:
                _store.touch(session_gid)
            yield f'data: {json.dumps({"type":"done","session_id":session_gid,"total_tokens":_total_tokens,"model":model,"iter_count":_iter_count})}\n\n'
            return

        # ── 写工具 → 暂停等待确认 ────────────────────────────────────────────
        write_calls = [
            tc for tc in tool_calls
            if catalog_registry.resolve(tc.function.name).confirmation_policy != "none"
        ]
        if write_calls:
            wtc     = write_calls[0]
            inputs  = json.loads(wtc.function.arguments or "{}")
            tool = catalog_registry.resolve(wtc.function.name)
            token = _te.issue_confirm_token(
                tool.name, inputs, session_gid, user_gid,
                catalog_release=catalog_runtime["catalog_release"],
                capability_id=tool.capability_id, major_version=tool.major_version,
                idempotency_key=f"{catalog_runtime['correlation'].request_id}:{wtc.id}",
                agent_identity=identity_for(tool, inputs),
            )
            preview = _te.build_preview(wtc.function.name, inputs)
            intent  = answer or f"即将执行：{preview}"
            _store.add_turn(session_gid, "assistant", intent)
            yield f'data: {json.dumps({"type":"confirm_required","tool_name":wtc.function.name,"tool_use_id":wtc.id,"confirm_token":token,"preview":preview,"session_id":session_gid})}\n\n'
            return

        # ── 只读/免确认写工具：并行执行 ──────────────────────────────────────
        from concurrent.futures import ThreadPoolExecutor as _TPE

        to_exec: list         = []
        preflight_err: dict   = {}

        for tc in tool_calls:
            name     = tc.function.name
            args_str = tc.function.arguments or "{}"
            inputs   = json.loads(args_str)
            tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
            if tool_call_counts[name] > _TOOL_MAX_CALLS:
                preflight_err[tc.id] = {"error": f"工具 {name} 超过单次调用上限"}
            else:
                call_key = f"{name}:{args_str}"
                if call_key in seen_calls:
                    preflight_err[tc.id] = {"error": f"检测到重复调用 {name}，已跳过"}
                else:
                    to_exec.append((tc, name, inputs, call_key))
                    yield f'data: {json.dumps({"type":"tool_start","name":name})}\n\n'

        exec_results: dict = {}
        if to_exec:
            def _exec_one(item):
                _tc, _name, _inputs, _call_key = item
                _result = asyncio.run(_te.execute_catalog_tool(
                    catalog_registry, _name, _inputs,
                    identity=identity_for(catalog_registry.resolve(_name), _inputs),
                    correlation=catalog_runtime["correlation"],
                    idempotency_key=f"{catalog_runtime['correlation'].request_id}:{_tc.id}",
                ))
                _res = (
                    _result.data if _result.ok else
                    {"error": _result.error.message, "code": _result.error.code}
                )
                return _tc.id, _name, _call_key, _res

            with _TPE(max_workers=min(len(to_exec), 5)) as pool:
                for fut in [pool.submit(_exec_one, item) for item in to_exec]:
                    tc_id, _name, call_key, res = fut.result()
                    exec_results[tc_id] = (_name, call_key, res)
                    ok = not (isinstance(res, dict) and res.get("error"))
                    _UI_TOOLS = {"generate_canvas", "bop_to_canvas", "create_discussion_topic", "open_in_container", "run_skill_canvas"}
                    evt: dict = {"type": "tool_end", "name": _name, "ok": ok}
                    if isinstance(res, dict) and isinstance(res.get("evidence"), list):
                        evt["evidence"] = res["evidence"][:20]
                    if _name in _UI_TOOLS and isinstance(res, dict):
                        evt["result"] = res
                    yield f'data: {json.dumps(evt)}\n\n'
                    if ok:
                        seen_calls.add(call_key)

        tool_result_msgs, batch_records = [], []
        for tc in tool_calls:
            name     = tc.function.name
            args_str = tc.function.arguments or "{}"
            inputs   = json.loads(args_str)
            if tc.id in preflight_err:
                exec_result = preflight_err[tc.id]
            elif tc.id in exec_results:
                _, _, exec_result = exec_results[tc.id]
            else:
                exec_result = {"error": "执行失败"}
            record = {"name": name, "input": inputs, "result": exec_result, "tool_use_id": tc.id}
            batch_records.append(record)
            tool_result_msgs.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": _serialize_result(exec_result),
            })

        _store.add_turn(session_gid, "tool_result", "", tool_calls=batch_records)
        msgs.append({
            "role": "assistant", "content": answer or None,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })
        msgs.extend(tool_result_msgs)

    _store.add_turn(session_gid, "assistant", answer)
    yield f'data: {json.dumps({"type":"done","session_id":session_gid,"total_tokens":_total_tokens,"model":model,"iter_count":_iter_count})}\n\n'


# ── Pi Runtime compatibility switch ──────────────────────────────────────────

def _pi_call(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent Runtime unavailable: {str(exc)[:240]}") from exc


def _require_legacy_session_owner(session_gid: str | None, user_gid: str) -> None:
    if not session_gid:
        return
    _store.require_owned_session(session_gid, user_gid)

# ── FastAPI 路由 ──────────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(
    body: dict, request: Request,
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    return await _invoke_interaction_chat(request, _user, principal, gateway, {"operation": "chat_stream", "body": body, "ai00_token": x_ai00_token})


def _legacy_chat_stream(
    body: dict,
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    """SSE 流式对话（主路径）；可灰度切换到 Pi Runtime。"""
    session_gid = body.get("session_id") or body.get("session_gid") or None
    user_gid = _user.get("gid", "")
    _require_legacy_session_owner(session_gid, user_gid)
    if _pi_proxy.enabled():
        return StreamingResponse(
            _pi_proxy.stream_chat(body, x_ai00_token), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    message     = body.get("message", "")
    auth_mode   = "feishu"
    auth_token  = body.get("auth_token", "")
    context_raw = body.get("context") or {}
    if isinstance(context_raw, str):
        try:
            import json as _j; context_raw = _j.loads(context_raw)
        except Exception:
            context_raw = {}
    canvas_ctx = body.get("canvas_context") or {}
    if isinstance(canvas_ctx, str):
        try:
            import json as _j; canvas_ctx = _j.loads(canvas_ctx)
        except Exception:
            canvas_ctx = {}

    return StreamingResponse(
        _chat_stream_gen(
            message=message,
            session_gid=session_gid,
            user_gid=user_gid,
            auth_mode=auth_mode,
            auth_token=auth_token,
            context=context_raw or None,
            canvas_context=canvas_ctx or None,
            catalog_runtime=_user.get("_catalog_runtime"),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _chat_sync_tolerant(body: dict, user: dict) -> dict:
    """UnicodeDecodeError 降级：完全绕开 litellm，用 httpx 容错解码直接发请求。"""
    try:
        cfg = _get_ai_config()
    except Exception as e:
        return {"error": f"读取 AI 配置失败: {_sanitize_error(e)}"}

    message = body.get("message", "")
    session_gid = body.get("session_id") or body.get("session_gid") or None
    user_gid = user.get("gid", "")

    # Reuse the private Agent session repository; no fallback database query.
    history = []
    if session_gid:
        try:
            history = [
                {"role": turn["role"], "content": turn["content"]}
                for turn in _store.get_turns(session_gid)
                if turn["role"] in ("user", "assistant")
            ][-20:]
        except Exception:
            pass
    msgs = history + [{"role": "user", "content": message}]
    model = _normalize_model(cfg["model"], cfg.get("api_base", ""))

    try:
        if _is_chj(cfg["model"], cfg.get("api_base") or ""):
            resp_data = _chj_completion(
                messages=msgs, model_id=model,
                api_key=cfg["api_key"], max_tokens=4096,
            )
        else:
            api_base = (cfg.get("api_base") or "https://api.openai.com").rstrip("/")
            url = f"{api_base}/v1/chat/completions"
            resp_data = _http_completion_tolerant(
                url=url, api_key=cfg["api_key"], model=model,
                messages=msgs, max_tokens=4096,
            )
        answer = resp_data["choices"][0]["message"].get("content", "")
        total_tokens = resp_data.get("usage", {}).get("total_tokens", 0)
        return {
            "answer": answer,
            "session_id": session_gid or "",
            "tool_calls": [],
            "total_tokens": total_tokens,
            "model": cfg["model"],
        }
    except Exception as e:
        return {"error": f"容错请求也失败: {_sanitize_error(e)}"}


@router.post("/chat")
async def chat_sync(
    body: dict, request: Request,
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    return await _invoke_interaction_chat(request, _user, principal, gateway, {"operation": "chat_sync", "body": body, "ai00_token": x_ai00_token})


def _legacy_chat_sync(
    body: dict,
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    """同步对话（降级路径，收集所有 SSE 事件后返回）。"""
    _require_legacy_session_owner(
        body.get("session_id") or body.get("session_gid"), _user.get("gid", ""),
    )
    if _pi_proxy.enabled():
        return _pi_proxy.sync_chat(body, x_ai00_token)
    try:
        chunks = list(_chat_stream_gen(
            message=body.get("message", ""),
            session_gid=body.get("session_id") or body.get("session_gid") or None,
            user_gid=_user.get("gid", ""),
            auth_mode="feishu",
            auth_token=body.get("auth_token", ""),
            context=body.get("context") or None,
            catalog_runtime=_user.get("_catalog_runtime"),
        ))
    except UnicodeDecodeError:
        # streaming 整体失败，直接用容错同步请求
        return _chat_sync_tolerant(body, _user)
    except Exception as e:
        return {"error": _sanitize_error(e)}

    answer = ""
    session_id = ""
    pending_confirm = None
    tool_calls_list = []
    total_tokens = 0
    model_used = ""
    iter_count = 0

    for chunk in chunks:
        if not chunk.startswith("data: "):
            continue
        try:
            evt = json.loads(chunk[6:])
        except Exception:
            continue
        t = evt.get("type")
        if t == "token":
            answer += evt.get("content", "")
        elif t == "done":
            session_id   = evt.get("session_id", "")
            total_tokens = evt.get("total_tokens", 0)
            model_used   = evt.get("model", "")
            iter_count   = evt.get("iter_count", 0)
        elif t == "confirm_required":
            pending_confirm = evt
        elif t == "tool_end":
            tool_calls_list.append({"name": evt.get("name"), "ok": evt.get("ok")})
        elif t == "error":
            return {"error": evt.get("message"), "session_id": session_id}

    return {
        "answer":          answer,
        "session_id":      session_id,
        "tool_calls":      tool_calls_list,
        "pending_confirm": pending_confirm,
        "total_tokens":    total_tokens,
        "model":           model_used,
        "iter_count":      iter_count,
    }


@router.post("/confirm")
async def confirm_tool(
    body: dict, request: Request,
    _user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    return await _invoke_confirmed_catalog_tool(request, _user, principal, gateway, {**body, "stream": True})


def _legacy_confirm_tool(
    body: dict,
    _user: dict = Depends(get_current_user),
):
    """确认写操作 → 继续执行对话。返回 SSE 流。"""
    if _pi_proxy.enabled():
        raise HTTPException(status_code=409, detail="Pi Runtime 写能力确认尚未开放")
    session_gid   = body.get("session_gid") or body.get("session_id", "")
    _require_legacy_session_owner(session_gid, _user.get("gid", ""))
    confirm_token = body.get("confirm_token", "")
    tool_name     = body.get("tool_name", "")
    tool_use_id   = body.get("tool_use_id", "")
    user_gid      = _user.get("gid", "")
    auth_token    = body.get("auth_token", "")

    valid, pending = _te.consume_confirm_token(confirm_token, tool_name, session_gid, user_gid)
    if not valid:
        return {"error": "确认令牌无效或已过期，请重新操作"}

    inputs = pending["inputs"]

    def _confirm_gen():
        raise CapabilityBusinessError(
            "provider_unavailable", "legacy Agent confirmation execution is retired",
        )
        tc_record = {"name": tool_name, "input": inputs, "result": write_result,
                     "tool_use_id": tool_use_id, "confirmed": True}
        _store.add_turn(session_gid, "tool_result", "", tool_calls=[tc_record])

        turns    = _store.get_turns(session_gid)
        messages = _build_messages(turns)
        system   = _sp.build(user_name=user_gid or "工程师", auth_mode="feishu", owner_gid=user_gid)

        yield from _chat_stream_gen(
            message="",  # 空消息：继续上轮对话
            session_gid=session_gid,
            user_gid=user_gid,
            auth_mode="feishu",
            auth_token=auth_token,
            context=None,
        )

    # 简化：直接执行并返回结果（不再走 stream）
    raise CapabilityBusinessError(
        "provider_unavailable", "legacy Agent confirmation execution is retired",
    )
    tc_record = {"name": tool_name, "input": inputs, "result": write_result,
                 "tool_use_id": tool_use_id, "confirmed": True}
    _store.add_turn(session_gid, "tool_result", "", tool_calls=[tc_record])

    return StreamingResponse(
        _chat_stream_gen(
            message="",
            session_gid=session_gid,
            user_gid=user_gid,
            auth_mode="feishu",
            auth_token=auth_token,
            context=None,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/confirm/sync")
async def confirm_tool_sync(
    body: dict, request: Request,
    _user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway),
):
    return await _invoke_confirmed_catalog_tool(request, _user, principal, gateway, {**body, "stream": False})


def _legacy_confirm_tool_sync(
    body: dict,
    _user: dict = Depends(get_current_user),
):
    """同步版确认写操作：执行工具后继续对话，收集 SSE 后返回 JSON。"""
    if _pi_proxy.enabled():
        raise HTTPException(status_code=409, detail="Pi Runtime 写能力确认尚未开放")
    session_gid   = body.get("session_gid") or body.get("session_id", "")
    _require_legacy_session_owner(session_gid, _user.get("gid", ""))
    confirm_token = body.get("confirm_token", "")
    tool_name     = body.get("tool_name", "")
    tool_use_id   = body.get("tool_use_id", "")
    user_gid      = _user.get("gid", "")
    auth_token    = body.get("auth_token", "")

    valid, pending = _te.consume_confirm_token(confirm_token, tool_name, session_gid, user_gid)
    if not valid:
        return {"error": "确认令牌无效或已过期，请重新操作"}

    inputs = pending["inputs"]
    raise CapabilityBusinessError(
        "provider_unavailable", "legacy Agent confirmation execution is retired",
    )
    tc_record = {"name": tool_name, "input": inputs, "result": write_result,
                 "tool_use_id": tool_use_id, "confirmed": True}
    _store.add_turn(session_gid, "tool_result", "", tool_calls=[tc_record])

    chunks = list(_chat_stream_gen(
        message="",
        session_gid=session_gid,
        user_gid=user_gid,
        auth_mode="feishu",
        auth_token=auth_token,
        context=None,
    ))

    answer = ""
    result_session_id = session_gid
    pending_confirm = None
    total_tokens = 0
    model_used = ""
    iter_count = 0
    tool_calls_list = [{
        "name": tool_name,
        "ok": not (isinstance(write_result, dict) and write_result.get("error")),
        "result": write_result,
        "input": inputs,
        "confirmed": True,
    }]

    for chunk in chunks:
        if not chunk.startswith("data: "):
            continue
        try:
            evt = json.loads(chunk[6:])
        except Exception:
            continue
        t = evt.get("type")
        if t == "token":
            answer += evt.get("content", "")
        elif t == "done":
            result_session_id = evt.get("session_id", session_gid)
            total_tokens      = evt.get("total_tokens", 0)
            model_used        = evt.get("model", "")
            iter_count        = evt.get("iter_count", 0)
        elif t == "confirm_required":
            pending_confirm = evt
        elif t == "tool_end":
            tool_calls_list.append({"name": evt.get("name"), "ok": evt.get("ok")})
        elif t == "error":
            return {"error": evt.get("message"), "session_id": result_session_id}

    return {
        "answer":          answer,
        "session_id":      result_session_id,
        "tool_calls":      tool_calls_list,
        "pending_confirm": pending_confirm,
        "total_tokens":    total_tokens,
        "model":           model_used,
        "iter_count":      iter_count,
    }


@router.post("/abort")
async def abort_stream(
    body: dict,
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    if _pi_proxy.enabled():
        return {"ok": True}
    session_gid = body.get("session_gid") or body.get("session_id", "")
    if session_gid:
        return await invoke_agent_capability("agent.interaction.cancel", {"session_gid": session_gid}, _user)
    return {"ok": True}


# ── 会话管理 ──────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    data = await invoke_agent_capability("agent.session.read", {"operation": "list"}, _user)
    payload = data.get("data", data) if isinstance(data, dict) else {}
    return {"sessions": [s for s in payload.get("sessions", []) if "_sub_" not in s.get("gid", "")]}


@router.delete("/sessions/{gid}")
async def delete_session(
    gid: str,
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    data = await invoke_agent_capability(
        "agent.session.change.apply", {"operation": "delete", "session_gid": gid}, _user
    )
    return data.get("data", data) if isinstance(data, dict) else data


@router.get("/sessions/{gid}")
async def get_session(
    gid: str,
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    """返回会话的所有轮次（前端恢复历史对话用）。"""
    data = await invoke_agent_capability(
        "agent.session.read", {"operation": "get", "session_gid": gid}, _user
    )
    return data.get("data", data) if isinstance(data, dict) else data


@router.post("/sessions/new")
async def new_session(
    body: dict = {},
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    data = await invoke_agent_capability("agent.session.change.apply", {"operation": "create"}, _user)
    return data.get("data", data) if isinstance(data, dict) else data


# ── 工具列表 ──────────────────────────────────────────────────────────────────

@router.get("/tools")
async def list_tools(
    _user: dict = Depends(get_current_user),
    x_ai00_token: str = Header(alias="X-AI00-Token"),
):
    if _pi_proxy.enabled():
        return _pi_call(_pi_proxy.list_tools, x_ai00_token)
    return await invoke_agent_capability("agent.tool_catalog.read", {"operation": "list"}, _user)


# ── AI 配置 ───────────────────────────────────────────────────────────────────

@router.get("/admin-config")
async def get_admin_config(
    _user: dict = Depends(get_current_user),
):
    """全局 AI 配置：由 Agent Runtime Capability 提供只读元数据。"""
    return await invoke_agent_capability("agent.runtime.config.read", {}, _user)


@router.post("/admin-config", status_code=410)
def save_admin_config(
    body: dict,
    _user: dict = Depends(require_role("super_admin")),
):
    raise HTTPException(
        status_code=410,
        detail="模型密钥由 Agent Runtime 部署 Secret 管理；旧配置写入入口已退役",
    )

@router.post("/test-connection")
def test_connection(
    body: dict,
    _user: dict = Depends(get_current_user),
):
    if _pi_proxy.enabled():
        return _pi_call(_pi_proxy.health)
    try:
        cfg = _get_ai_config()
    except Exception as e:
        return {"success": False, "error": f"读取 AI 配置失败: {_sanitize_error(e)}"}

    if not cfg["api_key"]:
        return {"success": False, "error": "未配置 API Key"}

    try:
        import litellm
        litellm.set_verbose = False
        model_id = _normalize_model(cfg["model"], cfg.get("api_base", ""))
        if _is_chj(cfg["model"], cfg.get("api_base") or ""):
            data = _chj_completion(
                messages=[{"role": "user", "content": "reply: ok"}],
                model_id=model_id, api_key=cfg["api_key"], max_tokens=16,
            )
            reply = data["choices"][0]["message"].get("content", "")[:80]
        else:
            call_kwargs: dict = {
                "model": model_id,
                "messages": [{"role": "user", "content": "reply: ok"}],
                "max_tokens": 16,
                "api_key": cfg["api_key"],
            }
            if cfg.get("api_base"):
                call_kwargs["api_base"] = cfg["api_base"]
            resp  = litellm.completion(**call_kwargs)
            reply = (resp.choices[0].message.content or "")[:80]
        return {"success": True, "reply": reply, "model": cfg["model"]}
    except UnicodeDecodeError:
        # litellm 内部 UTF-8 解码失败（服务返回 GBK/Latin-1 内容）
        # 降级：用 httpx 直接请求，强制容错解码
        return _test_connection_raw(cfg)
    except Exception as e:
        return {"success": False, "error": _sanitize_error(e)}


def _test_connection_raw(cfg: dict) -> dict:
    """litellm 编码失败时的降级方案：直接用 httpx，兼容 GBK/Latin-1 响应。"""
    import httpx, json as _json

    # CHJ 网关有专用鉴权，直接走 _chj_completion
    if _is_chj(cfg.get("model", ""), cfg.get("api_base") or ""):
        try:
            model_id = _normalize_model(cfg["model"], cfg.get("api_base", ""))
            data = _chj_completion(
                messages=[{"role": "user", "content": "reply: ok"}],
                model_id=model_id, api_key=cfg["api_key"], max_tokens=16,
            )
            reply = data["choices"][0]["message"].get("content", "")[:80]
            return {"success": True, "reply": reply, "model": cfg["model"]}
        except Exception as e:
            return {"success": False, "error": _sanitize_error(e)}

    api_base = (cfg.get("api_base") or "").rstrip("/")
    if not api_base:
        model = (cfg.get("model") or "").lower()
        api_base = "https://api.anthropic.com" if "claude" in model else "https://api.openai.com"
    url = f"{api_base}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.get("model", ""),
        "messages": [{"role": "user", "content": "reply: ok"}],
        "max_tokens": 16,
    }
    try:
        with httpx.Client(timeout=20) as client:
            r = client.post(url, json=payload, headers=headers)
        # 容错解码：UTF-8 → GBK → Latin-1
        raw = r.content
        text = ""
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                text = raw.decode(enc); break
            except Exception:
                continue
        else:
            text = raw.decode("latin-1", errors="replace")
        try:
            data = _json.loads(text)
        except Exception:
            return {"success": False, "error": f"HTTP {r.status_code}: {text[:200]}"}
        if r.status_code == 200 and data.get("choices"):
            reply = (data["choices"][0].get("message", {}).get("content") or "")[:80]
            return {"success": True, "reply": reply, "model": cfg.get("model", "")}
        # 提取错误信息（兼容 {"error":...} 和 {"errors":[...]} 两种格式）
        err = data.get("error") or (data.get("errors") or [{}])[0]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return {"success": False, "error": f"HTTP {r.status_code}: {msg or text[:200]}"}
    except Exception as e:
        return {"success": False, "error": f"测试连接失败: {str(e)[:200]}"}


# Preserve direct Python callers while HTTP requests enter through Gateway.
chat_stream_legacy = chat_stream = _legacy_chat_stream
chat_sync_legacy = chat_sync = _legacy_chat_sync
confirm_tool_legacy = confirm_tool = _legacy_confirm_tool
confirm_tool_sync_legacy = confirm_tool_sync = _legacy_confirm_tool_sync


def _normalize_interaction_payload(payload: dict) -> dict:
    body = dict(payload.get("body") or {})
    context = body.pop("context", None)
    body.pop("user_gid", None)
    if context is not None:
        if not isinstance(context, dict):
            raise HTTPException(status_code=400, detail="context must be an object")
        body["context_json"] = json.dumps(
            context, ensure_ascii=False, separators=(",", ":"),
        )
    return {**payload, "body": body}


async def _project_interaction_response(payload: dict, data, *, gateway=None):
    if isinstance(data, dict) and "response_json" in data:
        return json.loads(data["response_json"])
    if payload.get("operation") == "chat_stream" and isinstance(data, dict) and data.get("stream_id"):
        if gateway is None:
            raise ValueError("Gateway-managed Agent stream is unavailable")
        iterator, media_type = await gateway.claim_stream(str(data["stream_id"]))
        return StreamingResponse(
            iterator,
            media_type=media_type,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if payload.get("operation") in {"chat_stream", "confirm"} and isinstance(data, dict):
        return StreamingResponse(
            iter(data.get("events") or ()),
            media_type=data.get("media_type") or "text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return data
