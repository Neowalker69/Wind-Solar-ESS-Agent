import { create } from "zustand";
import { logger } from "./utils/logger";
import { createContainerFleet } from "./features/sceneLayout";
import { createBessRuntimeOverview } from "./features/stationTelemetryClient";
import { resolveWindSunStorageStore } from "./features/storeSingleton";

// ====================== Initial container data ======================
// 32 个储能集装箱按 4 × 8 矩阵部署；保留原有告警样例。
export const INIT_CONTAINERS = createContainerFleet();

// ====================== Alarm bands (ordered color intervals) ======================
export const ALARM_BANDS = [
  { from: -Infinity, to: 40, severity: "normal", color: "#10b981", label: "正常" },
  { from: 40, to: 50, severity: "warning", color: "#f59e0b", label: "预警" },
  { from: 50, to: Infinity, severity: "critical", color: "#ef4444", label: "严重" },
];

// Band lookup helper
function bandForTemp(temp) {
  return (
    ALARM_BANDS.find((b) => temp >= b.from && temp < b.to) ||
    ALARM_BANDS[ALARM_BANDS.length - 1]
  );
}

export function severityForTemp(temp) {
  return bandForTemp(temp).severity;
}

export function colorForTemp(temp) {
  return bandForTemp(temp).color;
}

// ====================== Smooth heatmap ramp 10C(cyan) -> 60C(red) ======================
// Mirrors the --temp-0..9 cool->hot ramp defined in index.css.
const TEMP_RAMP = [
  "#22d3ee", // 0 cool cyan
  "#38bdf8",
  "#60a5fa",
  "#818cf8",
  "#a78bfa",
  "#c084fc",
  "#f472b6",
  "#fb7185",
  "#f87171",
  "#ef4444", // 9 hot red
];

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function rgbToHex([r, g, b]) {
  const c = (n) => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, "0");
  return `#${c(r)}${c(g)}${c(b)}`;
}

export function tempColorScale(temp) {
  const lo = 10;
  const hi = 60;
  const t = Math.max(0, Math.min(1, (temp - lo) / (hi - lo)));
  const pos = t * (TEMP_RAMP.length - 1);
  const i = Math.floor(pos);
  const f = pos - i;
  if (i >= TEMP_RAMP.length - 1) return TEMP_RAMP[TEMP_RAMP.length - 1];
  const a = hexToRgb(TEMP_RAMP[i]);
  const b = hexToRgb(TEMP_RAMP[i + 1]);
  return rgbToHex([
    a[0] + (b[0] - a[0]) * f,
    a[1] + (b[1] - a[1]) * f,
    a[2] + (b[2] - a[2]) * f,
  ]);
}

// ====================== Severity -> hex ======================
const SEVERITY_COLORS = {
  normal: "#10b981",
  warning: "#f59e0b",
  critical: "#ef4444",
  info: "#00d4ff",
};

export function severityColor(sev) {
  return SEVERITY_COLORS[sev] || SEVERITY_COLORS.info;
}

export function clusterIdForDevice(deviceId) {
  const match = /^A-\d{2}/.exec(deviceId || "");
  return match?.[0] || null;
}

export function packageMetricsForContainer(container) {
  if (!container) return [];
  return Array.from({ length: 8 }, (_, index) => {
    const centered = index - 3.5;
    const soc = Math.max(4, Math.min(100, +(container.soc + centered * 1.7).toFixed(1)));
    const soh = Math.max(68, Math.min(100, +(96 - Math.abs(centered) * 1.2 - (container.severity === "critical" && index === 2 ? 18 : 0)).toFixed(1)));
    const voltage = +(648 + centered * 2.4 - (container.severity === "critical" && index === 2 ? 42 : 0)).toFixed(1);
    const severity = index === 2 && container.severity === "critical"
      ? "critical"
      : (index === 1 && container.severity === "warning") || soc < 20 || soh < 80 || voltage < 620
        ? "warning"
        : "normal";
    return { index, id: `${container.id}-P${String(index + 1).padStart(2, "0")}`, soc, soh, voltage, severity };
  });
}

// ====================== Timeline segments (colored alarm intervals) ======================
const TIMELINE_SEGMENTS = [
  { from: 0, to: 0.3, severity: "normal" },
  { from: 0.3, to: 0.4, severity: "critical", label: "A-03 高温", deviceId: "A-03", time: "14:23" },
  { from: 0.4, to: 0.62, severity: "normal" },
  { from: 0.62, to: 0.77, severity: "warning", label: "风扇异常", deviceId: "W-03", time: "14:18" },
  { from: 0.77, to: 0.92, severity: "warning", label: "高温预警", deviceId: "A-07", time: "13:55" },
  { from: 0.92, to: 1, severity: "normal" },
];

