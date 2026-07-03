"""
backend/routers/_bop/__init__.py
─────────────────────────────────
合并所有子路由，对外暴露单一 router。
"""
from fastapi import APIRouter

from . import factory, versions, entries, staging, fork, templates, gbop, pbom, lifecycle

router = APIRouter()
for _sub in [factory, versions, entries, staging, fork, templates, gbop, pbom, lifecycle]:
    router.include_router(_sub.router)
