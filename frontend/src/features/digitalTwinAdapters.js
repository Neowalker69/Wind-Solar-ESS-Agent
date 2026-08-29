export const SOC_LEVELS = {
  normal: { label: "正常", color: "#25e678", gradient: "linear-gradient(90deg, #0ea56b, #25e678)" },
  warning: { label: "预警", color: "#ffb547", gradient: "linear-gradient(90deg, #c67716, #ffcc62)" },
  critical: { label: "严重", color: "#ff4d5e", gradient: "linear-gradient(90deg, #b91c2b, #ff4d5e)" },
  offline: { label: "离线", color: "#65758b", gradient: "linear-gradient(90deg, #465466, #65758b)" },
};

export const ENERGY_SERIES = [
  { key: "pvMw", label: "光伏发电", color: "#31c6f4", unit: "MW" },
  { key: "windMw", label: "风电发电", color: "#3b82f6", unit: "MW" },
  { key: "essChargeMw", label: "储能充电", color: "#8b5cf6", unit: "MW" },
  { key: "essDischargeMw", label: "储能放电", color: "#22c997", unit: "MW" },
  { key: "loadMw", label: "负荷", color: "#f5a623", unit: "MW" },
  { key: "socPct", label: "SOC", color: "#00e5ff", unit: "%", rightAxis: true },
];

const ENERGY_METRIC_FIELDS = {
  pv_power: "pvMw",
  wind_power: "windMw",
  charge_power: "essChargeMw",
  discharge_power: "essDischargeMw",
  load_power: "loadMw",
  grid_power: "gridMw",
  soc: "socPct",
};

const ENERGY_RANGE_CONFIG = {
  realtime: { milliseconds: 60 * 60_000, interval: "1m" },
  "6h": { milliseconds: 6 * 3_600_000, interval: "5m" },
  "24h": { milliseconds: 24 * 3_600_000, interval: "5m" },
  "7d": { milliseconds: 7 * 86_400_000, interval: "1h" },
  "30d": { milliseconds: 30 * 86_400_000, interval: "1h" },
};

export function buildEnergyHistoryQuery(range, scope, now = new Date()) {
  const config = ENERGY_RANGE_CONFIG[range] || ENERGY_RANGE_CONFIG["24h"];
  const end = new Date(now);
  const start = new Date(end.getTime() - config.milliseconds);
  return new URLSearchParams({
    device_id: scope || "station",
    metrics: Object.keys(ENERGY_METRIC_FIELDS).join(","),
    start: start.toISOString(),
    end: end.toISOString(),
    interval: config.interval,
    aggregation: "avg",
  });
}

export function mapTelemetrySeries(series) {
  const byTime = new Map();
  for (const item of series || []) {
    const field = ENERGY_METRIC_FIELDS[item.metric_key];
    const isBessPower = item.metric_key === "power_kw";
    if ((!field && !isBessPower) || !Number.isFinite(Date.parse(item.time))) continue;
    const timestamp = new Date(item.time).toISOString();
    const point = byTime.get(timestamp) || { timestamp };
    const value = Number(item.value);
    if (!Number.isFinite(value)) continue;
    if (isBessPower) {
      point.essChargeMw = Math.max(-value, 0) / 1000;
      point.essDischargeMw = Math.max(value, 0) / 1000;
    } else {
      point[field] = value;
    }
    byTime.set(timestamp, point);
  }
  return [...byTime.values()].sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
}

export function mergeEnergyPoints(current, incoming, limit = 3000) {
  const byTime = new Map(current.map((point) => [point.timestamp, point]));
  for (const point of incoming) byTime.set(point.timestamp, { ...byTime.get(point.timestamp), ...point });
  return [...byTime.values()]
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp))
    .slice(-limit);
}

