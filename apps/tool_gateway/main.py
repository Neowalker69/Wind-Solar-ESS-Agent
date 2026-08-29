from fastapi import FastAPI

from apps.composition import container
from apps.http_contracts import install_http_contracts
from apps.tool_gateway.routers.tools import http_router
from packages.harness_common.schemas.api import api_success

app = FastAPI(title="Agent Harness Tool Gateway")
install_http_contracts(app, component="tool_gateway", container=container)
app.include_router(http_router)


@app.get("/api/v1/tool-gateway/health")
async def health() -> dict:
    return api_success({"status": "ok", "component": "tool_gateway"})
