"""
packages/agent-plugin/agent_backend/routers/__init__.py
Agent+AI 插件路由入口 — 物理迁移完成，使用相对 import
"""
from .ai_chat import router as ai_chat_router
from .ai_audit import router as ai_audit_router
from .flows import router as flows_router
from .skills_v2 import router as skills_router


def get_routers():
    return [ai_chat_router, ai_audit_router, flows_router, skills_router]


OWNED_MODULES = {"ai_chat", "ai_audit", "flows", "skills_v2"}
