from .knowledge_entries_legacy import router as entries_router
from .knowledge_hub_legacy import router as hub_router

OWNED_MODULES = {"knowledge", "knowledge_hub"}


def get_routers():
    return [entries_router, hub_router]
