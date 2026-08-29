import { bessHealthLevel } from "./bessScenePresentation.js";

export const BESS_TELEMETRY_INTERVAL_MS = 5_000;
export const BESS_STALE_AFTER_MS = BESS_TELEMETRY_INTERVAL_MS * 3;
export const BESS_RUNTIME_HISTORY_LIMIT = 360;

export const BESS_TELEMETRY_METRICS = Object.freeze([
  "soc",
  "soh",
  "temperature",
  "power_kw",
  "fan_rpm",
  "status_code",
  "alarm_severity",
]);

export function buildBessTelemetrySubscription(deviceIds) {
  return {
    op: "subscribe",
    channel: "telemetry",
    params: {
      device_ids: [...deviceIds],
      metrics: [...BESS_TELEMETRY_METRICS],
      interval_ms: BESS_TELEMETRY_INTERVAL_MS,
    },
  };
}

export function createBessRuntimeOverview() {
  return {
    status: "loading",
    source: "agent_facts",
    updatedAt: null,
    error: "",
    deviceCount: 0,
    netPowerKw: null,
    chargingPowerKw: null,
    dischargingPowerKw: null,
    averageSoc: null,
    history: [],
  };
}

function newestTimestamp(current, candidate) {
  if (!candidate || Number.isNaN(Date.parse(candidate))) return current;
  if (!current || Number.isNaN(Date.parse(current))) return candidate;
  return Date.parse(candidate) > Date.parse(current) ? candidate : current;
}

export function applyBessTelemetrySnapshot(containers, points, now = Date.now()) {
  const pointsByDevice = new Map();
  points.forEach((point) => {
    if (!/^A-\d{2}$/.test(point?.device_id) || !Number.isFinite(point?.value)) return;
    const devicePoints = pointsByDevice.get(point.device_id) || new Map();
    devicePoints.set(point.metric_key, point);
    pointsByDevice.set(point.device_id, devicePoints);
  });

  return containers.map((container) => {
    const devicePoints = pointsByDevice.get(container.id);
    let observedAt = container.observedAt || null;
    devicePoints?.forEach((point) => {
      observedAt = newestTimestamp(observedAt, point.time);
    });
    const age = observedAt ? now - Date.parse(observedAt) : Number.POSITIVE_INFINITY;
    const valueFor = (metricKey, fallback) => devicePoints?.get(metricKey)?.value ?? fallback;
    const statusCode = valueFor("status_code", container.statusCode);
    const alarmSeverity = valueFor("alarm_severity", container.alarmSeverity);
    const soc = valueFor("soc", container.soc);
    const temp = valueFor("temperature", container.temp);

    return {
      ...container,
      soc,
      soh: valueFor("soh", container.soh),
      temp,
      power: valueFor("power_kw", container.power),
      fanRpm: valueFor("fan_rpm", container.fanRpm),
      statusCode,
      alarmSeverity,
      severity: bessHealthLevel({ statusCode, alarmSeverity, soc, temp }, container.severity),
      observedAt,
      dataState: age <= BESS_STALE_AFTER_MS ? "live" : "stale",
    };
  });
}

export function summarizeBessRuntimeSnapshot(points, previous = createBessRuntimeOverview(), pushedAt) {
  const byDevice = new Map();
  let updatedAt = previous.updatedAt;
  points.forEach((point) => {
    if (!/^A-\d{2}$/.test(point?.device_id) || !Number.isFinite(point?.value)) return;
    const device = byDevice.get(point.device_id) || {};
    device[point.metric_key] = point.value;
    byDevice.set(point.device_id, device);
    updatedAt = newestTimestamp(updatedAt, point.time);
  });

  const powers = [...byDevice.values()].map((device) => device.power_kw).filter(Number.isFinite);
  const socValues = [...byDevice.values()].map((device) => device.soc).filter(Number.isFinite);
  if (!powers.length && !socValues.length) return previous;

  const netPowerKw = powers.reduce((total, value) => total + value, 0);
  const dischargingPowerKw = powers.reduce((total, value) => total + Math.max(0, value), 0);
  const chargingPowerKw = powers.reduce((total, value) => total + Math.abs(Math.min(0, value)), 0);
  const averageSoc = socValues.length
    ? socValues.reduce((total, value) => total + value, 0) / socValues.length
    : previous.averageSoc;
  const timestamp = pushedAt && !Number.isNaN(Date.parse(pushedAt)) ? pushedAt : updatedAt;
  const historyPoint = {
    timestamp,
    netPowerMw: netPowerKw / 1000,
    dischargingPowerMw: dischargingPowerKw / 1000,
    chargingPowerMw: chargingPowerKw / 1000,
    averageSoc,
  };
  const history = previous.history.at(-1)?.timestamp === timestamp
    ? [...previous.history.slice(0, -1), historyPoint]
    : [...previous.history, historyPoint];

  return {
    status: "live",
    source: "agent_facts",
    updatedAt,
    error: "",
    deviceCount: byDevice.size,
    netPowerKw,
    chargingPowerKw,
    dischargingPowerKw,
    averageSoc,
    history: history.slice(-BESS_RUNTIME_HISTORY_LIMIT),
  };
}

export function markBessRuntimeOverviewStale(overview, now = Date.now()) {
  if (!overview.updatedAt) return overview;
  const age = now - Date.parse(overview.updatedAt);
  if (!Number.isFinite(age) || age <= BESS_STALE_AFTER_MS) return overview;
  return { ...overview, status: "stale" };
}

export function bessTelemetrySocketUrl(token, locationLike = globalThis.location) {
  const protocol = locationLike.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${locationLike.host}/ws?token=${encodeURIComponent(token)}`;
}
