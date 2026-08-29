from packages.harness_common.schemas.plugin import ToolDefinition
from packages.observations.service import ObservationService
from packages.storage.repositories.evidence import EvidenceRepository


def _tool():
    return ToolDefinition(
        name="asset.get_asset",
        version="0.1.0",
        description="asset",
        plugin_id="asset",
        plugin_version="0.1.0",
    )


def test_authoritative_tool_result_preserves_provenance_and_hash():
    evidence_repo = EvidenceRepository()
    service = ObservationService(evidence_repo=evidence_repo)

    observation = service.capture_tool_observation(
        tool=_tool(),
        run_id="run-1",
        trace_id="trace-1",
        raw_observation={
            "tool_id": "asset.get_asset",
            "result": {
                "status": "success",
                "data": {"device_id": "PCS_07", "status": "warning"},
                "quality": "good",
                "source_refs": [
                    {
                        "source_system": "station_api",
                        "source_resource_type": "device",
                        "source_ref": "device:PCS_07",
                        "fact_time": "2026-07-19T09:00:00Z",
                        "upstream_trace_id": "station-trace-1",
                    }
                ],
            },
        },
    )

    evidence = evidence_repo.get(observation.evidence_id)
    assert evidence.source_type == "device"
    assert evidence.source_ref == "device:PCS_07"
    assert evidence.data["source_system"] == "station_api"
    assert evidence.data["upstream_trace_id"] == "station-trace-1"
    assert evidence.data["content_hash"].startswith("sha256:")


def test_no_data_result_creates_observation_without_fact_evidence():
    service = ObservationService()

    observation = service.capture_tool_observation(
        tool=_tool(),
        run_id="run-2",
        trace_id="trace-2",
        raw_observation={
            "tool_id": "asset.get_asset",
            "result": {
                "status": "no_data",
                "data": {"device_id": "missing"},
                "quality": "missing",
                "source_refs": [],
            },
        },
    )

    assert observation.evidence_id is None