export function socLevelFor(device, now = Date.now()) {
  const updatedAt = Date.parse(device?.updatedAt || "");
  const stale = Number.isFinite(updatedAt) && now - updatedAt > 30_000;
  if (!device || device.connectionState === "offline" || stale) return "offline";
  if (device.alarmLevel === "critical" || device.soc < 20) return "critical";
  if (device.alarmLevel === "warning" || device.soc < 50) return "warning";
  return "normal";
}

export function lodForDistance(distance) {
  if (distance > 80) return "compact";
  if (distance >= 35) return "standard";
  return "detail";
}

function labelPriority(item) {
  if (item.selected) return 500;
  if (item.hovered) return 450;
  if (item.level === "critical") return 400;
  if (item.level === "warning") return 300;
  if (item.level === "offline") return 100;
  return 200;
}

function rectanglesOverlap(left, right) {
  return left.x < right.x + right.width
    && left.x + left.width > right.x
    && left.y < right.y + right.height
    && left.y + left.height > right.y;
}

export function resolveSocLabelLayout(candidates, { maxVisible = 40, clusterDistance = 95 } = {}) {
  const items = new Map();
  const usable = candidates.filter((item) => !item.occluded || item.selected || item.level === "critical");
  if (usable.length >= 4 && usable.every((item) => item.distance >= clusterDistance)) {
    const socValues = usable.map((item) => Number(item.soc)).filter(Number.isFinite);
    const averageSoc = socValues.length ? Math.round(socValues.reduce((sum, value) => sum + value, 0) / socValues.length) : 0;
    for (const item of candidates) items.set(item.id, { visible: false, offsetX: 0, offsetY: 0 });
    return {
      items,
      cluster: {
        count: usable.length,
        averageSoc,
        alarmCount: usable.filter((item) => ["critical", "warning"].includes(item.level)).length,
      },
    };
  }

  const accepted = [];
  const sorted = [...usable].sort((left, right) => labelPriority(right) - labelPriority(left) || left.distance - right.distance);
  for (const item of sorted) {
    if (accepted.length >= maxVisible) {
      items.set(item.id, { visible: false, offsetX: 0, offsetY: 0 });
      continue;
    }
    const offsets = labelPriority(item) >= 400 ? [0, 64, -64, 128, -128] : labelPriority(item) >= 300 ? [0, 64, -64] : [0];
    const placement = offsets.map((offsetX) => ({ ...item, x: item.x + offsetX, offsetX })).find((candidate) => !accepted.some((placed) => rectanglesOverlap(candidate, placed)));
    if (!placement) {
      items.set(item.id, { visible: false, offsetX: 0, offsetY: 0 });
      continue;
    }
    accepted.push(placement);
    items.set(item.id, { visible: true, offsetX: placement.offsetX, offsetY: 0 });
  }
  for (const item of candidates) if (!items.has(item.id)) items.set(item.id, { visible: false, offsetX: 0, offsetY: 0 });
  return { items, cluster: null };
}

export function deviceAgentContext(container, alerts = []) {
  if (!container) return null;
  const stationDeviceId = container.stationDeviceId || container.id;
  return {
    device_id: stationDeviceId,
    soc: Number(container.soc),
    soh: Number(container.soh ?? Math.max(0, 98 - (100 - container.soc) * 0.05)),
    power_kw: Number(container.power ?? 0),
    temperature_c: Number(container.temp ?? 0),
    charge_state: container.power > 0 ? "discharging" : container.power < 0 ? "charging" : "standby",
    alarm_level: container.severity || "normal",
    alarm_ids: alerts.filter((alarm) => alarm.stationDeviceId === stationDeviceId || (!alarm.stationDeviceId && alarm.deviceId === container.id) || alarm.deviceId === stationDeviceId).map((alarm) => alarm.id || alarm.title),
    timestamp: container.updatedAt || new Date().toISOString(),
  };
}

export function buildAgentRequest(userInput, { container, alerts = [], range = "24h", stationId = "ess-station-01" } = {}) {
  const device = deviceAgentContext(container, alerts);
  return {
    client_message_id: globalThis.crypto?.randomUUID?.() || `msg_${Date.now()}`,
    user_input: userInput.trim(),
    node_id: device ? `ns=2;s=${device.device_id}.Status` : "ns=2;s=Station.Status",
    context: {
      site_id: stationId,
      site_name: stationId,
      time_range: range,
      selected_device: device,
    },
  };
}

