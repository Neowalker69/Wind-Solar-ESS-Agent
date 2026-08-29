import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from apps.tool_gateway.services.tool_dispatcher import ToolExecutionContext, ToolUpstreamError
from packages.security.auth import Hs256JwtVerifier


NODE_ID_PATTERN = re.compile(r"^ns=\d+;s=([A-Za-z0-9_.:-]+)\.([A-Za-z0-9_]+)$")
METRIC_ALIASES = {
    "soc": "soc",
    "soh": "soh",
    "temperature": "temperature",
    "temperature_c": "temperature",
    "power": "active_power",
    "active_power": "active_power",
    "voltage": "voltage",
    "current": "current",
}


class StationApiError(ToolUpstreamError):
    def __init__(self, message: str, *, status_code: int, trace_id: str | None = None) -> None:
        super().__init__(message)
        self.error_code = message if message.startswith("station_api_") else "station_api_request_failed"
        self.status_code = status_code
        self.trace_id = trace_id


class StationApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        token_provider: Callable[[], str],
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider
        self.http = http_client or httpx.Client(timeout=timeout_seconds)

    def get_device(self, device_ref: str, *, request_id: str) -> tuple[dict[str, Any], str | None] | None:
        return self._get(f"/devices/{quote(device_ref, safe='')}", request_id=request_id, allow_not_found=True)

    def search_devices(self, query: str, *, request_id: str) -> tuple[list[dict[str, Any]], str | None]:
        response = self._get(
            "/devices/search",
            request_id=request_id,
            params={"q": query, "size": 100},
        )
        assert response is not None
        data, trace_id = response
        return list(data.get("items") or []), trace_id

    def resolve_device_id(self, device_ref: str, *, request_id: str) -> str:
        """Resolve a scene code (for example ``A-03``) to Station's primary key."""
        direct = self.get_device(device_ref, request_id=request_id)
        if direct is not None:
            return str(direct[0]["device_id"])
        devices, _trace_id = self.search_devices(device_ref, request_id=request_id)
        normalized = device_ref.casefold()
        for device in devices:
            candidates = (device.get("device_id"), device.get("code"), device.get("name"))
            if any(str(candidate or "").casefold() == normalized for candidate in candidates):
                return str(device["device_id"])
        return device_ref

    def realtime(self, device_id: str, metric: str, *, request_id: str) -> tuple[list[dict[str, Any]], str | None]:
        response = self._get(
            "/telemetry/realtime",
            request_id=request_id,
            params={"device_id": device_id, "metrics": metric},
        )
        assert response is not None
        data, trace_id = response
        return list(data.get("items") or []), trace_id

    def history(
        self,
        device_id: str,
        metric: str,
        *,
        start: str,
        end: str,
        request_id: str,
        interval: str = "5m",
        aggregation: str = "avg",
    ) -> tuple[list[dict[str, Any]], str | None]:
        response = self._get(
            "/telemetry/history",
            request_id=request_id,
            params={
                "device_id": device_id,
                "metrics": metric,
                "start": start,
                "end": end,
                "interval": interval,
                "aggregation": aggregation,
            },
        )
        assert response is not None
        data, trace_id = response
        return list(data.get("series") or []), trace_id

    def list_alarms(
        self,
        *,
        request_id: str,
        status: str | None = None,
        device_id: str | None = None,
        station_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"size": 100}
        if status:
            params["status"] = status
        if device_id:
            params["device_id"] = device_id
        if station_id:
            params["station_id"] = station_id
        response = self._get("/alarms", request_id=request_id, params=params)
        assert response is not None
        data, trace_id = response
        return list(data.get("items") or []), trace_id

    def get_alarm(
        self,
        alarm_id: str,
        *,
        request_id: str,
    ) -> tuple[dict[str, Any], str | None] | None:
        return self._get(
            f"/alarms/{quote(alarm_id, safe='')}",
            request_id=request_id,
            allow_not_found=True,
        )

    def events(
        self,
        *,
        request_id: str,
        device_id: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params = {
            key: value
            for key, value in {
                "device_id": device_id,
                "start": start,
                "end": end,
            }.items()
            if value
        }
        response = self._get("/events", request_id=request_id, params=params)
        assert response is not None
        data, trace_id = response
        return list(data.get("items") or []), trace_id

    def _get(
        self,
        path: str,
        *,
        request_id: str,
        params: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> tuple[dict[str, Any], str | None] | None:
        try:
            response = self.http.get(
                f"{self.base_url}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {self.token_provider()}",
                    "X-Request-ID": request_id,
                },
            )
        except httpx.HTTPError as exc:
            raise StationApiError("station_api_unavailable", status_code=502) from exc
        try:
            envelope = response.json()
        except ValueError as exc:
            raise StationApiError("station_api_invalid_json", status_code=response.status_code) from exc
        trace_id = envelope.get("trace_id")
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code >= 400 or envelope.get("code") != 0:
            raise StationApiError(
                str(envelope.get("message") or "station_api_request_failed"),
                status_code=response.status_code,
                trace_id=trace_id,
            )
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise StationApiError("station_api_invalid_envelope", status_code=response.status_code, trace_id=trace_id)
        return data, trace_id


class StationApiToolAdapter:
    def __init__(self, client: StationApiClient) -> None:
        self.client = client

    def execute_tool(self, payload: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
        node_id = str(payload["node_id"])
        match = NODE_ID_PATTERN.fullmatch(node_id)
        if not match:
            raise ValueError("invalid_station_node_id")
        device_ref, attribute = match.groups()
        request_id = context.trace_id or f"req_tool_{uuid4().hex}"
        device, upstream_trace_id = self._resolve_device(device_ref, request_id=request_id)
        device_id = str(device["device_id"])
        normalized_attribute = attribute.lower()
        if normalized_attribute == "status":
            return {
                "node_id": node_id,
                "device_id": device_id,
                "metric_key": "status",
                "value": device.get("status"),
                "quality": "Good",
                "adapter_type": "station_api",
                "upstream_trace_id": upstream_trace_id,
            }
        metric = METRIC_ALIASES.get(normalized_attribute)
        if not metric:
            raise ValueError("unsupported_station_metric")
        points, telemetry_trace_id = self.client.realtime(device_id, metric, request_id=request_id)
        if not points:
            raise ValueError("station_metric_not_found")
        point = points[0]
        return {
            "node_id": node_id,
            "device_id": device_id,
            "metric_key": metric,
            "value": point.get("value"),
            "quality": self._quality(point.get("quality")),
            "timestamp": point.get("time"),
            "adapter_type": "station_api",
            "upstream_trace_id": telemetry_trace_id,
        }

    def _resolve_device(self, device_ref: str, *, request_id: str) -> tuple[dict[str, Any], str | None]:
        direct = self.client.get_device(device_ref, request_id=request_id)
        if direct is not None:
            return direct
        devices, trace_id = self.client.search_devices(device_ref, request_id=request_id)
        normalized = device_ref.casefold()
        for device in devices:
            candidates = (device.get("device_id"), device.get("code"), device.get("name"))
            if any(str(candidate or "").casefold() == normalized for candidate in candidates):
                resolved = self.client.get_device(str(device["device_id"]), request_id=request_id)
                if resolved is not None:
                    return resolved
        raise ValueError("station_device_not_found")

    @staticmethod
    def _quality(value: Any) -> str:
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return "Uncertain"
        if numeric >= 192:
            return "Good"
        if numeric > 0:
            return "Uncertain"
        return "Bad"


def build_station_api_tool_adapter() -> StationApiToolAdapter | None:
    base_url = os.getenv("STATION_API_BASE_URL")
    if not base_url:
        return None
    static_token = os.getenv("STATION_API_TOKEN")
    if static_token:
        token_provider = lambda: static_token
    else:
        issuer = os.getenv("TOOL_GATEWAY_JWT_ISSUER")
        if not issuer:
            raise RuntimeError("TOOL_GATEWAY_JWT_ISSUER is required for Station API service authentication")
        verifier = Hs256JwtVerifier()
        token_provider = lambda: verifier.issue_dev_token(
            user_id="0",
            scopes=["tools:execute"],
            expires_in_seconds=300,
            role="operator",
            issuer=issuer,
            token_type="access",
        )
    timeout_seconds = float(os.getenv("STATION_API_TIMEOUT_SECONDS", "5"))
    return StationApiToolAdapter(
        StationApiClient(
            base_url,
            token_provider=token_provider,
            timeout_seconds=timeout_seconds,
        )
    )
