import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from apps.composition import container
from apps.http_contracts import install_http_contracts
from apps.api_gateway.routers import agent, channel_feishu, context_snapshots, digital_twin, evidence, front_router, intent_router, memories, plugins, reflections, resources, runs, sessions, skills
from apps.tool_gateway.routers import tools
from packages.harness_common.schemas.api import api_success
from packages.observability.metrics import GLOBAL_METRICS
from packages.observability.langfuse_sink import (
    FORMAL_RUNTIME_TRACE_SOURCE,
    FORMAL_RUNTIME_VERSION,
)
from packages.agent_runtime_rpc.server import create_agent_runtime_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("CONTROL_RUNTIME_SHARED_SECRET"):
        raise RuntimeError("CONTROL_RUNTIME_SHARED_SECRET is required")
    runtime_server = create_agent_runtime_server(container)
    bind_address = os.getenv("AGENT_RUNTIME_GRPC_BIND", "0.0.0.0:50051")
    port = runtime_server.add_insecure_port(bind_address)
    if port == 0:
        raise RuntimeError(f"agent_runtime_grpc_bind_failed:{bind_address}")
    await runtime_server.start()
    app.state.agent_runtime_server = runtime_server
    try:
        yield
    finally:
        container.plugin_process_supervisor.close_all()
        await runtime_server.stop(grace=5)


app = FastAPI(title="Agent Harness API Gateway", lifespan=lifespan)
install_http_contracts(app, component="api_gateway", container=container)


@app.middleware("http")
async def mark_legacy_agent_api_deprecated(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/agent/"):
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Wed, 30 Sep 2026 00:00:00 GMT"
        response.headers["Link"] = '</api/v1/sessions>; rel="successor-version"'
    return response

app.include_router(channel_feishu.http_router)
app.include_router(agent.http_router)
app.include_router(digital_twin.http_router)
app.include_router(context_snapshots.http_router)
app.include_router(intent_router.http_router)
app.include_router(front_router.http_router)
app.include_router(runs.http_router)
app.include_router(sessions.http_router)
app.include_router(resources.http_router)
app.include_router(evidence.http_router)
app.include_router(memories.http_router)
app.include_router(skills.http_router)
app.include_router(plugins.http_router)
app.include_router(reflections.http_router)
app.include_router(tools.http_router)


@app.get("/api/v1/gateway/health")
async def health() -> dict:
    return api_success(
        {
            "status": "ok",
            "component": "api_gateway",
            "model_provider": {
                "provider": os.environ["AGENT_HARNESS_MODEL_PROVIDER"],
                "model": container.model_router.default_model_id,
            },
            "observability": {
                "mode": os.getenv("AGENT_HARNESS_OBSERVABILITY", "local").lower(),
                "sink_enabled": container.langfuse_runtime_sink.enabled,
                "trace_source": FORMAL_RUNTIME_TRACE_SOURCE,
                "runtime_version": FORMAL_RUNTIME_VERSION,
                "demo_export_enabled": False,
            },
        }
    )


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return GLOBAL_METRICS.render_prometheus()
