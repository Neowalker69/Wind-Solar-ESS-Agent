from apps.api_gateway.routers.front_router import route_intent
from apps.api_gateway.services.run_dispatcher import RunDispatcher
from apps.tool_gateway.services.tool_dispatcher import ToolDispatcher
from packages.data_model.registry import DataModelRegistry, default_lab_model
from packages.harness_common.schemas.intent import IntentDecision, RouterPath
from packages.harness_common.schemas.evidence import EvidenceRecord
from packages.memory.miner import mine_episodic_candidate
from packages.memory.service import MemoryService
from packages.plugins.opcua_connector.tools import read_node, tool_definitions
from packages.replay.service import ReplayService
from packages.storage.repositories.traces import TraceRepository
from packages.workflow.diagnosis_graph import run_diagnosis_graph


class LocalP0Harness:
    """Small local business-flow orchestrator for tests and demos.

    This deliberately uses deterministic local adapters and does not download
    models or contact external OPC UA servers.
    """

    def __init__(self) -> None:
        self.data_models = DataModelRegistry()
        self.data_models.register(default_lab_model())
        self.data_models.activate("opcua_lab_model", "0.1.0", site_id="opcua_lab")
        self.traces = TraceRepository()
        self.dispatcher = RunDispatcher(traces=self.traces)
        self.tools = ToolDispatcher()
        for tool in tool_definitions():
            handler = read_node if tool.name == "opcua_read_node" else lambda payload, name=tool.name: {"tool": name, "status": "ok"}
            self.tools.register(tool, handler)
        self.memory = MemoryService()
        self.replay = ReplayService(self.traces)

    def query_asset_status(self, *, asset_id: str) -> dict:
        intent = IntentDecision(
            intent_decision_id="intent_local_status",
            session_id="session_local",
            trace_id="trace_local",
            user_turn_hash="hash_local",
            intent_id="data.query",
            intent_label="数据查询",
            intent_family="data",
            confidence=1.0,
            router_path=RouterPath.RULE,
            normalized_user_turn=f"查询 {asset_id} 状态",
        )
        route = route_intent(intent, idempotency_key=f"local:{asset_id}:status")
        run = self.dispatcher.dispatch(route)
        mapping = self.data_models.node_for_signal(site_id="opcua_lab", asset_id=asset_id, signal_name="status")
        tool_result = self.tools.execute(
            "opcua_read_node",
            {"node_id": mapping.node_id, "mock_value": "OK"},
            run_id=run.run_id,
            trace_id=intent.trace_id,
        )
        evidence = EvidenceRecord(
            evidence_id=tool_result["evidence_id"], run_id=run.run_id, trace_id=intent.trace_id,
            source_type="telemetry", source_ref=f"opcua://{mapping.node_id}",
            data={"source_system": "opcua", "source_resource_type": "telemetry", "content_hash": f"sha256:{tool_result['evidence_id']}", "snapshot": {"asset_id": asset_id, "metric": "status", "status": tool_result["observation"].get("value", "OK")}},
        )
        final = run_diagnosis_graph(run.run_id, [evidence])["final"]
        memory = self.memory.create_candidate(mine_episodic_candidate(run.run_id, intent.trace_id, final["evidence_ids"]))
        replay = self.replay.record_replay(run.run_id, final)
        return {"run": run, "tool_result": tool_result, "final": final, "memory": memory, "replay": replay}