export function unwrapEnvelope(payload) {
  if (payload?.error) {
    const error = new Error(payload.error.message || "Agent Gateway 请求失败");
    error.code = payload.error.code;
    error.traceId = payload.trace_id;
    throw error;
  }
  if (!payload || !("data" in payload)) throw new Error("Agent Gateway 返回了无效响应");
  return payload.data;
}

export function flattenTraceTree(tree) {
  const rows = [];
  const visit = (node, depth = 0, parentObservationId = null) => {
    if (!node) return;
    rows.push({
      observationId: String(node.id || `observation_${rows.length}`),
      parentObservationId,
      depth,
      kind: node.kind || "event",
      name: node.title || node.kind || "执行步骤",
      status: node.status === "ok" ? "success" : node.status || "success",
      summary: node.summary || "",
      durationMs: node.metrics?.duration_ms ?? null,
      totalTokens: node.metrics?.total_tokens ?? null,
    });
    for (const child of node.children || []) visit(child, depth + 1, String(node.id || "root"));
  };
  visit(tree?.root);
  return rows;
}

export function createRunEventState(runId) {
  return {
    runId,
    lastEventId: "0",
    status: "queued",
    message: null,
    error: null,
    externalObservability: null,
    observations: [],
    sceneActions: [],
    seenSequences: [],
  };
}

function orderObservations(observations) {
  const byParent = new Map();
  for (const observation of observations) {
    const parent = observation.parentObservationId || null;
    if (!byParent.has(parent)) byParent.set(parent, []);
    byParent.get(parent).push(observation);
  }
  const ordered = [];
  const seen = new Set();
  const visit = (parentId, depth = 0) => {
    for (const observation of byParent.get(parentId) || []) {
      if (seen.has(observation.observationId)) continue;
      seen.add(observation.observationId);
      ordered.push({ ...observation, depth });
      visit(observation.observationId, depth + 1);
    }
  };
  visit(null);
  for (const observation of observations) {
    if (!seen.has(observation.observationId)) ordered.push(observation);
  }
  return ordered;
}

export function applyRunEventBatch(current, incomingEvents) {
  const state = { ...current, seenSequences: [...current.seenSequences], observations: [...current.observations], sceneActions: [...(current.sceneActions || [])] };
  const seen = new Set(state.seenSequences);
  const observations = new Map(state.observations.map((item) => [item.observationId, item]));
  const events = incomingEvents
    .filter((event) => event?.runId === state.runId && Number.isInteger(event.eventSequence))
    .sort((left, right) => left.eventSequence - right.eventSequence);

  for (const event of events) {
    if (seen.has(event.eventSequence)) continue;
    seen.add(event.eventSequence);
    if (event.type.startsWith("run.")) state.status = event.status || event.type.slice(4);
    if (event.type === "phase.changed") state.status = event.status || "running";
    if (event.type === "observation.upsert" && event.observation?.observationId) {
      observations.set(event.observation.observationId, { ...observations.get(event.observation.observationId), ...event.observation });
    }
    if (event.type === "tool.completed" && event.payload?.observationId) {
      observations.set(event.payload.observationId, {
        observationId: event.payload.observationId,
        parentObservationId: null,
        depth: 0,
        kind: "tool",
        name: event.payload.toolId || event.payload.toolLabel || "Agent 工具",
        status: event.payload.status === "completed" ? "success" : event.status || "success",
        summary: event.payload.summary || "",
        evidenceId: event.payload.evidenceId || null,
      });
    }
    if (event.type === "message.completed") state.message = event.message || null;
    if (event.type === "response.completed") state.message = event.payload || null;
    if (event.type === "scene.action" && event.action?.command && event.action?.assetId) state.sceneActions = [event.action];
    if (event.type === "run.failed") state.error = event.error || { message: "Agent 运行失败" };
    if (event.type === "error") state.error = event.payload || event.error || { message: "Agent 运行失败" };
    if (event.type === "run.completed") state.externalObservability = event.externalObservability || null;
  }
  state.seenSequences = [...seen].sort((left, right) => left - right).slice(-500);
  state.lastEventId = String(state.seenSequences.at(-1) || 0);
  state.observations = orderObservations([...observations.values()]);
  return state;
}

