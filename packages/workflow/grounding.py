from __future__ import annotations

from collections import defaultdict
from typing import Any

from packages.harness_common.schemas.evidence import EvidenceQuality, EvidenceRecord


_NO_DATA_STATUSES = {"no_data", "failed"}
_FACT_KEYS = ("asset_id", "device_id", "metric", "metric_key", "value", "unit", "status", "alarm_uuid", "alarm_id", "severity", "root_cause", "cause", "fact_time", "time", "timestamp")


def evaluate_diagnosis_evidence(run_id: str, records: list[EvidenceRecord]) -> dict[str, Any]:
    accepted: list[EvidenceRecord] = []
    rejected: list[dict[str, str]] = []
    facts: list[dict[str, Any]] = []
    for record in records:
        reason = _rejection_reason(run_id, record)
        if reason:
            rejected.append({"evidence_id": record.evidence_id, "reason": reason})
            continue
        extracted = _extract_facts(record)
        if not extracted:
            rejected.append({"evidence_id": record.evidence_id, "reason": "diagnostic_facts_missing"})
            continue
        accepted.append(record)
        facts.extend(extracted)
    conflicts = _conflicts(facts)
    return {
        "validated": bool(accepted) and not conflicts,
        "evidence_ids": [record.evidence_id for record in accepted],
        "facts": facts,
        "conflicts": conflicts,
        "rejected": rejected,
    }


def render_grounded_summary(facts: list[dict[str, Any]]) -> str:
    rendered: list[str] = []
    for fact in facts:
        snapshot = fact["fact"]
        asset = snapshot.get("asset_id") or snapshot.get("device_id") or "未知设备"
        metric = snapshot.get("metric") or snapshot.get("metric_key")
        fact_time = fact.get("fact_time") or snapshot.get("fact_time") or snapshot.get("time") or snapshot.get("timestamp")
        time_suffix = f"（事实时间 {fact_time}）" if fact_time else ""
        if metric and "value" in snapshot:
            rendered.append(f"{asset} {metric}={snapshot['value']}{(' ' + str(snapshot['unit'])) if snapshot.get('unit') else ''}{time_suffix}")
        elif snapshot.get("alarm_uuid") or snapshot.get("alarm_id"):
            alarm_id = snapshot.get("alarm_uuid") or snapshot.get("alarm_id")
            rendered.append(f"{asset} 告警 {alarm_id}（{snapshot.get('severity') or '级别未知'}）{time_suffix}")
        elif snapshot.get("status"):
            rendered.append(f"{asset} 状态={snapshot['status']}{time_suffix}")
        elif snapshot.get("root_cause") or snapshot.get("cause"):
            rendered.append(f"{asset} 证据所载原因={snapshot.get('root_cause') or snapshot.get('cause')}")
    return "已核验本次 Run 证据：" + "；".join(dict.fromkeys(rendered))


def _rejection_reason(run_id: str, record: EvidenceRecord) -> str | None:
    if record.run_id != run_id:
        return "evidence_wrong_run"
    if record.quality is not EvidenceQuality.GOOD:
        return "evidence_quality_not_allowed"
    data = record.data
    if not data.get("source_system") or not data.get("source_resource_type") or not data.get("content_hash"):
        return "evidence_provenance_incomplete"
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, (dict, list)) or not snapshot:
        return "evidence_snapshot_missing"
    if isinstance(snapshot, dict) and str(snapshot.get("status") or "").lower() in _NO_DATA_STATUSES:
        return "evidence_no_data"
    return None


def _extract_facts(record: EvidenceRecord) -> list[dict[str, Any]]:
    snapshot = record.data["snapshot"]
    if isinstance(snapshot, list):
        candidates = snapshot
    elif isinstance(snapshot.get("items"), list):
        candidates = snapshot["items"]
    elif isinstance(snapshot.get("points"), list) and snapshot["points"]:
        point = snapshot["points"][-1]
        candidates = [
            {
                **point,
                "asset_id": snapshot.get("asset_id") or snapshot.get("device_id"),
                "metric": snapshot.get("metric"),
                "unit": snapshot.get("unit") or point.get("unit"),
                "fact_time": point.get("fact_time") or point.get("time") or point.get("timestamp"),
            }
        ]
    else:
        candidates = [snapshot]
    result = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        fact = {key: candidate[key] for key in _FACT_KEYS if key in candidate and candidate[key] is not None}
        if any(key in fact for key in ("value", "status", "alarm_uuid", "alarm_id", "root_cause", "cause")):
            result.append({"evidence_id": record.evidence_id, "source_ref": record.source_ref, "fact_time": candidate.get("fact_time") or record.data.get("fact_time"), "fact": fact})
    return result


def _conflicts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in facts:
        fact = item["fact"]
        asset = str(fact.get("asset_id") or fact.get("device_id") or "")
        field = str(fact.get("metric") or fact.get("metric_key") or ("status" if "status" in fact else ""))
        if asset and field:
            fact_time = str(item.get("fact_time") or fact.get("fact_time") or fact.get("time") or fact.get("timestamp") or "current")
            grouped[(asset, f"{field}@{fact_time}")].append(item)
    conflicts = []
    for (asset, scoped_field), items in grouped.items():
        field, fact_time = scoped_field.rsplit("@", 1)
        values = {str(item["fact"].get("value", item["fact"].get("status"))) for item in items}
        if len(values) > 1:
            conflicts.append({"asset_id": asset, "field": field, "fact_time": fact_time, "values": sorted(values), "facts": items})
    return conflicts