// ====================== Store ======================
export const useStore = resolveWindSunStorageStore(() => create((set, get) => ({
  // --- containers ---
  containers: INIT_CONTAINERS,
  replaceContainers: (containers) => set({ containers }),
  runtimeOverview: createBessRuntimeOverview(),
  replaceRuntimeOverview: (runtimeOverview) => set({ runtimeOverview }),
  runtimeRefreshNonce: 0,
  refresh: () => {
    logger.info("app", "Refresh triggered", { selectedDevice: get().selectedDevice });
    set((state) => ({ runtimeRefreshNonce: state.runtimeRefreshNonce + 1 }));
  },

  // --- view ---
  activeView: 0, // 0数据 1温度热力 2潮流 3告警 4视频
  setActiveView: (n) => {
    logger.info("view", "View switched", { from: get().activeView, to: n });
    set({ activeView: n, selectedPackageIndex: n === 0 ? get().selectedPackageIndex : null });
  },

  // --- selection / hover ---
  selectedDevice: null,
  setSelectedDevice: (id) => {
    logger.info("device", "Device selected", { id });
    const packageMatch = /-P(\d{2})/.exec(id || "");
    set({
      selectedDevice: id,
      selectedPackageIndex: packageMatch ? Number(packageMatch[1]) - 1 : null,
    });
  },
  hoverDevice: null,
  setHoverDevice: (id) => set({ hoverDevice: id }),
  selectedPackageIndex: null,
  setSelectedPackageIndex: (index) => set({ selectedPackageIndex: index }),
  coolingMode: "auto",
  setCoolingMode: (mode) => set({ coolingMode: mode }),

  // --- logs ---
  debugLogsEnabled: process.env.NODE_ENV !== 'production',
  setDebugLogsEnabled: (enabled) => {
    logger.info("logger", "Debug log switch updated", { enabled });
    set({ debugLogsEnabled: enabled });
  },

  // --- scene loading ---
  loadingTotal: 6,
  loadedResources: 0,
  sceneLoading: true,
  sceneReady: false,
  loadingOverlayVisible: true,
  loadingStartedAt: 0,
  minLoadingDurationMs: 1500,
  startSceneLoading: () => {
    const nextStartedAt = Date.now();
    logger.info("loading", "Loading started", { total: get().loadingTotal });
    set({
      loadedResources: 0,
      sceneLoading: true,
      sceneReady: false,
      loadingOverlayVisible: true,
      loadingStartedAt: nextStartedAt,
    });
  },
  setLoadedResources: (count) => {
    const clamped = Math.max(0, Math.min(get().loadingTotal, count));
    const previous = get().loadedResources;
    if (clamped !== previous) {
      logger.debug("loading", "Loading progress updated", {
        loaded: clamped,
        total: get().loadingTotal,
      });
    }
    set({ loadedResources: clamped });
  },
  setSceneReady: (ready) => {
    logger.info("scene", ready ? "Scene ready" : "Scene marked not ready", {
      loadedResources: get().loadedResources,
      total: get().loadingTotal,
    });
    set({ sceneReady: ready });
  },
  finishSceneLoading: () => {
    logger.info("loading", "Loading finished", {
      loadedResources: get().loadedResources,
      total: get().loadingTotal,
    });
    set({
      sceneLoading: false,
    });
  },
  hideLoadingOverlay: () => set({ loadingOverlayVisible: false }),

  // --- temperature range filter ---
  tempRange: [10, 60],
  setTempRange: (range) => set({ tempRange: range }),

  // --- playback ---
  playing: true,
  setPlaying: (b) => set({ playing: b }),
  togglePlay: () => set((s) => ({ playing: !s.playing })),
  speed: "1x", // '0.5x'|'1x'|'2x'|'4x'
  setSpeed: (s) => set({ speed: s }),

  // --- timeline ---
  timelineProgress: 0.5,
  setTimelineProgress: (p) => set({ timelineProgress: Math.max(0, Math.min(1, p)) }),
  timelineSegments: TIMELINE_SEGMENTS,

  // --- alerts ---
  alerts: [],
  replaceAlerts: (alerts) => set({ alerts }),

  // --- layers ---
  layers: { heatmap: true, labels: true },
  toggleLayer: (key) =>
    set((s) => ({ layers: { ...s.layers, [key]: !s.layers[key] } })),

  // --- camera reset + presets ---
  resetCameraNonce: 0,
  cameraPreset: null, // { pos: [x,y,z], target: [x,y,z] } | null → uses defaults
  resetCamera: (preset = null) => set((s) => ({ resetCameraNonce: s.resetCameraNonce + 1, cameraPreset: preset })),
  cameraUserControlNonce: 0,
  markCameraUserControlled: () => set((s) => ({ cameraUserControlNonce: s.cameraUserControlNonce + 1 })),

  // --- settings / layers popover ---
  settingsOpen: false,
  toggleSettings: () => set((s) => ({ settingsOpen: !s.settingsOpen })),
})));

globalThis.__WIND_SUN_STORAGE_STORE__ = useStore;
