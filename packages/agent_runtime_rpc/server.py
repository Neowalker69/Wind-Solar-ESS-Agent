import grpc
import os

from apps.composition import AppContainer, build_container
from packages.agent_runtime_rpc.generated.agent_runtime.v1 import runtime_pb2_grpc
from packages.agent_runtime_rpc.service import AgentRuntimeServicer


def create_agent_runtime_server(container: AppContainer | None = None) -> grpc.aio.Server:
    """组装 Python Agent Runtime 的 gRPC 服务，不创建平行业务容器。"""

    server = grpc.aio.server()
    runtime_pb2_grpc.add_AgentRuntimeServicer_to_server(
        AgentRuntimeServicer(
            container or build_container(),
            required_transport_secret=os.getenv("CONTROL_RUNTIME_SHARED_SECRET"),
        ),
        server,
    )
    return server
