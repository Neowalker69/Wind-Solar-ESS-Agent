import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from packages.events.bus import EventBus, InMemoryEventBus
from packages.harness_common.schemas.evidence import EvidenceQuality, EvidenceRecord
from packages.harness_common.schemas.observation import ObservationRecord
from packages.harness_common.schemas.plugin import ToolDefinition
from packages.storage.repositories.evidence import EvidenceRepository
from packages.storage.repositories.observations import ObservationRepository


SENSITIVE_KEY_PARTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "health", "medical", "commercial")
SECRET_VALUE_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|api[_-]?key[:=]\S+)", re.IGNORECASE)


class ObservationService:
    def __init__(
        self,
        evidence_repo: EvidenceRepository | None = None,
        observation_repo: ObservationRepository | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.evidence_repo = evidence_repo or EvidenceRepository()
        self.observation_repo = observation_repo or ObservationRepository()
        self.event_bus = event_bus or InMemoryEventBus()

    def capture_tool_observation(
        self,
        *,
        tool: ToolDefinition,
        raw_observation: dict[str, Any],
        task_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        model_name: str | None = None,
        source_ref: str | None = None,
        duration_ms: int | None = None,
    ) -> ObservationRecord:
        observation_id = f"obs_{uuid4().hex}"
        extract_payload, redacted_fields = self._redact(raw_observation)
        evidence_id = None
        evidence_input = self._evidence_input(
            extract_payload,
            fallback_source_ref=source_ref
            or str(extract_payload.get("node_id", tool.name)),
        )
        if run_id and trace_id and evidence_input is not None:
            evidence = EvidenceRecord(
                evidence_id=f"ev_{uuid4().hex}",
                run_id=run_id,
                trace_id=trace_id,
                source_type=evidence_input["source_type"],
                source_ref=evidence_input["source_ref"],
                plugin_id=tool.plugin_id,
                plugin_version=tool.plugin_version,
                tool_name=tool.name,
                quality=evidence_input["quality"],
                data={
                    "observation_id": observation_id,
                    **evidence_input["data"],
                },
            )
            self.evidence_repo.create(evidence)
            evidence_id = evidence.evidence_id
        record = ObservationRecord(
            observation_id=observation_id,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            model_name=model_name,
            tool_name=tool.name,
            plugin_id=tool.plugin_id,
            plugin_version=tool.plugin_version,
            raw_snapshot_ref=f"observation://records/{observation_id}",
            extract_payload=extract_payload,
            evidence_id=evidence_id,
            redacted_fields=redacted_fields,
            metadata={"duration_ms": duration_ms, "sink": "observation_repository"},
        )
        self.observation_repo.create(record)
        self.event_bus.publish(run_id or observation_id, {"event_type": "ObservationCaptured", "observation_id": observation_id, "evidence_id": evidence_id})
        return record

    @staticmethod
    def _evidence_input(
        extract_payload: dict[str, Any],
        *,
        fallback_source_ref: str,
    ) -> dict[str, Any] | None:
        result = extract_payload.get("result")
        if not isinstance(result, dict):
            return {
                "source_type": "tool_observation",
                "source_ref": fallback_source_ref,
                "quality": (
                    EvidenceQuality.BAD
                    if extract_payload.get("quality") == "Bad"
                    else EvidenceQuality.GOOD
                ),
                "data": {"extract_payload": extract_payload},
            }
        if result.get("status") not in {"success", "partial"}:
            return None
        source_refs = result.get("source_refs")
        if not isinstance(source_refs, list) or not source_refs:
            return None
        provenance = source_refs[0]
        if not isinstance(provenance, dict):
            return None
        snapshot = result.get("data")
        canonical = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        quality = {
            "bad": EvidenceQuality.BAD,
            "uncertain": EvidenceQuality.UNCERTAIN,
        }.get(str(result.get("quality") or "").lower(), EvidenceQuality.GOOD)
        return {
            "source_type": str(
                provenance.get("source_resource_type") or "tool_observation"
            ),
            "source_ref": str(
                provenance.get("source_ref") or fallback_source_ref
            ),
            "quality": quality,
            "data": {
                "snapshot": snapshot,
                "source_system": provenance.get("source_system"),
                "source_resource_type": provenance.get("source_resource_type"),
                "fact_time": provenance.get("fact_time"),
                "observed_at": result.get("observed_at"),
                "upstream_trace_id": provenance.get("upstream_trace_id"),
                "query_window": provenance.get("query_window"),
                "aggregation": provenance.get("aggregation"),
                "content_hash": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            },
        }

    def _redact(self, value: Any, path: str = "$") -> tuple[Any, list[str]]:
        redacted_fields: list[str] = []
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}"
                if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
                    output[key] = "[REDACTED]"
                    redacted_fields.append(child_path)
                    continue
                output[key], child_redactions = self._redact(item, child_path)
                redacted_fields.extend(child_redactions)
            return output, redacted_fields
        if isinstance(value, list):
            items = []
            for index, item in enumerate(value):
                redacted_item, child_redactions = self._redact(item, f"{path}[{index}]")
                items.append(redacted_item)
                redacted_fields.extend(child_redactions)
            return items, redacted_fields
        if isinstance(value, str) and SECRET_VALUE_PATTERN.search(value):
            return "[REDACTED]", [path]
        return value, redacted_fields
