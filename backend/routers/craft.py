"""
backend/routers/craft.py
──────────────────────────
工艺 BOP API（V1 废弃）

V1 表（work_plans / sections / operation_flat）已在 schema 迁移中删除。
保留 router 对象以兼容 main.py import，所有端点已移除。
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/craft", tags=["craft"])
