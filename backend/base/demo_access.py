"""Server-configured demo entitlement; never derived from request fields."""
import os


def has_relation_demo_access(user_gid: str, project_gid: str | None = None) -> bool:
    if os.getenv('TABLE_PREFIX') != 'test_' or os.getenv('AI00_DEPLOY_PROFILE') == 'production':
        return False
    configured_actor = os.getenv('AI00_DEMO_ACCOUNT_GID', '').strip()
    configured_project = os.getenv('AI00_DEMO_PROJECT_GID', '').strip()
    return bool(configured_actor and configured_project and str(user_gid) == configured_actor
                and (project_gid is None or str(project_gid) == configured_project))
