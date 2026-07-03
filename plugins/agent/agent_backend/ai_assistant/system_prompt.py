"""
backend/ai_assistant/system_prompt.py
──────────────────────────────────────
动态系统提示词构建器。
"""
from __future__ import annotations

_SYSTEM_OVERVIEW = """你是小柔（AI00 智能助手），汽车工艺系统 AI00 的智能助理。
你帮助工程师管理任务、问题、工艺知识、BOP 结构分析、工作流规划等工作。

## 当前系统
- 平台：AI00 汽车工艺系统 V1.0（云端模式）
- 存储：PostgreSQL 云端数据库
- 认证：飞书 OAuth

## 回复规范
- 用中文回复，简洁清晰
- 优先调用工具获取实时数据，不要凭空猜测
- 写操作（创建/更新）需等用户确认
- 遇到不确定的需求，先调用 ask_for_clarification 工具询问
"""

_WFC_SECTION_DEFAULT = """
【WFC 画布对话模式】
你当前处于"工作流画布"独立窗口（WFC），用户正在规划自动化工作流或可视化工艺结构。
此模式下的对话目标：帮助用户把模糊的需求转化为结构化的工作流画布或沙盘白板。

画布模式说明：
- **流程图模式（flow）**：有泳道的节点流程图，适合自动化工作流规划（节点类型：agent/tool_read/tool_write/list/human_approval/human_task）
- **沙盘模式（sandbox）**：自由定位白板，适合可视化展示 BOP 工艺结构、头脑风暴（节点类型：bop_node/bop_station/bop_op/process/decision/text/metric/resource/note 等）

行为规则：
1. 当用户的需求涉及多个决策分支、备选方案或需要逐步确认时，
   **主动调用 `create_discussion_topic` 工具**，将问题拆解为结构化话题卡，
   供用户点选方案，而不是在对话气泡里罗列选项让用户手动回复。
2. 话题卡确认完毕（用户说"可以了""开始生成"等）后，
   调用 `generate_canvas` 生成画布结构。
3. 单一明确的需求可以跳过话题讨论，直接生成画布。
4. 每次调用 `create_discussion_topic` 时，`questions` 数组的 `id` 字段
   必须唯一且简短（如 q1、q2、q1_1），父子关系通过 `parentId` 引用。
5. 画布状态（如有）已在"当前工作上下文"中给出，可直接引用现有节点信息。
6. 用户想可视化 BOP 工艺结构时：先调用 `list_bop_versions` 确认版本，
   再调用 `bop_to_canvas` 工具（自动切换到沙盘模式，按工位列布局渲染工艺卡片）。
（提示：可在知识库中创建标签含 wfc_guide 的条目来自定义以上指令）
"""


def build(
    user_name: str = "工程师",
    user_role: str = "member",
    auth_mode: str = "feishu",
    context: dict | None = None,
    owner_gid: str = "",
) -> str:
    parts = [_SYSTEM_OVERVIEW]

    # 用户信息
    parts.append(f"\n## 当前用户\n- 姓名：{user_name}\n- 角色：{user_role}")

    # 上下文注入
    if context:
        ctx_lines = ["## 当前上下文"]
        if context.get("page"):
            ctx_lines.append(f"- 当前页面：{context['page']}")
        if context.get("current_page"):
            ctx_lines.append(f"- 当前页面：{context['current_page']}")
        if context.get("project_name"):
            ctx_lines.append(f"- 项目：{context['project_name']}")
        if context.get("bop_version"):
            ctx_lines.append(f"- BOP 版本：{context['bop_version']}")
        if context.get("item_type"):
            ctx_lines.append(f"- 当前对象类型：{context['item_type']}")
        if context.get("item_gid"):
            ctx_lines.append(f"- 当前对象GID：{context['item_gid']}")
        if context.get("canvas_context"):
            ctx_lines.append(f"- 画布状态：{context['canvas_context']}")
        if context.get("extra"):
            ctx_lines.append(f"- 补充信息：{context['extra']}")
        parts.append("\n".join(ctx_lines))

        # WFC 画布对话模式指令
        if context.get("current_page") == "wfc_canvas":
            custom = _inject_wfc_guide()
            parts.append(custom if custom else _WFC_SECTION_DEFAULT)

    # 用户偏好（从 DB 读取，失败则跳过）
    try:
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pref_key, pref_value FROM app.user_preferences WHERE user_gid=%s LIMIT 20",
                    (owner_gid,)
                )
                prefs = {r["pref_key"]: r["pref_value"] for r in cur.fetchall()}
        if prefs:
            pref_lines = ["## 用户偏好"] + [f"- {k}: {v}" for k, v in prefs.items()]
            parts.append("\n".join(pref_lines))
    except Exception:
        pass

    # Knowledge RAG（system_doc 标签）
    try:
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT title, content_md FROM knowledge.knowledge_entries
                    WHERE tags::text LIKE '%system_doc%'
                    ORDER BY created_at DESC LIMIT 5
                """)
                docs = cur.fetchall()
        if docs:
            rag_lines = ["## 系统参考文档（RAG）"]
            for d in docs:
                rag_lines.append(f"- {d['title']}: {(d.get('content_md') or '')[:200]}")
            parts.append("\n".join(rag_lines))
    except Exception:
        pass

    return "\n\n".join(parts)


def _inject_wfc_guide() -> str:
    """
    查找知识库中 tags 含 'wfc_guide' 的条目，返回其内容作为 WFC 模式指令。
    找到则返回格式化字符串（替换默认 wfc_section），找不到返回空字符串。
    """
    try:
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT title, content_md FROM knowledge.knowledge_entries
                    WHERE tags::text LIKE '%wfc_guide%'
                    ORDER BY created_at DESC LIMIT 1
                """)
                row = cur.fetchone()
        if not row:
            return ""
        title   = row["title"] or "WFC 画布对话模式（自定义）"
        content = (row.get("content_md") or "").strip()
        if not content:
            return ""
        return f"\n【{title}】\n{content}\n"
    except Exception:
        return ""

