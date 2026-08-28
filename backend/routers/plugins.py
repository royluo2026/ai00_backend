"""
backend/routers/plugins.py
──────────────────────────
插件管理 API（网页版，提供 Electron 插件接口的对等实现）
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.base.plugin_inventory import list_installed_plugins
from backend.routers.deps import build_profile, get_current_user
from backend.plugin_platform.service import PluginLifecycleError, PluginPlatformService, _tenant_for_user

router = APIRouter(prefix="/api/plugin", tags=["plugin"])


@router.get("/list")
def list_plugins(current_user: dict = Depends(get_current_user)):
    return list_installed_plugins()


class _ClosedBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PluginInstallBody(_ClosedBody):
    plugin_id: str
    release_version: str
    release_sha256: str
    requested_grants: list[str]
    idempotency_key: str


class PluginUninstallBody(_ClosedBody):
    expected_revision: int
    retain_tenant_data: bool
    idempotency_key: str


def _error(exc: PluginLifecycleError) -> HTTPException:
    status = {"invalid_input": 422, "revision_conflict": 409, "resource_not_found": 404,
              "release_not_verified": 409, "already_installed": 409}.get(exc.code, 400)
    return HTTPException(status, {"code": exc.code, "message": str(exc)})


def _trusted_lifecycle_actor(current_user: dict) -> dict[str, str]:
    """Normalize the authenticated Base user before the REST adapter reaches lifecycle state."""
    profile = build_profile(current_user)
    if "system.plugin.manage" not in set(profile.get("permissions", ())):
        raise HTTPException(status_code=403, detail="system.plugin.manage permission required")
    return {"gid": str(profile["gid"]), "tenant_gid": _tenant_for_user(profile)}


@router.post("/install")
def install_plugin(body: PluginInstallBody, current_user: dict = Depends(get_current_user)):
    try:
        actor = _trusted_lifecycle_actor(current_user)
        return {"success": True, "data": PluginPlatformService().request_install(
            actor=actor, command=body.model_dump(),
        )}
    except PluginLifecycleError as exc:
        raise _error(exc) from exc


@router.delete("/uninstall/{plugin_id}")
def uninstall_plugin(plugin_id: str, body: PluginUninstallBody, current_user: dict = Depends(get_current_user)):
    try:
        actor = _trusted_lifecycle_actor(current_user)
        return {"success": True, "data": PluginPlatformService().transition_uninstall(
            actor=actor, command={"plugin_id": plugin_id, **body.model_dump()},
        )}
    except PluginLifecycleError as exc:
        raise _error(exc) from exc
