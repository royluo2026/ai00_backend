"""
backend/ai_assistant/tool_registry.py
──────────────────────────────────────
AI 工具注册表（工具定义，供 LiteLLM 工具调用使用）
"""
from __future__ import annotations

_READ_TOOLS = [
    {
        "name": "global_search",
        "description": (
            "全局跨域搜索（等同于 Ctrl+O 全局搜索），一次调用同时搜索："
            "BOP工艺节点、任务、问题、知识库文档、工艺规则、飞书联系人/群/文档/日程。"
            "当用户询问'有没有关于X的内容''搜一下X''找找X相关'时优先使用此工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "搜索关键词"},
                "categories": {
                    "type": "string",
                    "description": "限定分类，逗号分隔：bop,task,issue,knowledge,rule,feishu。留空=全部（不含飞书）",
                },
                "limit": {"type": "integer", "description": "每分类最多返回条数，默认5"},
            },
            "required": ["q"],
        },
    },
    {
        "name": "search",
        "description": "跨模块统一关键词搜索（任务/问题/知识库/规则/BOP）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
                "modules": {"type": "string", "description": "限定模块，逗号分隔：task,issue,knowledge,rule,bop"},
                "limit":   {"type": "integer", "description": "每模块最多返回条数，默认5"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "list_tasks",
        "description": "列出任务，支持按状态/优先级/关键词/清单过滤。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":  {"type": "string"},
                "list_gid": {"type": "string", "description": "清单GID"},
                "status":   {"type": "string", "enum": ["pending", "in_progress", "completed", "closed"]},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "limit":    {"type": "integer", "description": "最多返回条数，默认20"},
            },
        },
    },
    {
        "name": "get_task",
        "description": "获取单条任务详情。",
        "input_schema": {
            "type": "object",
            "properties": {"gid": {"type": "string", "description": "任务GID"}},
            "required": ["gid"],
        },
    },
    {
        "name": "get_issue",
        "description": "获取单条问题详情。",
        "input_schema": {
            "type": "object",
            "properties": {"gid": {"type": "string", "description": "问题GID"}},
            "required": ["gid"],
        },
    },
    {
        "name": "list_task_lists",
        "description": "列出所有任务清单。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_issue_lists",
        "description": "列出所有问题清单。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_issues",
        "description": "列出问题，支持按状态/关键词/清单过滤。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":  {"type": "string"},
                "list_gid": {"type": "string"},
                "status":   {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "limit":    {"type": "integer", "description": "最多返回条数，默认20"},
            },
        },
    },
    {
        "name": "list_projects",
        "description": "列出所有项目。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_knowledge",
        "description": "在知识库中全文搜索条目（标题/标签/描述）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
                "limit":   {"type": "integer", "description": "最多返回条数，默认10"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_knowledge_entry",
        "description": "获取单条知识库条目的详细内容。",
        "input_schema": {
            "type": "object",
            "properties": {"gid": {"type": "string", "description": "知识条目GID"}},
            "required": ["gid"],
        },
    },
    {
        "name": "get_knowledge_document",
        "description": "读取有权访问的团队Markdown文档；可固定到指定revision，并返回可验证来源。",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_gid": {"type": "string", "description": "知识文档GID"},
                "revision_gid": {"type": "string", "description": "可选；指定不可变版本GID"},
            },
            "required": ["document_gid"],
        },
    },    {
        "name": "list_rules",
        "description": "列出工艺规则，支持按状态/类型过滤。",
        "input_schema": {
            "type": "object",
            "properties": {
                "status":    {"type": "string", "description": "active|inactive|draft"},
                "rule_type": {"type": "string"},
                "limit":     {"type": "integer", "description": "最多返回条数，默认20"},
            },
        },
    },
    {
        "name": "list_approval_orders",
        "description": "列出审批单，支持按状态过滤。",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "pending|approved|rejected"},
                "limit":  {"type": "integer"},
            },
        },
    },
]

