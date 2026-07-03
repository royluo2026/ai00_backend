"""
backend/ai_assistant/engineering_skills_seed.py
─────────────────────────────────────────────────
预定义 6 个工程框架技能，写入 app.skills 表（ON CONFLICT DO NOTHING，幂等安全）。
在 backend/main.py lifespan startup 阶段调用 seed_engineering_skills()。

每个技能是完整的 Canvas 定义（skill_type='canvas'，scope='global'，is_system=True）。
content JSONB 包含 nodes 和 connections 两个字段，节点格式兼容 WFC CanvasShell。
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def _gid(seed: str) -> str:
    """从固定种子生成稳定的 UUID（确保幂等）。"""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ai00.skill.{seed}")).replace("-", "")


# ── 技能定义 ────────────────────────────────────────────────────────────────────

_SKILLS: list[dict] = [
    # ── 1. 8D 问题分析法 ──────────────────────────────────────────────────────
    {
        "name":        "8d_problem_solving",
        "title":       "8D 问题分析法",
        "description": "通过8个规范步骤系统化解决工艺质量问题：紧急措施→团队→问题描述→临时遏制→根因→永久对策→验证→预防→总结",
        "icon":        "8d",
        "tags":        ["质量", "问题分析", "8D", "工程方法"],
        "content": {
            "nodes": [
                {"id": "d0_human",  "label": "D0 紧急措施评估",  "type": "human",  "position": {"x": 100,  "y": 100}},
                {"id": "d0_agent",  "label": "D0 评估AI辅助",    "type": "agent",  "position": {"x": 100,  "y": 200}, "config": {"prompt": "评估问题紧迫性，建议是否需要立即采取紧急遏制措施"}},
                {"id": "d1_human",  "label": "D1 组建团队",       "type": "human",  "position": {"x": 300,  "y": 100}},
                {"id": "d1_agent",  "label": "D1 团队建议",       "type": "agent",  "position": {"x": 300,  "y": 200}, "config": {"prompt": "根据问题类型建议所需团队成员角色和职责"}},
                {"id": "d2_human",  "label": "D2 问题描述",       "type": "human",  "position": {"x": 500,  "y": 100}},
                {"id": "d2_agent",  "label": "D2 IS/IS NOT分析",  "type": "agent",  "position": {"x": 500,  "y": 200}, "config": {"prompt": "协助完成IS/IS NOT矩阵分析，量化问题范围和影响"}},
                {"id": "d3_human",  "label": "D3 临时遏制措施",   "type": "human",  "position": {"x": 700,  "y": 100}},
                {"id": "d3_agent",  "label": "D3 遏制方案推荐",   "type": "agent",  "position": {"x": 700,  "y": 200}, "config": {"prompt": "推荐临时遏制措施，防止问题扩散"}},
                {"id": "d4_human",  "label": "D4 根因分析",       "type": "human",  "position": {"x": 900,  "y": 100}},
                {"id": "d4_agent",  "label": "D4 根因辅助分析",   "type": "agent",  "position": {"x": 900,  "y": 200}, "config": {"prompt": "使用5Why/鱼骨图方法辅助识别根本原因"}},
                {"id": "d5_human",  "label": "D5 永久纠正措施",   "type": "human",  "position": {"x": 1100, "y": 100}},
                {"id": "d5_agent",  "label": "D5 方案评估",       "type": "agent",  "position": {"x": 1100, "y": 200}, "config": {"prompt": "评估候选纠正措施的可行性、有效性和副作用"}},
                {"id": "d6_human",  "label": "D6 实施与验证",     "type": "human",  "position": {"x": 1300, "y": 100}},
                {"id": "d6_agent",  "label": "D6 验证方案",       "type": "agent",  "position": {"x": 1300, "y": 200}, "config": {"prompt": "设计验证计划，确认措施有效性"}},
                {"id": "d7_human",  "label": "D7 预防再发",       "type": "human",  "position": {"x": 1500, "y": 100}},
                {"id": "d7_agent",  "label": "D7 预防措施",       "type": "agent",  "position": {"x": 1500, "y": 200}, "config": {"prompt": "识别类似潜在问题，提出系统性预防措施"}},
                {"id": "d8_agent",  "label": "D8 总结报告",       "type": "agent",  "position": {"x": 1700, "y": 150}, "config": {"prompt": "综合所有D步骤输出完整的8D报告（Markdown格式）"}},
            ],
            "connections": [
                {"from": "d0_human", "to": "d0_agent"},
                {"from": "d0_agent", "to": "d1_human"},
                {"from": "d1_human", "to": "d1_agent"},
                {"from": "d1_agent", "to": "d2_human"},
                {"from": "d2_human", "to": "d2_agent"},
                {"from": "d2_agent", "to": "d3_human"},
                {"from": "d3_human", "to": "d3_agent"},
                {"from": "d3_agent", "to": "d4_human"},
                {"from": "d4_human", "to": "d4_agent"},
                {"from": "d4_agent", "to": "d5_human"},
                {"from": "d5_human", "to": "d5_agent"},
                {"from": "d5_agent", "to": "d6_human"},
                {"from": "d6_human", "to": "d6_agent"},
                {"from": "d6_agent", "to": "d7_human"},
                {"from": "d7_human", "to": "d7_agent"},
                {"from": "d7_agent", "to": "d8_agent"},
            ],
        },
    },

    # ── 2. 鱼骨图分析（石川图）────────────────────────────────────────────────
    {
        "name":        "fishbone_analysis",
        "title":       "鱼骨图分析（石川图）",
        "description": "6M并行分析（人/机/料/法/测/环），多Agent同时从6个维度识别问题原因，最终汇总根因",
        "icon":        "fishbone",
        "tags":        ["质量", "根因分析", "鱼骨图", "6M"],
        "content": {
            "nodes": [
                {"id": "problem_input",  "label": "问题描述输入",    "type": "human",  "position": {"x": 100,  "y": 300}},
                {"id": "agent_man",      "label": "人员因素分析",    "type": "agent",  "position": {"x": 400,  "y": 100}, "config": {"prompt": "从【人员(Man)】维度分析：技能缺失、操作不当、疲劳、培训不足等可能原因"}},
                {"id": "agent_machine",  "label": "设备因素分析",    "type": "agent",  "position": {"x": 400,  "y": 200}, "config": {"prompt": "从【设备(Machine)】维度分析：设备精度、磨损、维护保养、校准等可能原因"}},
                {"id": "agent_material", "label": "材料因素分析",    "type": "agent",  "position": {"x": 400,  "y": 300}, "config": {"prompt": "从【材料(Material)】维度分析：原材料质量、供应商、来料检验、储存条件等可能原因"}},
                {"id": "agent_method",   "label": "方法因素分析",    "type": "agent",  "position": {"x": 400,  "y": 400}, "config": {"prompt": "从【方法(Method)】维度分析：工艺参数、作业指导书、流程设计等可能原因"}},
                {"id": "agent_measure",  "label": "测量因素分析",    "type": "agent",  "position": {"x": 400,  "y": 500}, "config": {"prompt": "从【测量(Measurement)】维度分析：量具精度、测量方法、检验标准等可能原因"}},
                {"id": "agent_env",      "label": "环境因素分析",    "type": "agent",  "position": {"x": 400,  "y": 600}, "config": {"prompt": "从【环境(Environment)】维度分析：温湿度、清洁度、噪声、照明等可能原因"}},
                {"id": "join_node",      "label": "汇总节点",        "type": "data",   "position": {"x": 700,  "y": 300}},
                {"id": "summary_agent",  "label": "根因汇总与排序",  "type": "agent",  "position": {"x": 900,  "y": 300}, "config": {"prompt": "综合6M分析结果，按影响程度排序，输出主要根因列表和优先处理建议"}},
            ],
            "connections": [
                {"from": "problem_input",  "to": "agent_man"},
                {"from": "problem_input",  "to": "agent_machine"},
                {"from": "problem_input",  "to": "agent_material"},
                {"from": "problem_input",  "to": "agent_method"},
                {"from": "problem_input",  "to": "agent_measure"},
                {"from": "problem_input",  "to": "agent_env"},
                {"from": "agent_man",      "to": "join_node"},
                {"from": "agent_machine",  "to": "join_node"},
                {"from": "agent_material", "to": "join_node"},
                {"from": "agent_method",   "to": "join_node"},
                {"from": "agent_measure",  "to": "join_node"},
                {"from": "agent_env",      "to": "join_node"},
                {"from": "join_node",      "to": "summary_agent"},
            ],
        },
    },

    # ── 3. PDCA 循环 ─────────────────────────────────────────────────────────
    {
        "name":        "pdca_cycle",
        "title":       "PDCA 循环",
        "description": "P(计划)→D(执行)→C(检查)→A(处置) 持续改善循环，A 节点判断是否进入下一轮",
        "icon":        "pdca",
        "tags":        ["持续改善", "PDCA", "质量管理"],
        "content": {
            "nodes": [
                {"id": "p_human",     "label": "P 制定改善计划",    "type": "human",     "position": {"x": 100, "y": 200}},
                {"id": "p_agent",     "label": "P AI辅助计划制定",  "type": "agent",     "position": {"x": 100, "y": 350}, "config": {"prompt": "根据问题现状制定SMART改善目标、行动计划和成功指标"}},
                {"id": "d_human",     "label": "D 执行改善措施",    "type": "human",     "position": {"x": 400, "y": 200}},
                {"id": "d_agent",     "label": "D 执行监控",        "type": "agent",     "position": {"x": 400, "y": 350}, "config": {"prompt": "监控执行进度，识别执行偏差并提出调整建议"}},
                {"id": "c_human",     "label": "C 检查结果",        "type": "human",     "position": {"x": 700, "y": 200}},
                {"id": "c_agent",     "label": "C 效果评估",        "type": "agent",     "position": {"x": 700, "y": 350}, "config": {"prompt": "对比计划目标与实际结果，量化改善效果，识别差距"}},
                {"id": "a_human",     "label": "A 处置与标准化",    "type": "human",     "position": {"x": 1000, "y": 200}},
                {"id": "a_condition", "label": "目标是否达成？",    "type": "condition", "position": {"x": 1000, "y": 350}, "config": {"condition": "目标达成率 >= 80%"}},
                {"id": "a_std_agent", "label": "A 标准化输出",      "type": "agent",     "position": {"x": 1200, "y": 200}, "config": {"prompt": "将成功经验标准化，更新作业指导书和控制计划"}},
            ],
            "connections": [
                {"from": "p_human",     "to": "p_agent"},
                {"from": "p_agent",     "to": "d_human"},
                {"from": "d_human",     "to": "d_agent"},
                {"from": "d_agent",     "to": "c_human"},
                {"from": "c_human",     "to": "c_agent"},
                {"from": "c_agent",     "to": "a_human"},
                {"from": "a_human",     "to": "a_condition"},
                {"from": "a_condition", "to": "a_std_agent", "label": "是"},
                {"from": "a_condition", "to": "p_human",     "label": "否（下一轮）"},
            ],
        },
    },

    # ── 4. 5Why 根因分析 ──────────────────────────────────────────────────────
    {
        "name":        "five_why_analysis",
        "title":       "5Why 根因分析",
        "description": "连续追问5次'为什么'，逐层深挖根本原因，最终输出根因和改善建议",
        "icon":        "5why",
        "tags":        ["根因分析", "5Why", "质量工具"],
        "content": {
            "nodes": [
                {"id": "problem_input", "label": "收集问题描述",   "type": "human",  "position": {"x": 100,  "y": 200}},
                {"id": "why1_agent",    "label": "Why 1：现象原因", "type": "agent",  "position": {"x": 350,  "y": 200}, "config": {"prompt": "分析问题的直接原因（第1个Why），要求具体可验证"}},
                {"id": "why2_agent",    "label": "Why 2：深层原因", "type": "agent",  "position": {"x": 600,  "y": 200}, "config": {"prompt": "针对Why1的原因继续追问为什么（第2个Why）"}},
                {"id": "why3_agent",    "label": "Why 3：系统原因", "type": "agent",  "position": {"x": 850,  "y": 200}, "config": {"prompt": "针对Why2的原因继续追问为什么（第3个Why）"}},
                {"id": "why4_agent",    "label": "Why 4：管理原因", "type": "agent",  "position": {"x": 1100, "y": 200}, "config": {"prompt": "针对Why3的原因继续追问为什么（第4个Why）"}},
                {"id": "why5_agent",    "label": "Why 5：根本原因", "type": "agent",  "position": {"x": 1350, "y": 200}, "config": {"prompt": "针对Why4的原因给出最终根本原因（第5个Why），并说明改善建议"}},
                {"id": "output_agent",  "label": "输出根因报告",   "type": "agent",  "position": {"x": 1600, "y": 200}, "config": {"prompt": "整理5Why分析链，输出根因报告和改善行动计划"}},
            ],
            "connections": [
                {"from": "problem_input", "to": "why1_agent"},
                {"from": "why1_agent",    "to": "why2_agent"},
                {"from": "why2_agent",    "to": "why3_agent"},
                {"from": "why3_agent",    "to": "why4_agent"},
                {"from": "why4_agent",    "to": "why5_agent"},
                {"from": "why5_agent",    "to": "output_agent"},
            ],
        },
    },

    # ── 5. FMEA 失效模式分析 ──────────────────────────────────────────────────
    {
        "name":        "fmea_analysis",
        "title":       "FMEA 失效模式分析",
        "description": "系统评估失效模式的严重度(S)/发生度(O)/探测度(D)，计算RPN优先排序改善项",
        "icon":        "fmea",
        "tags":        ["质量", "FMEA", "风险分析", "预防"],
        "content": {
            "nodes": [
                {"id": "function_agent",  "label": "识别功能与要求",   "type": "agent",  "position": {"x": 100,  "y": 200}, "config": {"prompt": "识别分析对象的功能和性能要求，建立功能清单"}},
                {"id": "failure_agent",   "label": "枚举失效模式",      "type": "agent",  "position": {"x": 350,  "y": 200}, "config": {"prompt": "针对每个功能列举可能的失效模式（What can go wrong?）"}},
                {"id": "effect_agent",    "label": "分析失效影响",      "type": "agent",  "position": {"x": 600,  "y": 200}, "config": {"prompt": "评估每个失效模式对系统、子系统和用户的影响，确定严重度S(1-10)"}},
                {"id": "cause_agent",     "label": "识别失效原因",      "type": "agent",  "position": {"x": 850,  "y": 200}, "config": {"prompt": "识别导致每个失效模式的原因，评估发生频率O(1-10)"}},
                {"id": "detect_agent",    "label": "评估探测度",        "type": "agent",  "position": {"x": 1100, "y": 200}, "config": {"prompt": "评估现有控制措施对每个失效模式的探测能力D(1-10)，D越大越难探测"}},
                {"id": "rpn_agent",       "label": "计算RPN并排序",     "type": "agent",  "position": {"x": 1350, "y": 200}, "config": {"prompt": "计算RPN=S×O×D，按RPN降序排列，识别高风险失效模式（RPN>100）"}},
                {"id": "action_human",    "label": "确认改善措施",      "type": "human",  "position": {"x": 1600, "y": 100}},
                {"id": "action_agent",    "label": "推荐改善行动",      "type": "agent",  "position": {"x": 1600, "y": 300}, "config": {"prompt": "针对高RPN项推荐具体改善措施，预测改善后的S/O/D值"}},
            ],
            "connections": [
                {"from": "function_agent",  "to": "failure_agent"},
                {"from": "failure_agent",   "to": "effect_agent"},
                {"from": "effect_agent",    "to": "cause_agent"},
                {"from": "cause_agent",     "to": "detect_agent"},
                {"from": "detect_agent",    "to": "rpn_agent"},
                {"from": "rpn_agent",       "to": "action_human"},
                {"from": "rpn_agent",       "to": "action_agent"},
            ],
        },
    },

    # ── 6. A3 问题报告 ────────────────────────────────────────────────────────
    {
        "name":        "a3_report",
        "title":       "A3 问题报告",
        "description": "按A3标准格式（背景/现状/目标/根因/对策/计划/效果/巩固）结构化输出完整问题报告",
        "icon":        "a3",
        "tags":        ["精益", "A3", "问题报告", "丰田方法"],
        "content": {
            "nodes": [
                {"id": "bg_agent",      "label": "① 背景与重要性",   "type": "agent",  "position": {"x": 100,  "y": 100}, "config": {"prompt": "描述问题的业务背景、为什么此问题值得解决、与战略目标的关联"}},
                {"id": "status_agent",  "label": "② 现状分析",       "type": "agent",  "position": {"x": 100,  "y": 300}, "config": {"prompt": "用数据描述当前状况，包括问题发生频率、影响范围、趋势图表描述"}},
                {"id": "target_human",  "label": "③ 确定目标",       "type": "human",  "position": {"x": 400,  "y": 100}},
                {"id": "target_agent",  "label": "③ 目标建议",       "type": "agent",  "position": {"x": 400,  "y": 300}, "config": {"prompt": "提出SMART改善目标，包括量化指标、时间节点和责任人建议"}},
                {"id": "root_agent",    "label": "④ 根因分析",       "type": "agent",  "position": {"x": 700,  "y": 200}, "config": {"prompt": "使用5Why和鱼骨图分析，找出根本原因，区分直接原因和系统性原因"}},
                {"id": "counter_agent", "label": "⑤ 制定对策",       "type": "agent",  "position": {"x": 1000, "y": 200}, "config": {"prompt": "针对根因制定具体可行的对策，每条对策对应明确的责任人和完成时间"}},
                {"id": "plan_human",    "label": "⑥ 执行计划",       "type": "human",  "position": {"x": 1300, "y": 100}},
                {"id": "plan_agent",    "label": "⑥ 计划优化",       "type": "agent",  "position": {"x": 1300, "y": 300}, "config": {"prompt": "整理行动计划甘特图（文字版），包括里程碑节点和资源需求"}},
                {"id": "effect_agent",  "label": "⑦ 效果确认",       "type": "agent",  "position": {"x": 1600, "y": 100}, "config": {"prompt": "定义效果验证方法和成功判定标准"}},
                {"id": "sustain_agent", "label": "⑧ 巩固与推广",     "type": "agent",  "position": {"x": 1600, "y": 300}, "config": {"prompt": "提出标准化措施、经验推广计划和防止反弹的控制方法"}},
                {"id": "final_agent",   "label": "输出完整A3报告",   "type": "agent",  "position": {"x": 1900, "y": 200}, "config": {"prompt": "整合以上所有输出，生成完整的A3问题报告（Markdown格式），包含所有8个区块"}},
            ],
            "connections": [
                {"from": "bg_agent",      "to": "status_agent"},
                {"from": "bg_agent",      "to": "target_human"},
                {"from": "status_agent",  "to": "target_agent"},
                {"from": "target_human",  "to": "root_agent"},
                {"from": "target_agent",  "to": "root_agent"},
                {"from": "root_agent",    "to": "counter_agent"},
                {"from": "counter_agent", "to": "plan_human"},
                {"from": "counter_agent", "to": "plan_agent"},
                {"from": "plan_human",    "to": "effect_agent"},
                {"from": "plan_agent",    "to": "effect_agent"},
                {"from": "effect_agent",  "to": "sustain_agent"},
                {"from": "sustain_agent", "to": "final_agent"},
            ],
        },
    },
]


# ── 种子写入函数 ────────────────────────────────────────────────────────────────

def seed_engineering_skills() -> None:
    """
    将 6 个工程框架技能写入 app.skills 表。
    ON CONFLICT(name) DO NOTHING — 幂等安全，重启不会重复创建。
    """
    import json as _json
    try:
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                for skill in _SKILLS:
                    gid = _gid(skill["name"])
                    cur.execute("""
                        INSERT INTO app.skills
                            (gid, name, title, description, skill_type, scope,
                             status, is_system, content, icon, tags,
                             sort_order, is_pinned, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, 'canvas', 'global',
                                'active', TRUE, %s, %s, %s,
                                %s, FALSE, NOW(), NOW())
                        ON CONFLICT (name) DO NOTHING
                    """, (
                        gid,
                        skill["name"],
                        skill["title"],
                        skill["description"],
                        _json.dumps(skill["content"], ensure_ascii=False),
                        skill.get("icon", ""),
                        _json.dumps(skill.get("tags", []), ensure_ascii=False),
                        _SKILLS.index(skill) + 100,   # sort_order 从100开始，避免与用户自定义冲突
                    ))
            conn.commit()
        logger.info(f"[EngineeringSkills] 种子数据写入完成（{len(_SKILLS)} 个技能，已存在的跳过）")
    except Exception as e:
        logger.warning(f"[EngineeringSkills] 种子数据写入失败（跳过）: {e}")
