"""
backend/ai_assistant/orchestrator.py
──────────────────────────────────────
多 Agent Orchestrator（云端版）
--------------------------------
OrchestratorRunner 接收用户消息，调用 LLM 规划并行子任务（spawn_agent），
再用 threading 并发执行各 SubAgent，最后汇总结果。

调用方：backend/routers/ai_chat.py → _should_orchestrate() → OrchestratorRunner.run()
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .task_classifier import TaskClassification

logger = logging.getLogger(__name__)


# ── 预定义 Agent 类型的工具子集 ────────────────────────────────────────────────

_AGENT_TOOL_SUBSETS: dict[str, list[str]] = {
    "search":       ["search", "search_knowledge", "list_rules", "get_ontology_schema"],
    "bop_analyze":  ["search", "list_task_lists", "list_tasks", "list_issues",
                     "get_ontology_schema", "audit_entry_rules", "get_entry_relations"],
    "doc_writer":   ["search_knowledge", "list_rules", "search", "get_ontology_schema"],
    "task_planner": ["list_task_lists", "list_tasks", "create_task", "get_task",
                     "list_issue_lists", "list_issues"],
}

_AGENT_TYPES = list(_AGENT_TOOL_SUBSETS.keys())

# ── spawn_agent meta-tool（只在 Phase 1 使用）──────────────────────────────────

SPAWN_AGENT_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "spawn_agent",
        "description": (
            "派发一个子任务给 SubAgent 并行执行。每次调用派发一个 Agent。"
            "当用户请求涉及多个独立子任务时（如同时搜索 + 分析 + 生成报告），"
            "调用此工具将任务分发给专门的 SubAgent。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "enum": _AGENT_TYPES,
                    "description": (
                        "SubAgent 类型：search=搜索类, bop_analyze=BOP分析类, "
                        "doc_writer=文档写作类, task_planner=任务规划类"
                    ),
                },
                "instruction": {
                    "type": "string",
                    "description": "SubAgent 需要完成的具体任务描述（详细、清晰）",
                },
            },
            "required": ["agent_type", "instruction"],
        },
    },
}


# ── 数据结构 ───────────────────────────────────────────────────────────────────

@dataclass
class SubAgentDef:
    agent_id:    str
    agent_type:  str
    instruction: str
    tool_subset: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.tool_subset:
            self.tool_subset = list(_AGENT_TOOL_SUBSETS.get(self.agent_type, []))


@dataclass
class SubAgentResult:
    agent_id: str
    status:   str        # "done" | "error"
    output:   str
    error:    str | None = None


# ── 启发式触发器（保留作兜底，主路径已由 task_classifier 替代）────────────────────

_ORCHESTRATE_KEYWORDS = ("并行", "同时", "一起", "分别", "各自", "多个任务", "同步")

def should_orchestrate(message: str) -> bool:
    """
    关键词启发式降级兜底。
    主路径：ai_chat.py 调用 task_classifier.classify_task() 后根据 complexity 判断。
    此函数仅当 task_classifier 返回 None 时被调用。
    """
    return any(kw in message for kw in _ORCHESTRATE_KEYWORDS)


# ── 主 Orchestrator 类 ─────────────────────────────────────────────────────────

class OrchestratorRunner:
    """
    三阶段 Orchestrator：
    Phase 1 — 规划：LLM 调用 spawn_agent，收集 SubAgent 派发计划
    Phase 2 — 执行：threading 并行运行每个 SubAgent（最多 4 个）
    Phase 3 — 汇总：LLM 看所有结果，生成最终回答
    """

    MAX_AGENTS = 4

    def run(
        self,
        session_gid: str,
        user_msg:    str,
        ai_cfg:      dict,
        auth_mode:   str,
        auth_token:  str,
        user_gid:    str = "",
        system:      str = "",
        progress_cb: Callable[[str, str, str], None] | None = None,
        task_cls:    "TaskClassification | None" = None,
    ) -> dict:
        """
        执行 Orchestrator 全流程。
        task_cls：来自 Phase 0 task_classifier 的分类结果（可选）。
          - 有 task_cls 且含 sub_tasks → 直接跳过 Phase 1 LLM 规划，按 sub_tasks 构建 SubAgent。
          - 无 task_cls → 保持原有行为（Phase 1 LLM 规划）。
        progress_cb(agent_id, status, partial) — 实时进度回调（可选）
        返回 {"answer", "tool_calls", "pending_confirm", "orchestrator", "agents"}。
        若 Phase 1 未产生 SubAgent，返回 {"_fallback": True} 以降级到普通路径。
        """
        from .session_store import _store

        # ── Phase 1：规划 ──────────────────────────────────────────────
        if task_cls and task_cls.get("sub_tasks"):
            # 直接从 task_cls.sub_tasks 构建 SubAgent，跳过 LLM 规划
            agents = self._build_agents_from_classification(task_cls)
            logger.info(f"[Orchestrator] Phase 0 注入 sub_tasks，跳过 Phase 1 LLM 规划，{len(agents)} 个 SubAgent")
        else:
            agents, _plan_answer = self._phase1_plan(
                session_gid, user_msg, ai_cfg, auth_mode, system
            )

        if not agents:
            logger.info("[Orchestrator] Phase 1 未产生 SubAgent，降级单线程")
            return {"_fallback": True}

        logger.info(f"[Orchestrator] Phase 1 完成，{len(agents)} 个 SubAgent")

        agent_infos = [
            {
                "agent_id":    a.agent_id,
                "agent_type":  a.agent_type,
                "instruction": a.instruction,
                "status":      "pending",
                "output":      "",
            }
            for a in agents
        ]

        # ── Phase 2：并行执行 ───────────────────────────────────────────
        results: dict[str, SubAgentResult] = {}
        lock = threading.Lock()

        def _run_one(agent: SubAgentDef):
            if progress_cb:
                progress_cb(agent.agent_id, "running", "")
            for ai in agent_infos:
                if ai["agent_id"] == agent.agent_id:
                    ai["status"] = "running"

            try:
                sub_output = self._run_subagent(
                    agent, session_gid, ai_cfg, auth_mode, auth_token, user_gid, system
                )
                r = SubAgentResult(agent_id=agent.agent_id, status="done", output=sub_output)
            except Exception as exc:
                logger.warning(f"[Orchestrator] SubAgent {agent.agent_id} 失败: {exc}")
                r = SubAgentResult(
                    agent_id=agent.agent_id, status="error", output="", error=str(exc)
                )

            with lock:
                results[agent.agent_id] = r
                for ai in agent_infos:
                    if ai["agent_id"] == agent.agent_id:
                        ai["status"] = r.status
                        ai["output"] = r.output or r.error or ""

            if progress_cb:
                progress_cb(agent.agent_id, r.status, r.output or r.error or "")

        threads = [threading.Thread(target=_run_one, args=(a,), daemon=True) for a in agents]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

        logger.info(f"[Orchestrator] Phase 2 完成，结果数: {len(results)}")

        # ── Phase 3：汇总 ───────────────────────────────────────────────
        final_answer = self._phase3_summarize(
            user_msg, agents, results, ai_cfg, auth_mode, system
        )

        _store.add_turn(
            session_gid, "agent_result", final_answer,
            tool_calls=[{
                "name":       "orchestrator_summary",
                "input":      {"agents": agent_infos},
                "result":     {"agent_count": len(agents)},
                "tool_use_id": f"orch_{session_gid}",
                "confirmed":  False,
            }]
        )

        return {
            "answer":          final_answer,
            "tool_calls":      [],
            "pending_confirm": None,
            "orchestrator":    True,
            "agents":          agent_infos,
        }

    # ── Phase 0 辅助：从 task_cls 构建 SubAgent ──────────────────────────────

    def _build_agents_from_classification(
        self,
        task_cls: "TaskClassification",
    ) -> list[SubAgentDef]:
        """将 task_classifier 的 sub_tasks 列表转为 SubAgentDef 列表。"""
        agents: list[SubAgentDef] = []
        requires = set(task_cls.get("requires_tools") or [])
        type_counters: dict[str, int] = {}

        for instruction in (task_cls.get("sub_tasks") or []):
            if len(agents) >= self.MAX_AGENTS:
                break
            # 根据 requires_tools 推断最合适的 agent_type
            if requires & {"list_tasks", "create_task", "list_issue_lists", "list_issues"}:
                agent_type = "task_planner"
            elif requires & {"search_knowledge", "list_rules"}:
                agent_type = "doc_writer"
            else:
                agent_type = "search"

            count = type_counters.get(agent_type, 0)
            type_counters[agent_type] = count + 1
            agents.append(SubAgentDef(
                agent_id=f"{agent_type}_{count}",
                agent_type=agent_type,
                instruction=instruction,
            ))
        return agents

    # ── Phase 1：规划 ─────────────────────────────────────────────────────────

    def _phase1_plan(
        self,
        session_gid: str,
        user_msg:    str,
        ai_cfg:      dict,
        auth_mode:   str,
        system:      str,
    ) -> tuple[list[SubAgentDef], str]:
        import litellm

        messages = [
            {
                "role":    "system",
                "content": (
                    (system + "\n\n") if system else ""
                ) + (
                    "你是任务编排器。用户给出复杂任务时，"
                    "请调用 spawn_agent 工具将任务分解给不同类型的 SubAgent 并行处理。"
                    "每个 SubAgent 负责一个独立子任务。最多派发 4 个 SubAgent。"
                    "若任务简单不需并行，则不调用 spawn_agent，直接回复用户。"
                ),
            },
            {"role": "user", "content": user_msg},
        ]

        call_kwargs: dict = {
            "model":      ai_cfg["model"],
            "messages":   messages,
            "tools":      [SPAWN_AGENT_TOOL_OPENAI],
            "max_tokens": 2048,
            "api_key":    ai_cfg["api_key"],
        }
        if ai_cfg.get("api_base"):
            call_kwargs["api_base"] = ai_cfg["api_base"]
        if ai_cfg.get("extra_headers"):
            call_kwargs["extra_headers"] = ai_cfg["extra_headers"]

        try:
            resp = litellm.completion(**call_kwargs)
        except Exception as exc:
            logger.warning(f"[Orchestrator] Phase 1 LLM 调用失败: {exc}")
            return [], ""

        msg = resp.choices[0].message
        plan_answer = msg.content or ""
        tool_calls  = getattr(msg, "tool_calls", None) or []

        agents: list[SubAgentDef] = []
        type_counters: dict[str, int] = {}

        for tc in tool_calls:
            if tc.function.name != "spawn_agent":
                continue
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                continue
            agent_type  = args.get("agent_type", "search")
            instruction = args.get("instruction", "")
            if not instruction:
                continue
            count = type_counters.get(agent_type, 0)
            type_counters[agent_type] = count + 1
            agent_id = f"{agent_type}_{count}"
            agents.append(SubAgentDef(
                agent_id=agent_id, agent_type=agent_type, instruction=instruction
            ))
            if len(agents) >= self.MAX_AGENTS:
                break

        return agents, plan_answer

    # ── SubAgent 执行 ─────────────────────────────────────────────────────────

    def _run_subagent(
        self,
        agent:             SubAgentDef,
        parent_session_gid: str,
        ai_cfg:            dict,
        auth_mode:         str,
        auth_token:        str,
        user_gid:          str,
        system:            str,
    ) -> str:
        """
        在 ghost session 中运行单个 SubAgent，返回文本结果。
        使用 litellm 直接调用 + tool_handlers 执行工具（同步，无 SSE）。
        """
        import litellm
        from .tool_registry import ALL_TOOLS_OPENAI
        from .tool_handlers import dispatch as tool_dispatch

        sub_session_gid = f"{parent_session_gid}_sub_{agent.agent_id}"

        # 筛选出该 SubAgent 允许使用的工具
        allowed = set(agent.tool_subset)
        sub_tools = [t for t in ALL_TOOLS_OPENAI if t["function"]["name"] in allowed]

        messages = [
            {"role": "system", "content": system or "你是 AI 工艺助手小柔。"},
            {"role": "user",   "content": agent.instruction},
        ]

        call_kwargs: dict = {
            "model":      ai_cfg["model"],
            "messages":   messages,
            "tools":      sub_tools or None,
            "max_tokens": 2048,
            "api_key":    ai_cfg["api_key"],
        }
        if ai_cfg.get("api_base"):
            call_kwargs["api_base"] = ai_cfg["api_base"]
        if ai_cfg.get("extra_headers"):
            call_kwargs["extra_headers"] = ai_cfg["extra_headers"]

        MAX_ITER = 8
        for _ in range(MAX_ITER):
            resp = litellm.completion(**call_kwargs)
            msg  = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                return (msg.content or "（无结果）").strip()

            # 追加 assistant 消息
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": tool_calls})

            # 执行工具
            for tc in tool_calls:
                try:
                    inputs = json.loads(tc.function.arguments or "{}")
                except Exception:
                    inputs = {}
                result = tool_dispatch(
                    tool_name=tc.function.name,
                    inputs=inputs,
                    auth_mode=auth_mode,
                    auth_token=auth_token,
                    user_gid=user_gid,
                    session_gid=sub_session_gid,
                )
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result, ensure_ascii=False),
                })

            call_kwargs["messages"] = messages

        return "（SubAgent 已达最大迭代次数）"

    # ── Phase 3：汇总 ─────────────────────────────────────────────────────────

    def _phase3_summarize(
        self,
        user_msg: str,
        agents:   list[SubAgentDef],
        results:  dict[str, SubAgentResult],
        ai_cfg:   dict,
        auth_mode: str,
        system:   str,
    ) -> str:
        import litellm

        summary_parts = []
        for agent in agents:
            r = results.get(agent.agent_id)
            if r and r.status == "done" and r.output:
                summary_parts.append(
                    f"### SubAgent [{agent.agent_type}] 执行结果\n"
                    f"任务：{agent.instruction}\n"
                    f"结果：{r.output}"
                )
            elif r and r.status == "error":
                summary_parts.append(
                    f"### SubAgent [{agent.agent_type}] 执行失败\n"
                    f"任务：{agent.instruction}\n"
                    f"错误：{r.error}"
                )

        sub_results_text = "\n\n".join(summary_parts)

        messages = [
            {"role": "system",    "content": system or "你是 AI 工艺助手小柔。"},
            {"role": "user",      "content": user_msg},
            {"role": "assistant", "content": (
                f"我已将任务分发给 {len(agents)} 个 SubAgent 并行处理，以下是各 SubAgent 的结果：\n\n"
                + sub_results_text
            )},
            {"role": "user", "content": (
                "请综合以上所有 SubAgent 的结果，为用户提供完整、清晰的最终答案。"
                "如果某个 SubAgent 失败了，请说明并基于其他结果给出最佳答复。"
            )},
        ]

        call_kwargs: dict = {
            "model":      ai_cfg["model"],
            "messages":   messages,
            "max_tokens": 4096,
            "api_key":    ai_cfg["api_key"],
        }
        if ai_cfg.get("api_base"):
            call_kwargs["api_base"] = ai_cfg["api_base"]
        if ai_cfg.get("extra_headers"):
            call_kwargs["extra_headers"] = ai_cfg["extra_headers"]

        try:
            resp = litellm.completion(**call_kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning(f"[Orchestrator] Phase 3 汇总失败: {exc}")
            return (
                f"（汇总 LLM 调用失败：{exc}）\n\n以下是各 SubAgent 的原始结果：\n\n"
                + sub_results_text
            )
