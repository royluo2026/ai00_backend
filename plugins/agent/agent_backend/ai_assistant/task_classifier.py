"""
backend/ai_assistant/task_classifier.py
──────────────────────────────────────────
Phase 0 任务分类器：一次轻量 LLM 调用（非流式，≤200 token 输出），
替换 should_orchestrate() 的关键词启发式判断。

失败/超时 → 返回 None，调用方静默降级到旧流程。
"""
from __future__ import annotations

import json
import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


class TaskClassification(TypedDict):
    task_type:      str         # 诊断|规划|合规|查询|推荐|记录
    complexity:     str         # simple|multi_step|needs_decompose
    sub_tasks:      list[str]   # 若 needs_decompose，每条子任务描述（最多4条）
    requires_tools: list[str]   # 预判需要的工具名
    confidence:     float       # 分类置信度 0.0~1.0


# ── 强制工具调用 schema ────────────────────────────────────────────────────────

_CLASSIFY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "classify_task",
        "description": "对用户消息进行结构化任务分类",
        "parameters": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type":        "string",
                    "enum":        ["诊断", "规划", "合规", "查询", "推荐", "记录"],
                    "description": "任务主类型",
                },
                "complexity": {
                    "type":        "string",
                    "enum":        ["simple", "multi_step", "needs_decompose"],
                    "description": (
                        "simple=单步直接回答或单工具调用; "
                        "multi_step=单 Agent 顺序多步执行; "
                        "needs_decompose=明确需要多 Agent 并行处理的复合任务"
                    ),
                },
                "sub_tasks": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "description": "若 needs_decompose，列出每个子任务的简要描述（最多4条）",
                },
                "requires_tools": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "description": "预判需要调用的工具名列表",
                },
                "confidence": {
                    "type":        "number",
                    "description": "分类置信度 0.0~1.0",
                },
            },
            "required": ["task_type", "complexity", "confidence"],
        },
    },
}

_CLASSIFY_SYSTEM = (
    "你是任务分类器。分析用户消息，输出结构化分类结果。"
    "needs_decompose 仅用于明确需要并行处理多个独立子任务的情况（如'同时查询A和B'、'分别分析X、Y、Z'）。"
    "simple 用于单次问答。multi_step 用于需要顺序执行多步但不需要并行的任务。"
    "只调用 classify_task 工具，不输出任何解释文本。"
)


# ── 主函数 ────────────────────────────────────────────────────────────────────

def classify_task(
    message: str,
    ai_cfg: dict,
    system: str = "",
) -> TaskClassification | None:
    """
    Phase 0：结构化任务识别。

    - simple       → 直接进工具循环
    - multi_step   → 单 Agent 多步计划模式（system prompt 追加步骤提示）
    - needs_decompose → 触发 Orchestrator 多 Agent 并行

    失败/超时 → 返回 None（静默降级到旧流程）
    """
    try:
        import litellm
    except ImportError:
        return None

    messages = [
        {"role": "system", "content": _CLASSIFY_SYSTEM},
        {"role": "user",   "content": message},
    ]

    call_kwargs: dict = {
        "model":       ai_cfg.get("model", ""),
        "messages":    messages,
        "tools":       [_CLASSIFY_SCHEMA],
        "tool_choice": {"type": "function", "function": {"name": "classify_task"}},
        "max_tokens":  200,
        "api_key":     ai_cfg.get("api_key", ""),
    }
    if ai_cfg.get("api_base"):
        call_kwargs["api_base"] = ai_cfg["api_base"]
    if ai_cfg.get("extra_headers"):
        call_kwargs["extra_headers"] = ai_cfg["extra_headers"]

    try:
        resp = litellm.completion(**call_kwargs)
        msg  = resp.choices[0].message
        tcs  = getattr(msg, "tool_calls", None) or []
        if not tcs:
            return None
        args = json.loads(tcs[0].function.arguments or "{}")
        return TaskClassification(
            task_type=      args.get("task_type", "查询"),
            complexity=     args.get("complexity", "simple"),
            sub_tasks=      args.get("sub_tasks") or [],
            requires_tools= args.get("requires_tools") or [],
            confidence=     float(args.get("confidence", 0.8)),
        )
    except Exception as exc:
        logger.debug(f"[TaskClassifier] 分类失败（静默降级）: {exc}")
        return None
