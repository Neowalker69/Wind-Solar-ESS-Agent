from apps.composition import AppContainer, get_container_dependency
from apps.security_dependencies import require_scope
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from packages.harness_common.schemas.api import api_success
from packages.harness_common.schemas.plugin import PluginInstallation, PluginRuntimeStatus
from packages.plugins.marketplace import catalog
from packages.plugins.supervisor import health_check
from packages.security.auth import AuthContext


http_router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


class PluginRollbackRequest(BaseModel):
    version: str


@http_router.get("/catalog")
async def plugin_catalog() -> dict:
    return api_success({"plugins": [plugin.model_dump(mode="json") for plugin in catalog()]})


@http_router.get("")
async def list_plugins(container: AppContainer = Depends(get_container_dependency)) -> dict:
    return api_success({"plugins": [plugin.model_dump(mode="json") for plugin in container.plugins.list_all()]})


@http_router.post("/install")
async def install_plugin(
    plugin: PluginInstallation,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("plugins:write")),
) -> dict:
    checked = health_check(plugin)
    container.plugins.upsert_by_idempotency_key(checked)
    return api_success(checked.model_dump(mode="json"))


@http_router.post("/{plugin_id}/{version}/enable")
async def enable_plugin(
    plugin_id: str,
    version: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("plugins:write")),
) -> dict:
    return api_success(_update_status(container, plugin_id, version, PluginRuntimeStatus.READY).model_dump(mode="json"))


@http_router.post("/{plugin_id}/{version}/disable")
async def disable_plugin(
    plugin_id: str,
    version: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("plugins:write")),
) -> dict:
    container.plugin_process_supervisor.stop(plugin_id, version)
    disabled = _update_status(
        container,
        plugin_id,
        version,
        PluginRuntimeStatus.DISABLED,
    ).model_copy(update={"runtime_pid": None, "health": {"healthy": False}})
    container.plugins.create(disabled)
    return api_success(disabled.model_dump(mode="json"))


@http_router.post("/{plugin_id}/{version}/activate")
async def activate_plugin(
    plugin_id: str,
    version: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("plugins:write")),
) -> dict:
    plugin = _require(container, plugin_id, version)
    active = container.plugin_process_supervisor.activate(plugin)
    container.plugins.create(active)
    container.plugin_version_router.activate_default(plugin_id, version)
    return api_success(active.model_dump(mode="json"))


@http_router.post("/{plugin_id}/rollback")
async def rollback_plugin(
    plugin_id: str,
    payload: PluginRollbackRequest,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("plugins:write")),
) -> dict:
    _require(container, plugin_id, payload.version)
    container.plugin_version_router.rollback(plugin_id, payload.version)
    return api_success({"plugin_id": plugin_id, "active_version": payload.version})


@http_router.delete("/{plugin_id}/{version}")
async def delete_plugin(
    plugin_id: str,
    version: str,
    container: AppContainer = Depends(get_container_dependency),
    _auth: AuthContext = Depends(require_scope("plugins:write")),
) -> dict:
    container.plugin_process_supervisor.stop(plugin_id, version)
    key = f"{plugin_id}:{version}"
    if not container.plugins.delete(key):
        raise HTTPException(status_code=404, detail="plugin_not_found")
    return api_success({"deleted": True, "plugin_id": plugin_id, "version": version})


def _update_status(container: AppContainer, plugin_id: str, version: str, status: PluginRuntimeStatus) -> PluginInstallation:
    plugin = _require(container, plugin_id, version)
    updated = plugin.model_copy(update={"runtime_status": status})
    container.plugins.create(updated)
    return updated


def _require(container: AppContainer, plugin_id: str, version: str) -> PluginInstallation:
    plugin = container.plugins.get_version(plugin_id, version)
    if plugin is None:
        raise HTTPException(status_code=404, detail="plugin_not_found")
    return plugin