_WRITE_TOOLS_CONFIRM = [
    {
        "name": "create_task",
        "description": "创建新任务。需用户确认。",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "任务标题（必填）"},
                "priority":    {"type": "string", "description": "low|normal|high|urgent"},
                "description": {"type": "string"},
                "due_date":    {"type": "string", "description": "YYYY-MM-DD"},
                "list_gid":    {"type": "string", "description": "目标清单GID"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_task",
        "description": "更新任务字段（状态/标题/优先级/描述/截止日期等）。需用户确认。",
        "input_schema": {
            "type": "object",
            "properties": {
                "gid":         {"type": "string", "description": "任务GID（必填）"},
                "status":      {"type": "string"},
                "title":       {"type": "string"},
                "priority":    {"type": "string"},
                "description": {"type": "string"},
                "due_date":    {"type": "string"},
            },
            "required": ["gid"],
        },
    },
    {
        "name": "create_issue",
        "description": "创建新问题记录。需用户确认。",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "问题标题（必填）"},
                "severity":    {"type": "string", "description": "low|medium|high|critical"},
                "description": {"type": "string"},
                "list_gid":    {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_issue",
        "description": "更新问题字段。需用户确认。",
        "input_schema": {
            "type": "object",
            "properties": {
                "gid":         {"type": "string", "description": "问题GID（必填）"},
                "status":      {"type": "string"},
                "title":       {"type": "string"},
                "severity":    {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["gid"],
        },
    },
    {
        "name": "create_approval_order",
        "description": "创建新审批单。需用户确认。",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":        {"type": "string", "description": "审批单标题（必填）"},
                "description":  {"type": "string"},
                "approver_gid": {"type": "string"},
            },
            "required": ["title"],
        },
    },
]

_WRITE_TOOLS_NO_CONFIRM = [
    {
        "name": "add_task_progress_log",
        "description": "为任务追加进度备注（不修改任务状态）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "gid":     {"type": "string", "description": "任务GID（必填）"},
                "content": {"type": "string", "description": "进度备注内容"},
            },
            "required": ["gid", "content"],
        },
    },
    {
        "name": "run_skill_canvas",
        "description": "执行一个 Skill 画布（按阶段执行所有节点）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_gid":    {"type": "string", "description": "Skill GID（必填）"},
                "user_inputs":  {"type": "object", "description": "用户输入的初始参数"},
                "pause_token":  {"type": "string", "description": "从暂停点继续时传入"},
                "resume_inputs":{"type": "object", "description": "人工步骤确认后的输入"},
            },
            "required": ["skill_gid"],
        },
    },
]

