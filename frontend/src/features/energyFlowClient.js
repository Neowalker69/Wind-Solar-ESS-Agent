import { resolveStationToken } from "./stationAuthClient.js";
import { buildEnergyHistoryQuery, mapTelemetrySeries } from "./digitalTwinAdapters.js";

const METRICS = "pv_power,wind_power,charge_power,discharge_power,load_power,grid_power,power_kw,soc";

async function headers(signal, fetchImpl) {
  const token = sessionStorage.getItem("station.accessToken")
    || await resolveStationToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readStationEnvelope(response) {
  const body = await response.json().catch(() => ({ message: `Station API HTTP ${response.status}` }));
  if (!response.ok || body.code !== 0) throw new Error(body.message || `Station API HTTP ${response.status}`);
  return body.data;
}

export async function loadEnergyHistory(range, scope, signal, fetchImpl = fetch) {
  const query = buildEnergyHistoryQuery(range, scope);
  const response = await fetchImpl(`/api/v1/telemetry/history?${query}`, {
    headers: await headers(signal, fetchImpl),
    signal,
  });
  const data = await readStationEnvelope(response);
  return mapTelemetrySeries(data.series || []);
}

export async function loadLatestEnergyPoint(scope, signal, fetchImpl = fetch) {
  const query = new URLSearchParams({ device_id: scope || "station", metrics: METRICS });
  const response = await fetchImpl(`/api/v1/telemetry/realtime?${query}`, {
    headers: await headers(signal, fetchImpl),
    signal,
  });
  const data = await readStationEnvelope(response);
  return mapTelemetrySeries(data.items || []);
}
