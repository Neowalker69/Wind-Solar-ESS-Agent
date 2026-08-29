from typing import Any

from packages.harness_common.schemas.tool_result import (
    ToolResult,
    ToolResultQuality,
    ToolResultStatus,
)
from packages.tool_registry.registry import ToolExecutionContext
from packages.workflow.data_quality import (
    RequiredEvidenceMissing,
    validate_requested_evidence_ids,
)


def _service(context: ToolExecutionContext, name: str) -> Any:
    service = context.services.get(name)
    if service is None:
        raise RuntimeError(f"capability_service_unavailable:{name}")
    return service


def _evidence(context: ToolExecutionContext) -> list[Any]:
    return _service(context, "evidence_repo").list_by_run_id(context.run.run_id)


def generate_evidence_bundle(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    evidence = _evidence(context)
    return {"run_id": context.run.run_id, "evidence_ids": [item.evidence_id for item in evidence], "evidence": [item.model_dump(mode="json") for item in evidence]}


def validate_evidence_completeness(_payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    missing = [] if _evidence(context) else ["evidence"]
    return {"complete": not missing, "missing": missing}


def rank_root_causes(_payload: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
    evidence = _evidence(context)
    candidates_by_cause: dict[str, dict[str, Any]] = {}
    for record in evidence:
        snapshot = record.data.get("snapshot")
        if not isinstance(snapshot, dict):
            continue
        for signal in _causal_signals(snapshot):
            cause = signal["cause"]
            candidate = candidates_by_cause.setdefault(
                cause,
                {
                    "cause": cause,
                    "supporting_evidence_ids": [],
                    "alarm_ids": [],
                    "scenario_ids": [],
                },
            )
            _append_unique(
                candidate["supporting_evidence_ids"],
                record.evidence_id,
            )
            _append_unique(candidate["alarm_ids"], signal.get("alarm_id"))
            _append_unique(
                candidate["scenario_ids"],
                signal.get("scenario_id"),
            )
    candidates = list(candidates_by_cause.values())
    if not candidates:
        return ToolResult(
            status=ToolResultStatus.NO_DATA,
            data={
                "status": "insufficient_evidence",
                "candidates": [],
                "missing": ["causal_evidence"],
            },
            quality=ToolResultQuality.MISSING,
        )
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        data={"status": "supported", "candidates": candidates, "missing": []},
        quality=ToolResultQuality.GOOD,
    )


def _causal_signals(snapshot: dict[str, Any]) -> list[dict[str, str | None]]:
    signals: list[dict[str, str | None]] = []
    _append_causal_signal(signals, snapshot, snapshot)

    nested_snapshot = snapshot.get("snapshot")
    if isinstance(nested_snapshot, dict):
        _append_causal_signal(signals, nested_snapshot, snapshot)

    items = snapshot.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_snapshot = item.get("snapshot")
            if isinstance(item_snapshot, dict):
                _append_causal_signal(signals, item_snapshot, item)
    return signals


def _append_causal_signal(
    signals: list[dict[str, str | None]],
    causal_data: dict[str, Any],
    source_data: dict[str, Any],
) -> None:
    cause = causal_data.get("root_cause") or causal_data.get("cause")
    if not cause:
        return
    signals.append(
        {
            "cause": str(cause),
            "alarm_id": _optional_text(
                source_data.get("alarm_uuid") or source_data.get("alarm_id")
            ),
            "scenario_id": _optional_text(causal_data.get("scenario_id")),
        }
    )


def _append_unique(values: list[str], value: Any) -> None:
    normalized = _optional_text(value)
    if normalized is not None and normalized not in values:
        values.append(normalized)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def create_work_order_draft(payload: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
    records = _evidence(context)
    evidence_ids = list(payload.get("evidence_ids") or [item.evidence_id for item in _evidence(context)])
    asset_id = str(payload.get("asset_id") or context.run.runtime_context.get("selected_asset_id") or "unknown")
    if not evidence_ids:
        return ToolResult(
            status=ToolResultStatus.NO_DATA,
            data={"status": "blocked", "missing": ["evidence"]},
            quality=ToolResultQuality.MISSING,
        )
    try:
        validate_requested_evidence_ids(records, evidence_ids)
    except RequiredEvidenceMissing as exc:
        return ToolResult(
            status=ToolResultStatus.NO_DATA,
            data={"status": "blocked", "missing": [str(exc)]},
            quality=ToolResultQuality.MISSING,
        )
    workflow = _service(context, "durable_workflows").submit(
        "work_order_draft",
        run_id=context.run.run_id,
        normalized_input={"evidence_ids": evidence_ids, "asset_id": asset_id},
        idempotency_key=f"capability:workorder:{context.run.run_id}:{','.join(evidence_ids)}",
    )
    data = workflow.model_dump(mode="json")
    return ToolResult(
        status=(
            ToolResultStatus.SUCCESS
            if data["status"] == "completed"
            else ToolResultStatus.NO_DATA
        ),
        data=data,
        quality=(
            ToolResultQuality.GOOD
            if data["status"] == "completed"
            else ToolResultQuality.MISSING
        ),
    )