_SYSTEM_TOOLS = [
    {
        "name": "calculate",
        "description": "执行安全的数学表达式计算。",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学/日期表达式字符串"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "save_preference",
        "description": "保存用户长期偏好记忆（如回复语言、风格）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "key":   {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "list_preferences",
        "description": "查看当前用户已保存的所有长期偏好记忆。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ask_for_clarification",
        "description": "当需要更多信息才能完成任务时，向用户提问。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "要向用户提问的问题"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "generate_canvas",
        "description": (
            "生成工作流画布（流程泳道图），前端自动渲染。"
            "用户说「在画布里规划」「生成画布」「转为工作流」时调用。"
            "纵轴=lanes[]（泳道/角色），横轴=step_labels[]（自定义列标题），"
            "节点用lane_id+step(1-based)定位到单元格。"
            "⚠️ 重要约束：同一 step 列的不同泳道节点表示【并行执行】，"
            "顺序流程中每个步骤必须占用不同的 step 编号，禁止把先后顺序的步骤放在同一 step 列。"
            "例如：A→B→C 三步顺序流程，A用step=1，B用step=2，C用step=3，不能共用同一个step。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "画布标题"},
                "step_labels": {
                    "type": "array",
                    "description": "横轴列标题，如[\"需求\",\"设计\",\"开发\",\"测试\",\"发布\"]。节点step(1-based)对应下标+1。",
                    "items": {"type": "string"},
                },
                "lanes": {
                    "type": "array",
                    "description": "泳道列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":    {"type": "string"},
                            "label": {"type": "string", "description": "泳道名称"},
                        },
                        "required": ["id", "label"],
                    },
                },
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":      {"type": "string"},
                            "type":    {
                                "type": "string",
                                "enum": [
                                    "agent", "tool_read", "tool_write", "list",
                                    "human_approval", "human_task",
                                    "bop_node", "bop_station", "bop_op",
                                    "process", "decision", "data",
                                    "text", "metric", "resource", "link", "note", "container",
                                    "ui_select", "ui_form", "ui_button_group",
                                    "ui_table", "ui_text", "ui_metric",
                                    "ui_confirm", "ui_checklist", "ui_badge_group",
                                    "ui_section", "ui_result",
                                ],
                            },
                            "label":   {"type": "string"},
                            "lane_id": {"type": "string", "description": "所在泳道id（必填）"},
                            "step":    {"type": "integer", "description": "所在列，1-based（必填）"},
                            "params":  {"type": "object", "description": "节点补充参数，自由键值对"},
                        },
                        "required": ["id", "type", "label"],
                    },
                },
                "connections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":   {"type": "string"},
                            "from": {"type": "string"},
                            "to":   {"type": "string"},
                            "type": {"type": "string", "enum": ["dependency", "dataflow"]},
                        },
                        "required": ["id", "from", "to", "type"],
                    },
                },
            },
            "required": ["title", "nodes"],
        },
    },
    {
        "name": "open_in_container",
        "description": "在 WFC 窗口底部容器中打开指定页面。",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "页面标识: task|issue|bop|knowledge_hub|canvas"},
                "title":   {"type": "string", "description": "标签页标题"},
                "url":     {"type": "string", "description": "自定义URL（可选）"},
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "create_discussion_topic",
        "description": "在画布话题讨论区创建结构化多层级话题卡（适合有父子层级的决策树）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "话题标题"},
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":       {"type": "string"},
                            "text":     {"type": "string"},
                            "parentId": {"type": "string", "description": "父问题ID，顶级不填"},
                            "options":  {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id":   {"type": "string"},
                                        "text": {"type": "string"},
                                    },
                                    "required": ["id", "text"],
                                },
                            },
                        },
                        "required": ["id", "text"],
                    },
                },
            },
            "required": ["title", "questions"],
        },
    },
    # ── 记忆工具 ────────────────────────────────────────────────────────────────
    {
        "name": "save_memory",
        "description": (
            "保存结构化 AI 记忆条目（比 save_preference 更丰富，支持分类标签）。"
            "适合保存项目上下文、工程规律、领域知识等跨会话信息。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "记忆唯一键（简短描述性名称，如 'x11_project_context'）",
                },
                "content": {
                    "type": "string",
                    "description": "记忆内容（详细描述）",
                },
                "tag": {
                    "type": "string",
                    "enum": ["preference", "project_context", "learned_pattern", "domain_rule"],
                    "description": "记忆分类标签，默认 preference",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "若 key 已存在是否覆盖，默认 true",
                },
            },
            "required": ["key", "content"],
        },
    },
    {
        "name": "recall_memory",
        "description": "检索历史 AI 记忆，支持关键词搜索和标签过滤。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索关键词或自然语言描述",
                },
                "tag_filter": {
                    "type": "string",
                    "description": "按标签过滤：preference|project_context|learned_pattern|domain_rule",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数，默认10",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_memories",
        "description": "列出当前用户的所有 AI 记忆条目（按标签分组）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "最多返回条数，默认100"},
            },
        },
    },
    # ── 画布双向工具 ─────────────────────────────────────────────────────────────
    {
        "name": "get_canvas_state",
        "description": (
            "读取当前会话关联的工作流画布状态（节点列表、连接关系等）。"
            "仅当用户在画布页面发起对话时有效。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "canvas_id": {
                    "type": "string",
                    "description": "画布ID（可选，不传则使用会话关联的画布）",
                },
            },
        },
    },
    {
        "name": "get_selected_elements",
        "description": (
            "获取用户在画布/视图中当前选中的元素列表（gid、类型、标签等）。"
            "仅当用户在相关页面发起对话且有选中元素时有效。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "flag_for_review",
        "description": (
            "标记当前问题需要人工复核。当 AI 对结果不确定、发现潜在风险或无法给出可靠答案时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "需要人工复核的原因说明",
                },
                "context": {
                    "type": "string",
                    "description": "问题相关上下文（可选）",
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "紧急程度，默认 medium",
                },
            },
            "required": ["reason"],
        },
    },
    # ── 知识增强工具 ──────────────────────────────────────────────────────────────
    {
        "name": "find_similar_cases",
        "description": (
            "在任务/问题/知识库中语义搜索相似历史案例。"
            "比 search_knowledge 更聚焦于「相似情境」匹配，返回相似度评分。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用自然语言描述的情境或问题",
                },
                "item_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["issue", "task", "knowledge"]},
                    "description": "搜索范围，默认全搜 ['issue', 'task', 'knowledge']",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数，默认5",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "aggregate_history",
        "description": (
            "对任务或问题进行聚合统计分析（按状态/优先级/严重度/时间分组统计数量）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_type": {
                    "type": "string",
                    "enum": ["task", "issue"],
                    "description": "统计对象类型",
                },
                "group_by": {
                    "type": "string",
                    "enum": ["status", "priority", "severity", "created_week"],
                    "description": "分组维度，默认 status",
                },
                "filter_status": {
                    "type": "string",
                    "description": "按状态过滤（可选）",
                },
                "date_range": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d"],
                    "description": "时间范围过滤（可选）",
                },
            },
            "required": ["item_type"],
        },
    },
    {
        "name": "check_rules",
        "description": (
            "针对具体工艺场景，检索适用的工艺规则并判断强制/建议/参考级别。"
            "返回含置信度和规则强度的规则列表。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": "工艺场景描述（如'紧固件装配'、'焊接操作'）",
                },
                "part_no": {
                    "type": "string",
                    "description": "零件号（可选，用于精确匹配）",
                },
                "operation_type": {
                    "type": "string",
                    "description": "操作类型（可选）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数，默认10",
                },
            },
            "required": ["scenario"],
        },
    },
    {
        "name": "recommend_practice",
        "description": (
            "根据工艺场景推荐相关的最佳实践和经验教训。"
            "搜索 lesson_learned / guide 类型的知识条目。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": "工艺场景或问题描述",
                },
                "context": {
                    "type": "string",
                    "description": "额外上下文信息（可选）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数，默认5",
                },
            },
            "required": ["scenario"],
        },
    },
]