export function parseSseFrames(buffer) {
  const normalized = buffer.replaceAll("\r\n", "\n");
  const frames = normalized.split("\n\n");
  const remainder = frames.pop() || "";
  const events = [];
  for (const frame of frames) {
    const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data));
    } catch {
      // 损坏帧由 snapshot 恢复，不把部分数据写入 Store。
    }
  }
  return { events, remainder };
}

export function resolveSceneResourceCount({ sceneReady, observedLoaded, loadingTotal }) {
  const total = Math.max(0, Number(loadingTotal) || 0);
  if (sceneReady) return total;
  return Math.max(0, Math.min(total, Number(observedLoaded) || 0));
}

const RANGE_POINTS = { realtime: 60, "6h": 72, "24h": 96, "7d": 112, "30d": 120 };

export function createDemoEnergyFlow(range = "24h", scope = "station") {
  const count = RANGE_POINTS[range] || RANGE_POINTS["24h"];
  const end = Date.now();
  const durationMs = range === "realtime" ? 60 * 60_000 : range === "6h" ? 6 * 3_600_000 : range === "7d" ? 7 * 86_400_000 : range === "30d" ? 30 * 86_400_000 : 24 * 3_600_000;
  const scopeShift = scope ? [...scope].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % 9 : 0;
  return Array.from({ length: count }, (_, index) => {
    const phase = (index / Math.max(1, count - 1)) * Math.PI * 4;
    const solarWindow = Math.max(0, Math.sin(phase - 0.9));
    const timestamp = new Date(end - durationMs + (durationMs * index) / Math.max(1, count - 1)).toISOString();
    return {
      timestamp,
      pvMw: +(solarWindow * 47 + Math.sin(phase * 3) * 2).toFixed(1),
      windMw: +(34 + Math.sin(phase * 0.75 + scopeShift) * 12 + Math.cos(phase * 2.2) * 4).toFixed(1),
      essChargeMw: +(-Math.max(0, Math.sin(phase + 1.2)) * 31).toFixed(1),
      essDischargeMw: +(Math.max(0, Math.sin(phase - 1.8)) * 36).toFixed(1),
      loadMw: +(-68 - Math.sin(phase * 0.55) * 16).toFixed(1),
      gridMw: +(8 + Math.sin(phase * 0.8) * 12).toFixed(1),
      socPct: +(66 + Math.sin(phase * 0.45 - 0.5) * 16).toFixed(1),
    };
  });
}

export function summarizeEnergyFlow(points) {
  if (!points.length) return { pvMwh: 0, windMwh: 0, chargeMwh: 0, dischargeMwh: 0, loadMwh: 0, gridMwh: 0, equivalentCycles: 0 };
  const hours = points.length > 1 ? Math.max(0, Date.parse(points.at(-1).timestamp) - Date.parse(points[0].timestamp)) / 3_600_000 / (points.length - 1) : 0;
  const total = (key) => points.reduce((sum, point) => sum + Math.abs(Number(point[key]) || 0) * hours, 0);
  const chargeMwh = total("essChargeMw");
  const dischargeMwh = total("essDischargeMw");
  return {
    pvMwh: total("pvMw"),
    windMwh: total("windMw"),
    chargeMwh,
    dischargeMwh,
    loadMwh: total("loadMw"),
    gridMwh: total("gridMw"),
    equivalentCycles: (chargeMwh + dischargeMwh) / (2 * 200),
  };
}
