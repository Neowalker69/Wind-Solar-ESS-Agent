from dataclasses import dataclass
import re
from typing import Any

from packages.tool_registry.registry import ToolExecutionContext


_ASSET_REFERENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:A[-_ ]?0?(?:[1-9]|[12]\d|3[0-2])|(?:PCS|PACK|CELL|STK|CLU)[-_ ]?\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_CHINESE_CONTAINER_REFERENCE_PATTERN = re.compile(
    r"(?<!\d)([1-9]|[12]\d|3[0-2])\s*号\s*(?:储能)?(?:集装箱|舱|设备)"
)
_BROAD_QUERY_MARKERS = (
    "总体",
    "整体",
    "全场",
    "全站",
    "整个场站",
    "所有设备",
    "全部设备",
    "设备清单",
    "系统概况",
    "overall",
    "all devices",
    "all assets",
    "site-wide",
)


@dataclass(frozen=True, slots=True)
class IndustrialQueryScope:
    asset_id: str | None = None
    station_id: str | None = None


def resolve_query_scope(
    payload: dict[str, Any],
    context: ToolExecutionContext,
) -> IndustrialQueryScope:
    """Apply entity filters only when the current user turn names that entity."""
    query = _user_query(payload)
    runtime_context = context.run.runtime_context
    attributes = runtime_context.get("attributes") or {}
    station_id = str(payload.get("station_id") or attributes.get("trusted_site_id") or "")
    requested_asset = str(payload.get("asset_id") or "")
    selected_asset = str(runtime_context.get("selected_asset_id") or "")

    # Direct tool/API calls without a user query treat explicit parameters as authoritative.
    if not query:
        if requested_asset or selected_asset:
            return IndustrialQueryScope(asset_id=_resolve_asset(requested_asset or selected_asset, context))
        if payload.get("station_id"):
            return IndustrialQueryScope(station_id=station_id)
        return IndustrialQueryScope()

    for candidate in (requested_asset, selected_asset):
        if candidate and _reference_mentioned(query, candidate):
            return IndustrialQueryScope(asset_id=_resolve_asset(candidate, context))

    if station_id and _reference_mentioned(query, station_id):
        return IndustrialQueryScope(station_id=station_id)

    references = _asset_references(query)
    if references:
        return IndustrialQueryScope(asset_id=_resolve_asset(next(iter(references)), context))
    if is_broad_query(query):
        return IndustrialQueryScope()
    if selected_asset:
        return IndustrialQueryScope(asset_id=_resolve_asset(selected_asset, context))
    return IndustrialQueryScope()


def selected_asset_id(
    payload: dict[str, Any],
    context: ToolExecutionContext,
) -> str:
    asset_id = resolve_query_scope(payload, context).asset_id
    if asset_id is None:
        raise ValueError("asset_id_required")
    return asset_id


def _resolve_asset(asset_id: str, context: ToolExecutionContext) -> str:
    normalized = str(asset_id)
    station_api = context.services.get("station_api")
    resolver = getattr(station_api, "resolve_device_id", None)
    if callable(resolver):
        return str(resolver(normalized, request_id=context.run.run_id))
    return normalized


def _user_query(payload: dict[str, Any]) -> str:
    return str(payload.get("query") or payload.get("content") or payload.get("question") or "").strip()


def _reference_mentioned(query: str, reference: str) -> bool:
    if reference.casefold() in query.casefold():
        return True
    return bool(_asset_references(query) & _asset_references(reference))


def is_broad_query(query: str) -> bool:
    normalized = query.casefold()
    return any(marker in normalized for marker in _BROAD_QUERY_MARKERS)


def should_inherit_selected_asset(query: str, selected_asset_id: str) -> bool:
    if not selected_asset_id:
        return False
    references = _asset_references(query)
    if references:
        return _reference_mentioned(query, selected_asset_id)
    return not is_broad_query(query)


def explicit_asset_reference(query: str) -> str | None:
    """Return the normalized target only when the turn names one unique asset."""
    references = sorted(_asset_references(query))
    return references[0] if len(references) == 1 else None


def effective_target_asset_id(query: str, selected_asset_id: str) -> str | None:
    """Resolve the deterministic single-asset scope used by planning and tools."""
    explicit_reference = explicit_asset_reference(query)
    if explicit_reference:
        return explicit_reference
    if _asset_references(query):
        # Multi-asset turns must remain available to broader planning.
        return None
    if should_inherit_selected_asset(query, selected_asset_id):
        return selected_asset_id
    return None


def _asset_references(value: str) -> set[str]:
    references = {
        _normalize_asset_reference(match.group(0))
        for match in _ASSET_REFERENCE_PATTERN.finditer(value)
    }
    references.update(
        f"A-{int(match.group(1)):02d}"
        for match in _CHINESE_CONTAINER_REFERENCE_PATTERN.finditer(value)
    )
    return references


def _normalize_asset_reference(reference: str) -> str:
    compact = re.sub(r"[-_ ]", "", reference).upper()
    if compact.startswith("A"):
        return f"A-{int(compact[1:]):02d}"
    prefix = next(
        candidate
        for candidate in ("PACK", "CELL", "PCS", "STK", "CLU")
        if compact.startswith(candidate)
    )
    return f"{prefix}_{int(compact[len(prefix):]):02d}"


def require_station_api(context: ToolExecutionContext) -> Any:
    station_api = context.services.get("station_api")
    if station_api is None:
        raise RuntimeError("capability_service_unavailable:station_api")
    return station_api