# LiteLLM/OpenAI tools format (function calling)
def _to_openai_format(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"],
            },
        }
        for t in tools
    ]


ALL_TOOLS_RAW: list[dict] = (
    _READ_TOOLS + _WRITE_TOOLS_CONFIRM + _WRITE_TOOLS_NO_CONFIRM + _SYSTEM_TOOLS
)

ALL_TOOLS_RAW += [
    {
        "name": "get_ontology_schema",
        "description": (
            "查询某个 BOP 节点类型（node_type）的本体字段定义，返回该类的数据属性（字段名、类型、"
            "必填、范围约束）和已绑定的 CEL 规则。用于了解某类节点'有哪些字段'或'有哪些约束'。"
            "示例：node_type='operation' 可获得增值工时、总工时等字段的完整定义。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_type": {
                    "type": "string",
                    "description": (
                        "BOP 节点类型，如 operation / station_process / operator_process / "
                        "line_process / project_equipment / project_tooling / project_tools / "
                        "project_roles / physical_station / physical_equipment"
                    ),
                },
            },
            "required": ["node_type"],
        },
    },
    {
        "name": "audit_entry_rules",
        "description": (
            "对某个 BOP 条目执行工艺规则审计，检查该条目的实际字段值是否满足本体定义的 CEL 规则。"
            "返回未通过的规则列表（规则名、结果 fail/warn、说明）。结果为空表示全部通过。"
            "需要提供 entry_gid（BOP 条目的 gid）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_gid": {"type": "string", "description": "BOP 条目的 gid"},
                "node_type": {"type": "string", "description": "BOP 节点类型（可选，若不填则自动从数据库读取）"},
            },
            "required": ["entry_gid"],
        },
    },
    {
        "name": "get_entry_relations",
        "description": (
            "通过本体语义查询某个 BOP 条目的所有实例级关联，返回该条目关联的工具、工装、零件、"
            "问题、任务、知识等实体列表。本体驱动：先从本体获取该节点类型的对象属性定义，"
            "再查 bop_entry_links 取实际关联数据。"
            "示例：查 OP-020 的关联 → 返回使用了哪些工具、关联了哪些问题、装配哪些零件等。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_gid": {"type": "string", "description": "BOP 条目的 gid"},
                "rel_type":  {
                    "type": "string",
                    "description": "过滤指定关系类型（可选），如 hasTool / hasIssue / usesPart，留空=全部",
                },
            },
            "required": ["entry_gid"],
        },
    },
]

ALL_TOOLS_OPENAI: list[dict] = _to_openai_format(ALL_TOOLS_RAW)

# Set of tool names that require user confirmation
WRITE_TOOLS_CONFIRM: set[str] = {t["name"] for t in _WRITE_TOOLS_CONFIRM}


def get_all_tools_with_skills(owner_gid: str = "", auth_mode: str = "feishu") -> list[dict]:
    """返回所有工具（含动态 Skill 工具）的 OpenAI format 列表。"""
    tools = list(ALL_TOOLS_OPENAI)
    # 动态 skill 工具：从数据库读取 active skills
    try:
        from ..data.connection import get_agent_conn
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT gid, name, title, description FROM workmanship_app_skills
                    WHERE status='active' AND deleted_at IS NULL AND (owner_gid=%s OR owner_gid='__system__' OR scope='global')
                    ORDER BY sort_order ASC LIMIT 20
                """, (owner_gid,))
                skills = cur.fetchall()
        for s in skills:
            tools.append({
                "type": "function",
                "function": {
                    "name": f"skill_tool_{s['name']}",
                    "description": f"[Skill] {s['title']}: {s['description'][:200]}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_inputs": {"type": "object", "description": "传入 Skill 的用户参数"},
                        },
                    },
                },
            })
    except Exception:
        pass
    return tools


def build_catalog_tool_registry(release, *, client=None):
    """Build the authoritative Agent tool set from one pinned Catalog release."""
    from .catalog_tools import CatalogToolRegistry
    return CatalogToolRegistry(release, client=client)


def catalog_tools_openai(registry) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in registry.tools()
    ]
