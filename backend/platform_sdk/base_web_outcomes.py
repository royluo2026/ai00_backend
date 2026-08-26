"""Public Python boundary for reviewed Base-owned legacy Web outcomes.

Capability Providers use this module instead of reaching into the HTTP router
package.  The compatibility routers remain the single implementation while
Base service extraction can proceed independently of Gateway consumers.
"""
from backend.routers.grants import GrantBody, create_grant, delete_grant, list_grants
from backend.routers.notifications import get_prefs, update_prefs
from backend.routers.org import SyncFromFeishuBody, list_teams as list_org_teams, sync_from_feishu
from backend.routers.plugins import list_plugins
from backend.routers.self_annotations import (
    SelfAnnotationBody,
    get_annotation,
    get_batch as get_annotation_batch,
    get_list as list_annotations,
    upsert_annotation,
)
from backend.routers.teams import list_teams
from backend.routers.users import AssignRoleBody, assign_role, get_me, list_users, search_users
from backend.routers.views import (
    CreateViewBody,
    UpdateViewBody,
    copy_view,
    create_view,
    delete_view,
    list_views,
    update_view,
)

__all__ = [
    "AssignRoleBody", "CreateViewBody", "GrantBody", "SelfAnnotationBody",
    "SyncFromFeishuBody", "UpdateViewBody", "assign_role", "copy_view",
    "create_grant", "create_view", "delete_grant", "delete_view",
    "get_annotation", "get_annotation_batch", "get_me", "get_prefs",
    "list_annotations", "list_grants", "list_org_teams", "list_plugins",
    "list_teams", "list_users", "list_views", "search_users",
    "sync_from_feishu", "update_prefs", "update_view", "upsert_annotation",
]
