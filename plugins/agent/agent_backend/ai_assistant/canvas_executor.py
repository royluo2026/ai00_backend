"""
backend/ai_assistant/canvas_executor.py
─────────────────────────────────────────
WFC 画布自主执行引擎（云端版）

设计原则：
  - LLM 不驱动每一步——由执行引擎按 step 顺序自动执行工具/数据节点
  - LLM 仅介入 agent 节点（推理/分析）和复杂 condition 节点（无法本地求值时）
  - human* 节点在自动模式下暂停，返回 paused 状态
  - progress_cb 供前端实时接收节点状态更新
"""
from __future__ import annotations

import re
import json
import logging
import datetime

logger = logging.getLogger(__name__)

# 单次 LLM 推理最大 token
_LLM_MAX_TOKENS = 400
# 上游结果截断长度（传给 LLM 的 context）
_CTX_TRUNCATE = 400


class CanvasExecutor:
    """
    执行 WFC canvas 数据（JSON），按 step 顺序运行每个节点。

    Args:
        auth_mode:   'feishu'（云端唯一模式）
        auth_token:  飞书 access_token
        owner_gid:   当前用户 GID（供工具鉴权）
        progress_cb: callable(node_id, label, status, summary)
                     status: 'running' | 'ok' | 'error' | 'skipped'
    """

    def __init__(
        self,
        auth_mode:   str = "feishu",
        auth_token:  str = "",
        owner_gid:   str = "",
        progress_cb=None,
        invocation_id: str = "",
    ):
        self.auth_mode   = auth_mode
        self.auth_token  = auth_token
        self.owner_gid   = owner_gid
        self.progress_cb = progress_cb
        self.invocation_id = invocation_id
        self.node_results: dict[str, dict] = {}
        self._exec_log:    list[str] = []
        self._log_start_ts: str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 日志工具 ──────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        self._exec_log.append(f"[{ts}] {msg}")

    def get_exec_log(self) -> list[str]:
        return list(self._exec_log)

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def execute(
        self,
        canvas_data:     dict,
        init_params:     dict | None = None,
        restore_results: dict | None = None,
    ) -> dict:
        """
        执行 canvas，返回 {status, node_results, summary}。
        status: 'completed' | 'paused' | 'halted' | 'error'

        restore_results: 上次执行已完成的 node_results（断点续跑时传入），
                         已存在的节点自动跳过重新执行。
        """
        nodes = canvas_data.get("nodes", []) or []
        if not nodes:
            return {"status": "completed", "node_results": {}, "summary": "画布无节点，执行完成"}

        if restore_results:
            self.node_results.update(restore_results)

        if init_params and "__init__" not in self.node_results:
            self.node_results["__init__"] = {
                "_status": "ok", "_summary": "初始参数",
                **init_params,
            }

        nodes_sorted = sorted(nodes, key=lambda n: int(n.get("step") or 0))

        step_groups: dict[int, list] = {}
        for n in nodes_sorted:
            s = int(n.get("step") or 0)
            step_groups.setdefault(s, []).append(n)

        self._log(f"▶ 开始执行  总节点数={len(nodes_sorted)}  auth_mode={self.auth_mode}")
        if restore_results:
            self._log(f"  （断点续跑，已有 {len(restore_results)} 个节点结果）")

        for step, group in sorted(step_groups.items()):
            for node in group:
                nid   = node.get("id", f"node_{step}")
                label = node.get("label", node.get("type", ""))
                ntype = node.get("type", "")

                if nid in self.node_results:
                    prev_st = self.node_results[nid].get("_status", "")
                    fe_st = "success" if prev_st == "ok" else prev_st
                    self._emit(nid, label, fe_st or "ok", self.node_results[nid].get("_summary", ""))
                    self._log(f"  ↷ [{nid}]「{label}」({ntype}) — 续跑跳过（已有状态：{prev_st}）")
                    continue

                self._log(f"  → step={step} [{nid}]「{label}」({ntype})")
                self._emit(nid, label, "running", "")

                result = self._execute_node(node)
                self.node_results[nid] = result

                status  = result.get("_status", "ok")
                summary = result.get("_summary", "")

                self._emit(nid, label, status, summary)

                status_icon = {"ok": "✔", "error": "✖", "skipped": "⊘", "pending_approval": "⏸"}.get(status, "?")
                self._log(f"    {status_icon} {status.upper()}: {summary[:200]}")
                if status == "error":
                    err_detail = result.get("error", "")
                    if err_detail and err_detail != summary:
                        self._log(f"    错误详情: {err_detail[:300]}")

                if result.get("_halt"):
                    if result.get("_pause"):
                        self._log(f"  ⏸ 流程暂停 — 等待人工确认节点「{label}」")
                        return {
                            "status":         "paused",
                            "halt_reason":    summary,
                            "halted_node_id": nid,
                            "halted_label":   label,
                            "node_results":   self.node_results,
                            "summary":        f"流程在节点「{label}」等待人工确认：{summary}",
                        }
                    self._log(f"  ⛔ 流程中止 — 条件节点「{label}」走 false 分支")
                    return {
                        "status":      "halted",
                        "halt_reason": summary,
                        "node_results": self.node_results,
                        "summary":     f"流程在节点「{label}」被中止：{summary}",
                    }

        overall_summary = self._build_summary(nodes_sorted)
        ok      = sum(1 for r in self.node_results.values() if r.get("_status") == "ok")
        skipped = sum(1 for r in self.node_results.values() if r.get("_status") == "skipped")
        errors  = sum(1 for r in self.node_results.values() if r.get("_status") == "error")
        self._log(f"■ 执行完成  ok={ok}  skipped={skipped}  error={errors}")
        return {
            "status":       "completed",
            "node_results": self.node_results,
            "summary":      overall_summary,
        }

    # ── 节点分发 ──────────────────────────────────────────────────────────────

    def _execute_node(self, node: dict) -> dict:
        ntype  = node.get("type", "")
        params = self._resolve_template(node.get("params", {}) or {})

        skip_keys = params.get("skip_when_empty") or []
        if isinstance(skip_keys, list) and skip_keys:
            if all(not str(params.get(k) or "").strip() for k in skip_keys):
                label = node.get("label", "")
                self._log(f"    ⊘ 跳过 — skip_when_empty 字段均为空：{skip_keys}")
                return {"_status": "skipped", "_summary": f"节点「{label}」已跳过（条件字段为空）"}

        if ntype in ("tool_read", "tool_write"):
            return self._exec_tool_node(node, params)
        if ntype == "agent":
            return self._exec_agent_node(node, params)
        if ntype == "condition":
            return self._exec_condition_node(node, params)
        if ntype in ("data_db", "data_mem", "data_file", "list"):
            return self._exec_data_node(node, params)
        if ntype == "skill_call":
            return self._exec_skill_call_node(node, params)
        if ntype in ("human", "human_approval", "human_task"):
            label = node.get("label", "") or ntype
            summary = f"流程需要人工确认：{label}"
            return {
                "_status":  "pending_approval",
                "_summary": summary,
                "_halt":    True,
                "_pause":   True,
                "label":    label,
            }
        if ntype in ("fork", "join"):
            return {"_status": "ok", "_summary": "控制流节点"}

        return {"_status": "skipped", "_summary": f"未知节点类型 {ntype}"}

    # ── tool_read / tool_write ────────────────────────────────────────────────

    def _exec_tool_node(self, node: dict, params: dict) -> dict:
        tool_name = (params.get("tool_name") or "").strip()
        node_id   = node.get("id", "?")
        node_lbl  = node.get("label", "?")

        if not tool_name or re.search(r"[\s+]", tool_name):
            self._log(f"    ⊘ 跳过 — 复合/空工具声明「{tool_name}」（由 LLM 动态调用）")
            return {
                "_status":  "skipped",
                "_summary": f"复合/空工具声明「{tool_name}」，由 LLM 调用",
            }

        _META = {"tool_name", "confirm_required", "db", "access", "skip_when_empty"}
        tool_inputs = {k: v for k, v in params.items() if k not in _META}

        self._log(f"    调用工具：{tool_name}  输入：{json.dumps(tool_inputs, ensure_ascii=False)[:300]}")

        try:
            result = {"error": "legacy canvas tools are retired; use Catalog/Gateway"}
        except Exception as e:
            self._log(f"    ✖ 工具调用抛出异常：{e}")
            return {"_status": "error", "_summary": str(e), "error": str(e)}

        # tuple 返回（某些 BOP 工具）
        if isinstance(result, tuple):
            result = result[0]

        if isinstance(result, dict) and "error" in result:
            self._log(f"    ✖ 工具返回错误：{result['error']}")
            return {"_status": "error", "_summary": result["error"], **result}

        text    = result.get("text", "") if isinstance(result, dict) else ""
        summary = (text or json.dumps(result, ensure_ascii=False))[:200]
        self._log(f"    ✔ 工具成功  摘要：{summary[:200]}")

        node_status = "ok"
        if isinstance(result, dict) and result.get("ok") is False:
            node_status = "warning"
            self._log(f"    ⚠ 工具返回 ok=False（结果有警告/错误项）")

        _count = None
        if isinstance(result, dict):
            for _cnt_key in ("errors", "total", "count"):
                if isinstance(result.get(_cnt_key), (int, float)):
                    _count = int(result[_cnt_key])
                    break

        out = {"_status": node_status, "_summary": summary, **(result if isinstance(result, dict) else {})}
        if _count is not None:
            out["_count"] = _count
        return out

    # ── agent（LLM 介入推理）────────────────────────────────────────────────

    def _exec_agent_node(self, node: dict, params: dict) -> dict:
        task_desc = params.get("task_desc", node.get("label", "执行任务"))
        context   = self._build_context_text()

        prompt = (
            f"你是工作流自动执行引擎中的推理节点。\n\n"
            f"上游节点执行结果：\n{context}\n\n"
            f"当前任务：{task_desc}\n\n"
            f"请根据以上结果，给出简洁的处理结论或操作建议（不超过 200 字）。"
        )
        self._log(f"    LLM 推理  task={task_desc[:80]}")
        try:
            answer = self._simple_llm(prompt)
            self._log(f"    LLM 回复：{answer[:200]}")
            return {"_status": "ok", "_summary": answer, "text": answer}
        except Exception as e:
            self._log(f"    LLM 失败：{e}")
            return {"_status": "error", "_summary": str(e), "error": str(e)}

    # ── condition ─────────────────────────────────────────────────────────────

    def _exec_condition_node(self, node: dict, params: dict) -> dict:
        expr          = (params.get("condition_expr") or node.get("label", "")).strip()
        true_label    = params.get("true_branch", "true")
        false_label   = params.get("false_branch", "false")
        halt_on_false = params.get("halt_on_false", False)

        self._log(f"    条件表达式：{expr}  (halt_on_false={halt_on_false})")

        ctx: dict = {}
        for res in self.node_results.values():
            if isinstance(res, dict):
                ctx.update({k: v for k, v in res.items() if not k.startswith("_")})

        try:
            value  = eval(expr, {"__builtins__": {}}, ctx)  # noqa: S307
            branch = "true_branch" if value else "false_branch"
            label  = true_label if value else false_label
            self._log(f"    条件结果：{value}  走分支：{branch}（{label}）")
            halt_detail = ""
            if not value and halt_on_false:
                for res in self.node_results.values():
                    if not isinstance(res, dict):
                        continue
                    if res.get("_status") == "error":
                        halt_detail = res.get("error") or res.get("_summary") or ""
                        break
                    if res.get("text") and not halt_detail:
                        halt_detail = str(res["text"])[:300]
            summary_text = f"条件「{expr}」不满足，流程中止：{label}"
            if halt_detail:
                summary_text += f"\n\n{halt_detail}"
            result = {
                "_status":  "ok",
                "_summary": summary_text if (not value and halt_on_false)
                            else f"条件「{expr}」= {value}，走 {branch}：{label}",
                "branch": branch,
                "value":  value,
            }
            if not value and halt_on_false:
                result["_halt"] = True
            return result
        except Exception as eval_err:
            self._log(f"    本地 eval 失败（{eval_err}），转交 LLM 判断")

        return self._llm_condition(expr, true_label, false_label, halt_on_false)

    def _llm_condition(
        self, expr: str, true_label: str, false_label: str, halt_on_false: bool
    ) -> dict:
        context = self._build_context_text()
        prompt  = (
            f"根据以下执行结果，判断下面的条件是否满足（只回答是或否，不要解释）：\n\n"
            f"执行结果：\n{context}\n\n"
            f"条件：{expr}"
        )
        try:
            answer  = self._simple_llm(prompt).strip()
            is_true = answer.startswith("是") or answer.lower().startswith("yes") or "true" in answer.lower()
            branch  = "true_branch" if is_true else "false_branch"
            label   = true_label if is_true else false_label
            result  = {
                "_status":  "ok",
                "_summary": f"LLM 判断「{expr}」={is_true}，走 {branch}：{label}",
                "branch": branch,
                "value":  is_true,
            }
            if not is_true and halt_on_false:
                result["_halt"] = True
            return result
        except Exception as e:
            self._log(f"    LLM 条件判断异常：{e}")
            result = {"_status": "error", "_summary": str(e), "error": str(e)}
            if halt_on_false:
                result["_halt"] = True
            return result

    # ── data 节点 ─────────────────────────────────────────────────────────────

    def _exec_data_node(self, node: dict, params: dict) -> dict:
        ntype = node.get("type", "")
        label = node.get("label", ntype)
        return {
            "_status":  "skipped",
            "_summary": f"数据节点「{label}」（由关联工具节点访问）",
        }

    # ── skill_call（递归）────────────────────────────────────────────────────

    def _exec_skill_call_node(self, node: dict, params: dict) -> dict:
        skill_gid = params.get("skill_gid", "")
        if not skill_gid:
            return {"_status": "skipped", "_summary": "skill_call 未配置 skill_gid"}
        try:
            from ..data.connection import get_agent_conn
            with get_agent_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT content, title FROM workmanship_app_skills WHERE gid=%s AND deleted_at IS NULL AND (owner_gid=%s OR owner_gid='__system__' OR scope='global')",
                        (skill_gid, self.owner_gid),
                    )
                    row = cur.fetchone()
            if not row:
                return {"_status": "error", "_summary": f"Skill 不存在：{skill_gid}", "error": f"Skill 不存在：{skill_gid}"}
            content = row["content"] or {}
            canvas  = content.get("canvas", {}) if isinstance(content, dict) else {}
            if not canvas:
                return {"_status": "skipped", "_summary": f"Skill「{row['title']}」无画布内容"}
            sub = CanvasExecutor(
                auth_mode=self.auth_mode,
                auth_token=self.auth_token,
                owner_gid=self.owner_gid,
            )
            result = sub.execute(canvas, init_params=params)
            return {"_status": "ok", "_summary": result.get("summary", ""), **result}
        except Exception as e:
            return {"_status": "error", "_summary": str(e), "error": str(e)}

    # ── 工具方法 ─────────────────────────────────────────────────────────────

    def _build_context_text(self) -> str:
        parts = []
        for nid, res in self.node_results.items():
            if not isinstance(res, dict):
                continue
            if res.get("_status") not in ("ok", "done"):
                continue
            text = res.get("text") or res.get("_summary", "")
            if text:
                parts.append(f"[{nid}]: {str(text)[:_CTX_TRUNCATE]}")
        return "\n".join(parts[-6:]) or "（暂无上游结果）"

    def _build_summary(self, nodes: list[dict]) -> str:
        ok      = sum(1 for r in self.node_results.values() if r.get("_status") == "ok")
        skipped = sum(1 for r in self.node_results.values() if r.get("_status") == "skipped")
        errors  = sum(1 for r in self.node_results.values() if r.get("_status") == "error")
        lines   = [f"执行完成：{ok} 个节点成功，{skipped} 个跳过，{errors} 个出错"]

        key_texts = []
        for nid, res in self.node_results.items():
            if res.get("_status") == "ok" and res.get("text"):
                key_texts.append(res["text"][:300])
        if key_texts:
            lines.append("\n关键结果：")
            lines.extend(key_texts[:3])

        error_lines = []
        for nid, res in self.node_results.items():
            if res.get("_status") == "error":
                err_msg = res.get("error") or res.get("_summary") or "未知错误"
                error_lines.append(f"  ✗ [{nid}] {err_msg[:200]}")
        if error_lines:
            lines.append("\n失败节点：")
            lines.extend(error_lines)

        skip_composite = [
            nid for nid, res in self.node_results.items()
            if res.get("_status") == "skipped" and "复合" in (res.get("_summary") or "")
        ]
        if skip_composite:
            lines.append(f"\n跳过的复合工具节点（需 LLM 按上下文动态调用）：{', '.join(skip_composite)}")

        return "\n".join(lines)

    def _resolve_template(self, params: dict) -> dict:
        """
        将 params 中 {{node_id.field}} 占位符替换为上游节点结果。
        支持 || 降级语法：{{n5.gid||__init__.version_gid}}
        """
        result: dict = {}
        for k, v in params.items():
            if isinstance(v, str) and "{{" in v:
                def _replacer(m: re.Match) -> str:
                    alternatives = [a.strip() for a in m.group(1).split("||")]
                    for alt in alternatives:
                        if "." in alt:
                            node_id, field = alt.split(".", 1)
                            val = self.node_results.get(node_id, {}).get(field)
                            if val is not None and str(val) and not str(val).startswith("{{"):
                                return str(val)
                        else:
                            return alt
                    return ""
                v = re.sub(r"\{\{([^}]+)\}\}", _replacer, v)
            result[k] = v
        return result

    def _emit(self, node_id: str, label: str, status: str, summary: str) -> None:
        if self.progress_cb:
            try:
                self.progress_cb(node_id, label, status, summary)
            except Exception:
                pass

    def _simple_llm(self, prompt: str) -> str:
        """同步调用 LLM，仅用于 agent/condition 节点推理（无工具调用）。"""
        try:
            import litellm
            from ..routers.ai_chat import _get_ai_config
            ai_cfg = _get_ai_config(self.owner_gid)
            if not ai_cfg.get("api_key"):
                raise RuntimeError("未配置 AI API Key，无法执行推理节点")
            call_kwargs: dict = {
                "model":      ai_cfg["model"],
                "messages":   [{"role": "user", "content": prompt}],
                "max_tokens": _LLM_MAX_TOKENS,
                "api_key":    ai_cfg["api_key"],
            }
            if ai_cfg.get("api_base"):
                call_kwargs["api_base"] = ai_cfg["api_base"]
            resp = litellm.completion(**call_kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"[CanvasExecutor] _simple_llm 失败: {e}")
            raise
