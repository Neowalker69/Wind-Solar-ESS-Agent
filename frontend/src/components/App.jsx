import React, { useState, useEffect, useRef, useMemo, useCallback, Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { useProgress } from "@react-three/drei";
import { Icon, Toast, MetricCard, StatusPill, RangeSlider, GasGauge, SegmentedBar, CameraFeed } from "./components";
import { Scene3D, TopologySLD, CameraGrid } from "./scene";
import { logger } from "../utils/logger";
import { useStore, clusterIdForDevice, severityColor } from "../store";
import { DonutChart, ScatterExtreme, RealtimeMultiLine, VerticalTempRange, TempBar } from "./charts";
import { VideoMonitorView, VideoMonitorPanel } from "./video";
import { EnergyFlowTrend } from "../features/EnergyFlowTrend";
import { BessTelemetryBridge } from "../features/BessTelemetryBridge";
import { resolveSceneResourceCount } from "../features/digitalTwinAdapters";
import { SCENE_RENDER_POLICY } from "../features/sceneLayout";
import { Bot } from "lucide-react";
import { TWIN_VIEW_DEFINITIONS, viewDefinitionForIndex } from "../../../apps/harness-control/src/workspace/twin-view-registry";
import * as Tooltip from "@radix-ui/react-tooltip";
import * as ScrollArea from "@radix-ui/react-scroll-area";
import * as Progress from "@radix-ui/react-progress";
import * as Separator from "@radix-ui/react-separator";

// ====================== Radix UI primitives (themed wrappers) ======================
// Thin, dark-cyan-styled wrappers so the data dashboard uses real radix-ui under the hood.
const RScroll = ({ children, style }) => (
  <ScrollArea.Root style={{ overflow: "hidden", flex: 1, minHeight: 0, ...style }}>
    <ScrollArea.Viewport style={{ width: "100%", height: "100%" }}>{children}</ScrollArea.Viewport>
    <ScrollArea.Scrollbar orientation="vertical" style={{ display: "flex", userSelect: "none", touchAction: "none", width: 6, padding: 1 }}>
      <ScrollArea.Thumb style={{ flex: 1, background: "rgba(0,212,255,0.28)", borderRadius: 4 }} />
    </ScrollArea.Scrollbar>
  </ScrollArea.Root>
);

const RProgress = ({ value, max = 100, color = "var(--brand-primary)", height = 3 }) => {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <Progress.Root value={pct} style={{ position: "relative", overflow: "hidden", height, background: "#1f2738", borderRadius: 2 }}>
      <Progress.Indicator
        style={{ height: "100%", width: "100%", background: color, borderRadius: 2, boxShadow: `0 0 6px ${color}`,
          transform: `translateX(-${100 - pct}%)`, transition: "transform 600ms cubic-bezier(0.4,0,0.2,1)" }} />
    </Progress.Root>
  );
};

const RTip = ({ label, children }) => (
  <Tooltip.Root>
    <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
    <Tooltip.Portal>
      <Tooltip.Content side="top" sideOffset={6}
        style={{ background: "rgba(10,14,26,0.96)", border: "1px solid var(--brand-primary)", borderRadius: 6,
          padding: "4px 8px", fontSize: 11, fontFamily: "var(--ff-mono)", color: "var(--brand-primary)",
          boxShadow: "0 0 16px rgba(0,212,255,0.3)", zIndex: 200 }}>
        {label}
        <Tooltip.Arrow style={{ fill: "var(--brand-primary)" }} />
      </Tooltip.Content>
    </Tooltip.Portal>
  </Tooltip.Root>
);

const RSeparator = (props) => (
  <Separator.Root {...props} style={{ background: "var(--border-divider)", height: 1, width: "100%", margin: 0, border: "none", ...(props.style || {}) }} />
);

const TOOLBAR_GLYPHS = {
  refresh: <><path d="M20 6v5h-5" /><path d="M19 11a8 8 0 1 0 1 5" /></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
  settings: <><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.5v-.1a1.7 1.7 0 0 0-1.4-1.5 1.7 1.7 0 0 0-1.88.34l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 3.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H2V9.5h.1A1.7 1.7 0 0 0 3.6 8a1.7 1.7 0 0 0-.34-1.88l-.06-.06L6.06 3.2l.06.06A1.7 1.7 0 0 0 8 3.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V2h4.1v.1A1.7 1.7 0 0 0 15 3.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 8a1.7 1.7 0 0 0 .6 1 1.7 1.7 0 0 0 1.1.4h.1v4.1h-.1a1.7 1.7 0 0 0-1.7 1.5Z" /></>,
  maximize: <><path d="M8 3H3v5" /><path d="M16 3h5v5" /><path d="M8 21H3v-5" /><path d="M16 21h5v-5" /></>,
  minimize: <><path d="M8 3v5H3" /><path d="M16 3v5h5" /><path d="M8 21v-5H3" /><path d="M16 21v-5h5" /></>,
};

const ToolbarIconButton = ({ icon, label, onClick, active = false, badge = null, size = 30 }) => (
  <button
    type="button"
    className={`btn icon-only toolbar-icon-button ${active ? "active" : ""}`}
    style={{ height: size, width: size, position: "relative" }}
    title={label}
    aria-label={label}
    onClick={onClick}
  >
    <svg
      className="toolbar-glyph"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="#7dd3fc"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {TOOLBAR_GLYPHS[icon]}
    </svg>
    {badge !== null && <span className="toolbar-icon-badge">{badge}</span>}
  </button>
);

// ====================== Settings / layers popover (headbar 设置 action) ======================
const SettingsPanel = () => {
  const open = useStore((s) => s.settingsOpen);
  const toggle = useStore((s) => s.toggleSettings);
  const layers = useStore((s) => s.layers);
  const toggleLayer = useStore((s) => s.toggleLayer);
  if (!open) return null;
  const items = [
    { key: "labels",  label: "设备标签", icon: "tag"      },
    { key: "heatmap", label: "热力辉光", icon: "flame"    },
  ];
  return (
    <div className="card" style={{ position: "absolute", top: 88, right: 24, width: 220, zIndex: 60, padding: 0, background: "rgba(10,14,26,0.95)", backdropFilter: "blur(12px)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", borderBottom: "1px solid var(--border-divider)" }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", letterSpacing: "0.08em" }}>显示设置 · LAYERS</span>
        <button className="btn icon-only" style={{ height: 24, width: 24 }} onClick={toggle}><Icon name="x" size={12} /></button>
      </div>
      <div style={{ padding: "8px 14px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map((it) => (
          <button key={it.key} className={`btn ${layers[it.key] ? "active" : ""}`}
            style={{ height: 30, justifyContent: "space-between" }} onClick={() => toggleLayer(it.key)}>
            <span style={{ display:"flex", alignItems:"center", gap:6, fontSize: 12 }}>
              <Icon name={it.icon} size={12} color={layers[it.key] ? "var(--brand-primary)" : "var(--text-tertiary)"} />
              {it.label}
            </span>
            <span style={{ fontSize: 10, fontFamily: "var(--ff-mono)" }}>{layers[it.key] ? "ON" : "OFF"}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

// ====================== SOC battery indicator (inline SVG, number inside) ======================
const SocBattery = ({ soc }) => {
  const pct = Math.max(0, Math.min(100, soc));
  const color = pct < 20 ? "#ef4444" : pct < 50 ? "#f59e0b" : "#10b981";
  const fillW = Math.round((pct / 100) * 14);
  return (
    <svg width="30" height="13" viewBox="0 0 30 13" style={{ display: "inline-block", verticalAlign: "middle", flexShrink: 0 }}>
      <rect x="0.6" y="0.6" width="25" height="11.8" rx="1.5" fill="rgba(10,14,26,0.7)" stroke={color} strokeWidth="1.2" />
      <rect x="25.8" y="3.5" width="3.2" height="6" rx="1" fill={color} />
      <rect x="1.8" y="1.8" width={fillW} height="9.4" rx="0.8" fill={color} opacity="0.65" />
      <text x="13.5" y="9.5" fontSize="5.8" fill="#e6ebf5" textAnchor="middle" fontFamily="monospace" fontWeight="700">{pct}%</text>
    </svg>
  );
};

// ====================== Live Clock (isolated so the 1s tick does not re-render the whole tree) ======================
const LiveClock = ({ style }) => {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString("zh-CN", { hour12: false }));
  useEffect(() => {
    const t = setInterval(() => setTime(new Date().toLocaleTimeString("zh-CN", { hour12: false })), 1000);
    return () => clearInterval(t);
  }, []);
  return <span style={style}>{time}</span>;
};

// ====================== Header ======================
const Header = ({ activeView, onViewChange, agentOpen, onAgentToggle }) =>
<div className="card area-header" style={{ padding: "0 24px", display: "flex", alignItems: "center", gap: 24, position: "relative" }}>
    <span className="corner-deco tl" /><span className="corner-deco tr" />
    <span className="corner-deco bl" /><span className="corner-deco br" />

    {/* Logo */}
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <div style={{
      width: 36, height: 36, position: "relative",
      display: "grid", placeItems: "center"
    }}>
        <svg viewBox="0 0 36 36" width="36" height="36" style={{ filter: "drop-shadow(0 0 8px rgba(0,212,255,0.6))" }}>
          <polygon points="18,3 32,11 32,25 18,33 4,25 4,11" fill="none" stroke="#00d4ff" strokeWidth="1.5" />
          <polygon points="18,8 28,13 28,23 18,28 8,23 8,13" fill="none" stroke="#00d4ff" strokeWidth="0.8" opacity="0.5" />
          <circle cx="18" cy="18" r="3" fill="#00d4ff" />
          <circle cx="18" cy="18" r="6" fill="none" stroke="#00d4ff" strokeWidth="0.5" opacity="0.4">
            <animate attributeName="r" values="6;9;6" dur="2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.4;0;0.4" dur="2s" repeatCount="indefinite" />
          </circle>
        </svg>
      </div>
      <div>
        <div style={{ fontSize: "var(--text-lg)", fontWeight: 600, letterSpacing: "0.05em" }}>
          风光储一体化数字孪生
        </div>
        <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)", letterSpacing: "0.1em" }}>
          WIND · SOLAR · STORAGE · DIGITAL TWIN
        </div>
      </div>
    </div>

    {/* Tabs */}
    <div className="tab-group" style={{ marginLeft: 28 }}>
      {TWIN_VIEW_DEFINITIONS.map((definition, index) =>
    <div key={definition.id} className={`tab ${activeView === index ? "active" : ""}`} onClick={() => onViewChange(index)}>
          {definition.label}
        </div>
    )}
    </div>

    {/* Site selector */}
    <div style={{ marginLeft: 16, display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", border: "1px solid var(--border-divider)", borderRadius: "var(--r-md)" }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--status-normal)", boxShadow: "var(--glow-normal)" }} />
      <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>示范电站 · 北京昌平</span>
      <Icon name="chevD" size={12} color="var(--text-tertiary)" />
    </div>

    <div style={{ flex: 1 }} />

    {/* Live time + status */}
    <div style={{ textAlign: "right" }}>
      <LiveClock style={{ display: "block", fontFamily: "var(--ff-display)", fontWeight: 700, fontSize: "var(--text-lg)", letterSpacing: "0.02em" }} />
      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)", marginTop: 2 }}>
        UPTIME 142d 03:24:18 · 数据延迟 &lt; 200ms
      </div>
    </div>

    {/* Actions */}
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 8 }}>
      <button type="button" className={`agent-launch ${agentOpen ? "active" : ""}`} onClick={onAgentToggle} aria-label={agentOpen ? "关闭 AI Agent 工作台" : "打开 AI Agent 工作台"} aria-pressed={agentOpen}>
        <span><Bot size={16} /></span><b>AI Agent</b>
      </button>
      <ToolbarIconButton icon="refresh" label="刷新数据" onClick={() => useStore.getState().refresh()} />
      <ToolbarIconButton icon="bell" label="查看告警" badge={useStore.getState().alerts.length} onClick={() => useStore.getState().setActiveView(3)} />
      <ToolbarIconButton icon="settings" label="设置 / 图层" onClick={() => useStore.getState().toggleSettings()} />
      <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 12, borderLeft: "1px solid var(--border-divider)" }}>
        <div style={{ width: 28, height: 28, borderRadius: "50%", background: "linear-gradient(135deg, #4f46e5, #00d4ff)", display: "grid", placeItems: "center", fontSize: "var(--text-xs)", fontWeight: 600 }}>张</div>
        <div>
          <div style={{ fontSize: "var(--text-sm)", lineHeight: 1.2 }}>张工</div>
          <div style={{ fontSize: 10, color: "var(--text-tertiary)" }}>运维工程师</div>
        </div>
      </div>
    </div>
  </div>;


// ====================== Left Sidebar: Device Tree ======================
const DeviceTree = ({ containers, selectedDevice, onSelect, hoverDevice, onHover }) => {
  const [expanded, setExpanded] = useState({
    site: true, ess: true, sub: false,
  });
  const toggle = (k) => setExpanded((p) => ({ ...p, [k]: !p[k] }));

  const sevColor = (s) => s === "critical" ? "var(--status-critical)" : s === "warning" ? "var(--status-warning)" : "var(--status-normal)";

  const abnormalCount = containers.filter(c => c.severity !== "normal").length;

  return (
    <div className="card area-sidebar" style={{ display: "flex", flexDirection: "column", position: "relative" }}>
      <span className="corner-deco tl" /><span className="corner-deco tr" />
      <span className="corner-deco bl" /><span className="corner-deco br" />

      <div className="card-header">
        <div className="card-title">设备树 · DEVICE TREE</div>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)" }}>{containers.length} BESS</span>
      </div>

      <div style={{ padding: "12px 16px 8px" }}>
        <div className="search">
          <Icon name="search" size={14} color="var(--text-tertiary)" />
          <input placeholder="搜索 BESS 容器…" />
          <span style={{ fontSize: 10, color: "var(--text-tertiary)", border: "1px solid var(--border-divider)", borderRadius: 3, padding: "1px 4px" }}>⌘K</span>
        </div>
      </div>

      <div style={{ padding: "4px 16px 8px", display: "flex", gap: 6 }}>
        {["全部", "异常", "离线"].map((f, i) =>
          <span key={f} className={`pill ${i === 1 ? "warning" : i === 2 ? "info" : "normal"}`}
            style={{ cursor: "pointer", opacity: i === 0 ? 1 : 0.6, height: 20, fontSize: 10 }}>
            {f}
            {i === 0 && <span style={{ opacity: 0.7 }}>{containers.length}</span>}
            {i === 1 && <span style={{ opacity: 0.7 }}>{abnormalCount}</span>}
            {i === 2 && <span style={{ opacity: 0.7 }}>0</span>}
          </span>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", paddingBottom: 8 }}>
        {/* Root */}
        <div onClick={() => toggle("site")} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", color: "var(--text-secondary)", cursor: "pointer", fontSize: "var(--text-sm)" }}>
          <Icon name={expanded.site ? "chevD" : "chevR"} size={12} />
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--status-normal)", boxShadow: "var(--glow-normal)" }} />
          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>示范电站</span>
          <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "var(--ff-mono)", color: "var(--text-tertiary)" }}>{containers.length} BESS</span>
        </div>

        {expanded.site &&
          <div style={{ paddingLeft: 12 }}>
            {/* ESS group */}
            <div onClick={() => toggle("ess")} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", cursor: "pointer", fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
              <Icon name={expanded.ess ? "chevD" : "chevR"} size={12} />
              <Icon name="battery" size={13} color="#00d4ff" />
              <span>储能舱组</span>
              <span style={{ marginLeft: "auto", fontFamily: "var(--ff-mono)", fontSize: 10, color: "var(--text-tertiary)" }}>{containers.length}/{containers.length}</span>
            </div>

            {expanded.ess && containers.map((c) => (
              <div
                key={c.id}
                className={`tree-node ${c.severity} ${selectedDevice === c.id ? "selected" : ""}`}
                style={{ marginLeft: 18, fontSize: "var(--text-sm)", paddingLeft: 20 }}
                onClick={() => onSelect(c.id)}
                onMouseEnter={() => onHover(c.id)}
                onMouseLeave={() => onHover(null)}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Icon name="battery" size={12} color={sevColor(c.severity)} strokeWidth={1.5} />
                  <span style={{ fontFamily: "var(--ff-mono)", fontWeight: 500 }}>BESS {c.id}</span>
                  <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "var(--ff-mono)", color: c.severity === "critical" ? "var(--status-critical)" : "var(--text-tertiary)" }}>
                    {Number.isFinite(c.temp) ? `${c.temp.toFixed(1)}℃` : "--"}
                  </span>
                </div>
                <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 3, fontFamily: "var(--ff-mono)", display: "flex", justifyContent: "space-between", alignItems: "center", paddingLeft: 17 }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>SOC <SocBattery soc={Number.isFinite(c.soc) ? c.soc : 0} /></span>
                  <span>{Number.isFinite(c.power) ? c.power.toFixed(0) : "--"} kW · 容器级</span>
                </div>
              </div>
            ))}
            {expanded.ess && (
              <div style={{ margin: "6px 14px 8px 32px", color: "var(--text-tertiary)", fontSize: 10, lineHeight: 1.5 }}>
                包/电芯级遥测未接入权威数据源
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}>
              <Icon name="wind" size={13} color="#60a5fa" />
              <Icon name="sun" size={13} color="#facc15" />
              <span>风光遥测本阶段未接入</span>
            </div>

            {/* Substation */}
            <div onClick={() => toggle("sub")} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", cursor: "pointer", fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
              <Icon name={expanded.sub ? "chevD" : "chevR"} size={12} />
              <Icon name="bolt" size={13} color="#3b82f6" />
              <span>升压变电站</span>
              <span style={{ marginLeft: "auto", fontFamily: "var(--ff-mono)", fontSize: 10, color: "var(--text-tertiary)" }}>220kV</span>
            </div>
          </div>
        }
      </div>
    </div>);

};

// ====================== Right Sidebar: View-responsive ======================
const RightPanel = ({ activeView, containers, runtimeOverview, alerts, onAlertClick, tempRange, selectedCamera, onSelectCamera }) => {
  const definition = viewDefinitionForIndex(activeView);
  if (definition.dashboard === "thermal") return <TempHeatmapPanel containers={containers} tempRange={tempRange}/>;
  if (definition.dashboard === "power-flow") return <FlowAnalysisPanel/>;
  if (definition.dashboard === "alarms") return <AlarmAnalysisPanel alerts={alerts} onAlertClick={onAlertClick}/>;
  if (definition.dashboard === "video") return <VideoMonitorPanel selectedCamera={selectedCamera} onSelectCamera={onSelectCamera}/>;
  return <DataOverviewPanel containers={containers} runtimeOverview={runtimeOverview} alerts={alerts} onAlertClick={onAlertClick}/>;
};

// ---------- View 0: Data Overview ----------
const DataOverviewPanel = ({ containers, runtimeOverview, alerts, onAlertClick }) => {
  const hasFacts = runtimeOverview.status === "live" || runtimeOverview.status === "stale";
  const ratedPowerMw = Math.max(1, containers.length * 1.25);
  const realtime = {
    net: runtimeOverview.history.map((point) => point.netPowerMw),
    discharge: runtimeOverview.history.map((point) => point.dischargingPowerMw),
    charge: runtimeOverview.history.map((point) => point.chargingPowerMw),
  };
  const sources = [
    { k: "net", label: "储能净功率", value: runtimeOverview.netPowerKw, color: "#60a5fa" },
    { k: "discharge", label: "放电功率", value: runtimeOverview.dischargingPowerKw, color: "#22c997" },
    { k: "charge", label: "充电功率", value: runtimeOverview.chargingPowerKw, color: "#f5a623" },
  ];
  const netPowerMw = hasFacts && Number.isFinite(runtimeOverview.netPowerKw)
    ? runtimeOverview.netPowerKw / 1000
    : null;
  const socHistory = runtimeOverview.history.map((point) => point.averageSoc).filter(Number.isFinite);
  const socDelta = socHistory.length > 1 ? socHistory.at(-1) - socHistory[0] : null;
  const socTrend = Number.isFinite(socDelta)
    ? { direction: socDelta > 0 ? "up" : socDelta < 0 ? "down" : "flat", value: `${Math.abs(socDelta).toFixed(1)}%` }
    : null;
  const updatedTime = runtimeOverview.updatedAt
    ? new Date(runtimeOverview.updatedAt).toLocaleTimeString("zh-CN", { hour12: false })
    : "--:--:--";
  const operatingLabel = !Number.isFinite(netPowerMw)
    ? "等待数据"
    : netPowerMw > 0.01 ? "放电中" : netPowerMw < -0.01 ? "充电中" : "待机";

  return (
    <div className="area-right" style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 0 }}>
      <div className="card" style={{ position: "relative", padding: "14px 16px 10px" }}>
        <span className="corner-deco tl" /><span className="corner-deco tr" />
        <span className="corner-deco bl" /><span className="corner-deco br" />
        <div style={{display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10}}>
          <div className="card-title" style={{margin:0}}>全站概览 · OVERVIEW</div>
          <span style={{fontSize:10, color:runtimeOverview.status === "live" ? "#10b981" : "#f59e0b", fontFamily:"var(--ff-mono)", display:"flex", alignItems:"center", gap:4}}>
            <span style={{width:6, height:6, borderRadius:"50%", background:runtimeOverview.status === "live" ? "#10b981" : "#f59e0b", boxShadow:runtimeOverview.status === "live" ? "0 0 6px #10b981" : "none", animation:runtimeOverview.status === "live" ? "pulse-soft 1.5s ease-in-out infinite" : "none"}}/>
            {runtimeOverview.status === "live" ? "权威数据 · 5s" : runtimeOverview.status === "stale" ? "数据已过期" : "正在连接"}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
          <span className="display-num" style={{ fontSize: "var(--text-4xl)" }}>{Number.isFinite(netPowerMw) ? netPowerMw.toFixed(2) : "--"}</span>
          <span style={{ color: "var(--text-secondary)", fontFamily: "var(--ff-mono)", fontSize: "var(--text-sm)" }}>MW</span>
          <span className={`pill ${runtimeOverview.status === "stale" ? "warning" : "normal"}`} style={{ marginLeft: "auto" }}><span className="dot" />{operatingLabel}</span>
        </div>
        <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: "var(--ff-mono)" }}>
          BESS 实时净功率 / AUTHORITATIVE NET POWER
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginTop: 14 }}>
          {sources.map(s => {
            const v = hasFacts && Number.isFinite(s.value) ? s.value / 1000 : null;
            return (
              <RTip key={s.k} label={Number.isFinite(v) ? `${s.label}: ${v.toFixed(2)} MW` : `${s.label}: 等待权威数据`}>
              <div>
                <div style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)" }}>{s.label}</div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
                  <span style={{ fontSize: "var(--text-lg)", fontFamily: "var(--ff-display)", fontWeight: 600 }}>{Number.isFinite(v) ? v.toFixed(2) : "--"}</span>
                  <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>MW</span>
                </div>
                <div style={{ marginTop: 4 }}>
                  <RProgress value={Number.isFinite(v) ? Math.abs(v) : 0} max={ratedPowerMw} color={s.color} />
                </div>
              </div>
              </RTip>
            );
          })}
        </div>

        {/* Realtime 3-series mini chart */}
        <div style={{ marginTop: 12, paddingTop: 10 }}>
          <RSeparator style={{ marginBottom: 10 }} />
          <div style={{ display:"flex", justifyContent:"space-between", fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", marginBottom:4, letterSpacing:"0.08em" }}>
            <span>session start</span>
            <span style={{color:"var(--brand-primary)"}}>本次会话 · 5 秒权威快照</span>
            <span>latest</span>
          </div>
          {runtimeOverview.history.length
            ? <RealtimeMultiLine height={64} data={realtime} colors={{net:"#60a5fa", discharge:"#22c997", charge:"#f5a623"}}/>
            : <div style={{height:64, display:"grid", placeItems:"center", color:"var(--text-tertiary)", fontSize:10}}>等待首个权威快照</div>}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <MetricCard title="平均 SOC" value={hasFacts && Number.isFinite(runtimeOverview.averageSoc) ? runtimeOverview.averageSoc.toFixed(1) : "--"} unit="%"
          trend={socTrend} sparkline={socHistory}
          severity="normal" icon="battery" />
        <MetricCard title="最后更新" value={updatedTime}
          severity={runtimeOverview.status === "stale" ? "warning" : "normal"} icon="activity" valueSize="var(--text-xl)" />
      </div>

      <div className="card" style={{ position: "relative", padding: "14px 16px", flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
        <span className="corner-deco tl" /><span className="corner-deco tr" />
        <span className="corner-deco bl" /><span className="corner-deco br" />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div className="card-title" style={{ margin: 0 }}>实时告警 · ALERTS</div>
          <span className="pill critical"><span className="dot" />{alerts.length} 待处理</span>
        </div>
        <RScroll>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {!alerts.length && <div style={{padding:"18px 4px", textAlign:"center", color:"var(--text-tertiary)", fontSize:11}}>当前无活动告警</div>}
          {alerts.map((a) =>
            <div key={a.id} onClick={() => onAlertClick(a.deviceId)}
              style={{
                padding: "10px 12px", border: "1px solid", borderRadius: "var(--r-md)",
                borderColor: a.severity === "critical" ? "rgba(239,68,68,0.4)" : "rgba(245,158,11,0.4)",
                background: a.severity === "critical" ? "var(--status-critical-bg)" : "var(--status-warning-bg)",
                cursor: "pointer"
              }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%",
                  background: a.severity === "critical" ? "var(--status-critical)" : "var(--status-warning)",
                  boxShadow: `0 0 8px ${a.severity === "critical" ? "var(--status-critical)" : "var(--status-warning)"}`,
                  animation: a.severity === "critical" ? "pulse-soft 1s ease-in-out infinite" : "none"
                }} />
                <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: a.severity === "critical" ? "var(--status-critical)" : "var(--status-warning)" }}>{a.title}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)" }}>{a.time}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", fontFamily: "var(--ff-mono)", paddingLeft: 14 }}>{a.detail}</div>
            </div>
          )}
          </div>
        </RScroll>
      </div>
    </div>
  );
};

// ---------- View 1: Temperature Heatmap ----------
const TempHeatmapPanel = ({ containers, tempRange }) => {
  // Synthetic stats — generated once
  const stats = useMemo(() => {
    const hi = 14;  // events in 24h
    const lo = 2;
    return { hi, lo };
  }, []);

  // Working range distribution
  const distribution = useMemo(() => {
    const high = containers.filter(c => c.temp > 45).length * 8;
    const mid = containers.filter(c => c.temp >= 25 && c.temp <= 45).length * 8;
    const low = containers.filter(c => c.temp < 25).length * 8;
    return [
      { label: "高温区 (>45℃)", value: high + 12, color: "#ef4444" },
      { label: "常温区 (25-45℃)", value: mid + 56, color: "#10b981" },
      { label: "低温区 (<25℃)", value: low + 8, color: "#06b6d4" },
      { label: "离线", value: 0, color: "#6b7280" },
    ];
  }, [containers]);

  return (
    <div className="area-right" style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 0 }}>
      {/* Header indicator */}
      <div className="card" style={{ position: "relative", padding: "14px 16px" }}>
        <span className="corner-deco tl" /><span className="corner-deco tr" />
        <span className="corner-deco bl" /><span className="corner-deco br" />
        <div style={{display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12}}>
          <div className="card-title" style={{margin:0}}>温度统计 · TEMP STATS</div>
          <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>近 24h</span>
        </div>

        <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12}}>
          <div style={{padding:"12px 14px", border:"1px solid rgba(239,68,68,0.35)", borderRadius:"var(--r-md)", background:"var(--status-critical-bg)", position:"relative", overflow:"hidden"}}>
            <div style={{display:"flex", alignItems:"center", gap:6, fontSize:11, color:"var(--text-secondary)"}}>
              <Icon name="flame" size={12} color="#ef4444"/>高温次数
            </div>
            <div style={{display:"flex", alignItems:"baseline", gap:6, marginTop:6}}>
              <span className="display-num" style={{fontSize:"var(--text-3xl)", color:"#ef4444"}}>{stats.hi}</span>
              <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>EVENTS</span>
            </div>
            <div style={{fontSize:10, color:"var(--text-tertiary)", marginTop:4, fontFamily:"var(--ff-mono)"}}>阈值 &gt; 45℃</div>
            <div style={{position:"absolute", right:-8, bottom:-8, opacity:0.06}}>
              <Icon name="flame" size={56} color="#ef4444"/>
            </div>
          </div>
          <div style={{padding:"12px 14px", border:"1px solid rgba(6,182,212,0.35)", borderRadius:"var(--r-md)", background:"rgba(6,182,212,0.1)", position:"relative", overflow:"hidden"}}>
            <div style={{display:"flex", alignItems:"center", gap:6, fontSize:11, color:"var(--text-secondary)"}}>
              <Icon name="thermo" size={12} color="#06b6d4"/>低温次数
            </div>
            <div style={{display:"flex", alignItems:"baseline", gap:6, marginTop:6}}>
              <span className="display-num" style={{fontSize:"var(--text-3xl)", color:"#06b6d4"}}>{stats.lo}</span>
              <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>EVENTS</span>
            </div>
            <div style={{fontSize:10, color:"var(--text-tertiary)", marginTop:4, fontFamily:"var(--ff-mono)"}}>阈值 &lt; 15℃</div>
            <div style={{position:"absolute", right:-8, bottom:-8, opacity:0.06}}>
              <Icon name="thermo" size={56} color="#06b6d4"/>
            </div>
          </div>
        </div>
      </div>

      {/* Scatter — Cell extremes */}
      <div className="card" style={{position:"relative", padding:"14px 16px"}}>
        <span className="corner-deco tl" /><span className="corner-deco tr" />
        <span className="corner-deco bl" /><span className="corner-deco br" />
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:8}}>
          <div className="card-title" style={{margin:0}}>极值分布 · EXTREMES</div>
          <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>180 cells · 10 cluster</span>
        </div>
        <ScatterExtreme width={328} height={170}/>
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginTop:8, paddingTop:8, borderTop:"1px solid var(--border-divider)", fontSize:10, fontFamily:"var(--ff-mono)"}}>
          <span style={{color:"var(--text-tertiary)"}}>异常单体</span>
          <span style={{color:"#ef4444", fontWeight:600}}>A-03 · Pack#3 · Cell#07</span>
          <span style={{color:"var(--text-tertiary)"}}>ΔT</span>
          <span style={{color:"#ef4444", fontWeight:600}}>18℃</span>
          <span style={{color:"var(--text-tertiary)"}}>一致性</span>
          <span style={{color:"#facc15", fontWeight:600}}>4.2%</span>
        </div>
      </div>

      {/* Working temp distribution */}
      <div className="card" style={{position:"relative", padding:"14px 16px", flex:1, minHeight:0}}>
        <span className="corner-deco tl" /><span className="corner-deco tr" />
        <span className="corner-deco bl" /><span className="corner-deco br" />
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10}}>
          <div className="card-title" style={{margin:0}}>电芯工作温区 · WORKING RANGE</div>
          <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>HIGH / MED / LOW / OFFLINE</span>
        </div>
        <SegmentedBar segments={distribution}/>

        <div style={{marginTop:14, paddingTop:10, borderTop:"1px solid var(--border-divider)", display:"grid", gridTemplateColumns:"1fr 1fr", gap:10}}>
          <div>
            <div style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>电芯一致性</div>
            <div style={{display:"flex", alignItems:"baseline", gap:6, marginTop:2}}>
              <span className="display-num" style={{fontSize:"var(--text-xl)"}}>96.3</span>
              <span style={{fontSize:10, color:"var(--text-secondary)"}}>%</span>
            </div>
            <div style={{fontSize:9, color:"#f59e0b", fontFamily:"var(--ff-mono)", marginTop:2}}>↓ 0.8% (7d)</div>
          </div>
          <div>
            <div style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>当前筛选</div>
            <div style={{display:"flex", alignItems:"baseline", gap:6, marginTop:2}}>
              <span className="display-num" style={{fontSize:"var(--text-xl)", color:"var(--brand-primary)"}}>{tempRange[0]}—{tempRange[1]}</span>
              <span style={{fontSize:10, color:"var(--text-secondary)"}}>℃</span>
            </div>
            <div style={{fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", marginTop:2}}>场景同步高亮</div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------- View 2: Flow Analysis (placeholder) ----------
const FlowAnalysisPanel = () => {
  const flows = [
    { name: "光伏 → 母线",  v: "690 V",    a: "347 A", p: "24.0 MW", color: "#facc15", dir: "in"  },
    { name: "风电 → 母线",  v: "35 kV",    a: "244 A", p: "17.1 MW", color: "#60a5fa", dir: "in"  },
    { name: "母线 → ESS",   v: "1500 V",   a: "825 A", p: "38.5 MW", color: "#f97316", dir: "out" },
    { name: "母线 → 电网",  v: "220 kV",   a: "209 A", p: "80.4 MW", color: "#3b82f6", dir: "out" },
  ];
  return (
    <div className="area-right" style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 0 }}>
      <div className="card" style={{position:"relative", padding:"14px 16px"}}>
        <span className="corner-deco tl" /><span className="corner-deco tr" />
        <span className="corner-deco bl" /><span className="corner-deco br" />
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:14}}>
          <div className="card-title" style={{margin:0}}>实时潮流 · LIVE FLOW</div>
          <span className="pill normal"><span className="dot"/>稳定</span>
        </div>
        <div style={{display:"flex", flexDirection:"column", gap:10}}>
          {flows.map((f, i) => (
            <div key={i} style={{padding:"10px 12px", border:`1px solid ${f.color}33`, borderRadius:"var(--r-md)", background:`linear-gradient(90deg, ${f.color}14, transparent)`}}>
              <div style={{display:"flex", justifyContent:"space-between", alignItems:"center"}}>
                <span style={{fontSize:12, color:f.color, fontWeight:600, fontFamily:"var(--ff-mono)"}}>{f.name}</span>
                <span style={{fontSize:10, color:f.color, fontFamily:"var(--ff-mono)", letterSpacing:"0.05em"}}>
                  {f.dir === "in" ? "← IN" : "OUT →"}
                </span>
              </div>
              <div style={{display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8, marginTop:8, fontFamily:"var(--ff-mono)"}}>
                <div>
                  <div style={{fontSize:9, color:"var(--text-tertiary)"}}>U</div>
                  <div style={{fontSize:13, color:"#e6ebf5", fontWeight:600}}>{f.v}</div>
                </div>
                <div>
                  <div style={{fontSize:9, color:"var(--text-tertiary)"}}>I</div>
                  <div style={{fontSize:13, color:"#e6ebf5", fontWeight:600}}>{f.a}</div>
                </div>
                <div>
                  <div style={{fontSize:9, color:"var(--text-tertiary)"}}>P</div>
                  <div style={{fontSize:13, color:f.color, fontWeight:600, filter:`drop-shadow(0 0 4px ${f.color})`}}>{f.p}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{position:"relative", padding:"14px 16px", flex:1, minHeight:0, display:"flex", flexDirection:"column"}}>
        <span className="corner-deco tl" /><span className="corner-deco tr" />
        <span className="corner-deco bl" /><span className="corner-deco br" />
        <div className="card-title" style={{marginBottom:10}}>功率平衡 · BALANCE</div>
        <div style={{display:"flex", justifyContent:"space-around", alignItems:"center", flex:1}}>
          <div style={{textAlign:"center"}}>
            <div style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>发电端</div>
            <div className="display-num" style={{fontSize:"var(--text-2xl)", color:"#facc15", marginTop:4}}>41.9</div>
            <div style={{fontSize:10, color:"var(--text-secondary)"}}>MW</div>
          </div>
          <div style={{fontSize:18, color:"var(--brand-primary)"}}>→</div>
          <div style={{textAlign:"center"}}>
            <div style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>ESS</div>
            <div className="display-num" style={{fontSize:"var(--text-2xl)", color:"#f97316", marginTop:4}}>38.5</div>
            <div style={{fontSize:10, color:"var(--text-secondary)"}}>MW ↑</div>
          </div>
          <div style={{fontSize:18, color:"var(--brand-primary)"}}>→</div>
          <div style={{textAlign:"center"}}>
            <div style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>电网端</div>
            <div className="display-num" style={{fontSize:"var(--text-2xl)", color:"#3b82f6", marginTop:4}}>80.4</div>
            <div style={{fontSize:10, color:"var(--text-secondary)"}}>MW</div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------- View 3: Alarm Analysis (placeholder) ----------
const AlarmAnalysisPanel = ({ alerts, onAlertClick }) => (
  <div className="area-right" style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 0 }}>
    <div className="card" style={{position:"relative", padding:"14px 16px"}}>
      <span className="corner-deco tl" /><span className="corner-deco tr" />
      <span className="corner-deco bl" /><span className="corner-deco br" />
      <div className="card-title" style={{marginBottom:10}}>告警分析 · ALARM ANALYSIS</div>
      <div style={{display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:8}}>
        {[
          {l:"严重", v:1, c:"#ef4444"},
          {l:"警告", v:2, c:"#f59e0b"},
          {l:"信息", v:5, c:"#3b82f6"},
        ].map(s => (
          <div key={s.l} style={{padding:"8px 10px", border:`1px solid ${s.c}40`, borderRadius:"var(--r-md)", background:`${s.c}14`}}>
            <div style={{fontSize:10, color:"var(--text-secondary)"}}>{s.l}</div>
            <div className="display-num" style={{fontSize:"var(--text-xl)", color:s.c, marginTop:2}}>{s.v}</div>
          </div>
        ))}
      </div>
    </div>

    <div className="card" style={{position:"relative", padding:"14px 16px", flex:1, minHeight:0, display:"flex", flexDirection:"column"}}>
      <span className="corner-deco tl" /><span className="corner-deco tr" />
      <span className="corner-deco bl" /><span className="corner-deco br" />
      <div className="card-title" style={{marginBottom:10}}>告警时间线 · TIMELINE</div>
      <RScroll>
      <div style={{display:"flex", flexDirection:"column", gap:10}}>
        {alerts.map((a, i) => (
          <div key={i} onClick={() => onAlertClick(a.deviceId)}
            style={{position:"relative", paddingLeft:18, paddingBottom:10, borderLeft:"1px dashed var(--border-divider)", cursor:"pointer"}}>
            <span style={{position:"absolute", left:-5, top:2, width:10, height:10, borderRadius:"50%",
              background: a.severity === "critical" ? "#ef4444" : "#f59e0b",
              boxShadow: `0 0 8px ${a.severity === "critical" ? "#ef4444" : "#f59e0b"}`,
              border:"2px solid #0a0e1a"}}/>
            <div style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>{a.time}</div>
            <div style={{fontSize:12, color: a.severity === "critical" ? "#ef4444" : "#f59e0b", fontWeight:600, marginTop:2}}>{a.title}</div>
            <div style={{fontSize:11, color:"var(--text-secondary)", fontFamily:"var(--ff-mono)", marginTop:4}}>{a.detail}</div>
            {/* mock thumbnail */}
            <div style={{marginTop:6, height:54, border:"1px solid var(--border-divider)", borderRadius:"var(--r-sm)", background:"linear-gradient(135deg, #0f172a, #1a2540)", display:"flex", alignItems:"center", justifyContent:"center", position:"relative", overflow:"hidden"}}>
              <svg width="100%" height="100%" viewBox="0 0 200 50" preserveAspectRatio="none">
                <rect x="40" y="12" width="40" height="24" fill="#1e293b" stroke={a.severity==="critical"?"#ef4444":"#f59e0b"} strokeWidth="1"/>
                <rect x="90" y="12" width="40" height="24" fill="#1e293b" stroke="#475569" strokeWidth="0.5"/>
                <text x="60" y="28" fontSize="6" fill={a.severity==="critical"?"#ef4444":"#f59e0b"} textAnchor="middle" fontFamily="JetBrains Mono">[{a.deviceId}]</text>
              </svg>
              <span style={{position:"absolute", top:4, right:6, fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>定位截图</span>
            </div>
          </div>
        ))}
      </div>
      </RScroll>
    </div>
  </div>
);

// ====================== Center Canvas (scene + overlays) ======================
const SceneLoadBoundary = () => {
  useEffect(() => {
    logger.debug("loading", "Canvas suspense fallback active");
  }, []);
  return null;
};

const SceneLoadingBridge = () => {
  const { active, loaded, errors } = useProgress();
  const loadingTotal = useStore((s) => s.loadingTotal);
  const sceneReady = useStore((s) => s.sceneReady);
  const setLoadedResources = useStore((s) => s.setLoadedResources);
  const loggedLoadedRef = useRef(false);
  const errorCountRef = useRef(0);

  useEffect(() => {
    setLoadedResources(resolveSceneResourceCount({
      sceneReady,
      observedLoaded: loaded,
      loadingTotal,
    }));
  }, [loaded, loadingTotal, sceneReady, setLoadedResources]);

  useEffect(() => {
    if (active) {
      logger.debug("loading", "Scene assets loading in progress", {
        loaded: Math.min(loadingTotal, loaded),
        total: loadingTotal,
      });
    }
  }, [active, loaded, loadingTotal]);

  useEffect(() => {
    if (loaded >= loadingTotal && !loggedLoadedRef.current) {
      logger.info("scene", "All GLB resources loaded", { loaded: loadingTotal, total: loadingTotal });
      loggedLoadedRef.current = true;
    }
    if (loaded < loadingTotal) {
      loggedLoadedRef.current = false;
    }
  }, [loaded, loadingTotal]);

  useEffect(() => {
    const nextErrors = errors.slice(errorCountRef.current);
    nextErrors.forEach((error, index) => {
      logger.error("scene", "Model load failed", {
        index: errorCountRef.current + index,
        error: error?.message || String(error),
      });
    });
    errorCountRef.current = errors.length;
  }, [errors]);

  return null;
};

const LoadingOverlay = () => {
  const sceneLoading = useStore((s) => s.sceneLoading);
  const overlayVisible = useStore((s) => s.loadingOverlayVisible);
  const loadedResources = useStore((s) => s.loadedResources);
  const loadingTotal = useStore((s) => s.loadingTotal);
  const sceneReady = useStore((s) => s.sceneReady);
  const progress = loadingTotal ? Math.min(100, Math.round((loadedResources / loadingTotal) * 100)) : 0;

  if (!overlayVisible) return null;

  return (
    <div className={`loading-overlay ${sceneLoading ? "active" : "fade-out"}`}>
      <div className="loading-panel">
        <div className="loading-eyebrow">ENERGY STATION · SCENE BOOTSTRAP</div>
        <div className="loading-ring-wrap">
          <div className="loading-ring loading-ring-outer" />
          <div className="loading-ring loading-ring-middle" />
          <div className="loading-ring loading-ring-inner" />
          <div className="loading-core">
            <span>{progress}%</span>
            <small>{sceneReady ? "SCENE READY" : "LOADING"}</small>
          </div>
          <div className="loading-topology-link loading-link-a" />
          <div className="loading-topology-link loading-link-b" />
          <div className="loading-topology-link loading-link-c" />
          <div className="loading-topology-link loading-link-d" />
          <div className="loading-nodes">
            {Array.from({ length: loadingTotal }).map((_, index) => {
              const lit = index < loadedResources;
              return <span key={index} className={`loading-node ${lit ? "lit" : ""}`} />;
            })}
          </div>
        </div>
        <div className="loading-title">风光储数字孪生场景加载中</div>
        <div className="loading-subtitle">正在初始化三维场景与能源数据 · 拓扑节点依次点亮</div>
        <div className="loading-progress-bar">
          <div className="loading-progress-fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="loading-progress-meta">
          <span>场景资源 {progress}%</span>
          <span>{sceneReady ? "SCENE READY" : "INITIALIZING 3D WORLD"}</span>
        </div>
      </div>
    </div>
  );
};

const CAMERA_PRESETS = [
  { label: "俯视", pos: [0, 52, 1],    target: [0, 0, 0]    }, // top-down
  { label: "等距", pos: [22, 16, 26],  target: [0, 1.5, 0]  }, // isometric (default)
  { label: "正面", pos: [0, 8, 40],    target: [0, 2, 0]    }, // front-facing
];

const CenterCanvas = ({ activeView, containers, selectedDevice, onSelect, hoverDevice, onHover, tempRange, onTempRangeChange, selectedCamera, onSelectCamera }) => {
  const definition = viewDefinitionForIndex(activeView);
  const isVideo = definition.sceneProfile === "camera";
  const canvasWrapRef = useRef(null);
  const resetCamera = useStore((s) => s.resetCamera);
  const cameraUserControlNonce = useStore((s) => s.cameraUserControlNonce);
  const [activeCamIdx, setActiveCamIdx] = useState(1); // default: 等距
  const [isFullscreen, setIsFullscreen] = useState(false);
  const selectedCluster = definition.sceneProfile === "asset"
    ? containers.find((container) => container.id === clusterIdForDevice(selectedDevice))
    : null;
  const setSelectedPackageIndex = useStore((s) => s.setSelectedPackageIndex);
  const coolingMode = useStore((s) => s.coolingMode);
  const setCoolingMode = useStore((s) => s.setCoolingMode);
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);
  useEffect(() => {
    if (cameraUserControlNonce > 0) setActiveCamIdx(null);
  }, [cameraUserControlNonce]);
  const toggleFullscreen = () => {
    const el = canvasWrapRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen?.();
    else el.requestFullscreen?.();
  };

  return (
    <div ref={canvasWrapRef} className="card area-canvas" style={{ position: "relative", overflow: "hidden", padding: 0 }}>
      <span className="corner-deco tl" /><span className="corner-deco tr" />
      <span className="corner-deco bl" /><span className="corner-deco br" />

      {/* View header */}
      <div style={{ position: "absolute", top: 14, left: 18, right: 18, display: "flex", alignItems: "center", justifyContent: "space-between", zIndex: 10, pointerEvents: "none" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, pointerEvents: "auto" }}>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)", letterSpacing: "0.15em" }}>SCENE / {definition.label.toUpperCase()}</div>
          <div style={{ height: 14, width: 1, background: "var(--border-divider)" }} />
          <div style={{ display: "flex", gap: 6 }}>
            {CAMERA_PRESETS.map((p, i) =>
              <button key={p.label}
                className={`btn ${activeCamIdx === i ? "active" : ""}`}
                style={{ height: 24, padding: "0 10px", fontSize: 11 }}
                onClick={() => { resetCamera(p); setActiveCamIdx(i); }}>
                {p.label}
              </button>
            )}
          </div>
        </div>

        <div style={{ display: "flex", gap: 6, pointerEvents: "auto" }}>
          <div className="cooling-mode-control" aria-label="ECC 散热强度">
            {[
              ["auto", "自动"],
              ["low", "低"],
              ["medium", "中"],
              ["high", "高"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={coolingMode === value ? "active" : ""}
                aria-pressed={coolingMode === value}
                onClick={() => setCoolingMode(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <ToolbarIconButton
            icon={isFullscreen ? "minimize" : "maximize"}
            label={isFullscreen ? "退出全屏" : "全屏"}
            active={isFullscreen}
            size={28}
            onClick={toggleFullscreen}
          />
        </div>
      </div>

      {/* Canvas 始终挂载，视角切换只更换叠层与场景配置。 */}
      <div style={{ position: "absolute", inset: 0 }}>
        <SceneLoadingBridge />
        <Canvas
          shadows={SCENE_RENDER_POLICY.realtimeShadows}
          dpr={selectedCluster ? 1 : [1, 1.5]}
          camera={{
            position: [22, 16, 26],
            fov: 45,
            near: SCENE_RENDER_POLICY.cameraNear,
            far: SCENE_RENDER_POLICY.cameraFar,
          }}
          gl={{ antialias: false, alpha: false, powerPreference: "high-performance" }}
          performance={{ min: 0.5 }}
          onPointerMissed={() => {
            onSelect(null);
            setSelectedPackageIndex(null);
          }}
          style={{ width: "100%", height: "100%" }}
        >
          <Suspense fallback={<SceneLoadBoundary />}>
            <Scene3D />
          </Suspense>
        </Canvas>
        <LoadingOverlay />
        {isVideo && (
          <div style={{ position: "absolute", inset: 0, zIndex: 4 }}>
            <VideoMonitorView selectedCamera={selectedCamera} onSelectCamera={onSelectCamera}/>
          </div>
        )}
      </div>

      {/* Bottom-left legend: Power flow only */}
      {(definition.legendProfile === "power" || definition.legendProfile === "flow") && (
      <div style={{ position: "absolute", left: 18, bottom: 14, zIndex: 5 }}>
        <div className="card" style={{ padding: "10px 14px", background: "rgba(10,14,26,0.7)" }}>
          <div style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)", marginBottom: 6, letterSpacing: "0.1em" }}>POWER FLOW</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, fontFamily: "var(--ff-mono)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 14, height: 2, background: "#10b981", boxShadow: "0 0 6px #10b981" }} /><span style={{ color: "var(--text-secondary)" }}>新能源充电</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 14, height: 2, background: "#f97316", boxShadow: "0 0 6px #f97316" }} /><span style={{ color: "var(--text-secondary)" }}>储能放电</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 14, height: 2, background: "#3b82f6", boxShadow: "0 0 6px #3b82f6" }} /><span style={{ color: "var(--text-secondary)" }}>电网交互</span>
            </div>
          </div>
        </div>
      </div>
      )}

      {/* Right-side TEMPERATURE legend (vertical, slider integrated) */}
      {definition.legendProfile === "temperature" && (
      <div className="card" style={{ position: "absolute", right: 14, bottom: 14, zIndex: 5, padding: "12px 14px 14px", background: "rgba(10,14,26,0.85)", backdropFilter:"blur(10px)" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom: 10, gap: 12 }}>
          <div style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)", letterSpacing: "0.1em" }}>TEMP</div>
          <span style={{fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>热力视图可拖动</span>
        </div>
        <VerticalTempRange
          min={10} max={60}
          value={tempRange}
          onChange={onTempRangeChange}
          active />
      </div>
      )}


      {/* Top-right inset: weather */}
      {!isVideo && definition.sceneProfile !== "asset" && !selectedCluster && (
      <div className="card" style={{ position: "absolute", top: 60, right: 14, padding: "10px 14px", background: "rgba(10,14,26,0.7)", minWidth: 172, zIndex: 5 }}>
        <div style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "var(--ff-mono)", marginBottom: 6, letterSpacing: "0.1em" }}>WEATHER · 实况</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative" }}>
            <Icon name="sun" size={28} color="#facc15" />
          </div>
          <div>
            <div style={{ fontFamily: "var(--ff-display)", fontSize: "var(--text-xl)", fontWeight: 600 }}>26<span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>℃</span></div>
            <div style={{ fontSize: 10, color: "var(--text-secondary)", fontFamily: "var(--ff-mono)" }}>晴 · 西南风 4级</div>
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--border-divider)", marginTop: 8, paddingTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 10, fontFamily: "var(--ff-mono)", color: "var(--text-secondary)" }}>
          <div>风速 <span style={{ color: "var(--text-primary)" }}>7.2 m/s</span></div>
          <div>湿度 <span style={{ color: "var(--text-primary)" }}>43%</span></div>
          <div>辐照 <span style={{ color: "var(--text-primary)" }}>820 W/m²</span></div>
          <div>气压 <span style={{ color: "var(--text-primary)" }}>1013 hPa</span></div>
        </div>
      </div>
      )}
    </div>);

};

// ====================== Bottom: Chart + Timeline ======================
const BottomPanel = ({ chartRange, onChartRangeChange, selectedDevice, stationId, onAskAgent }) => {
  return (
    <div className="card area-footer" style={{ position: "relative", overflow: "hidden" }}>
      <span className="corner-deco tl" /><span className="corner-deco tr" />
      <span className="corner-deco bl" /><span className="corner-deco br" />
      <EnergyFlowTrend range={chartRange} onRangeChange={onChartRangeChange} selectedDevice={selectedDevice} stationId={stationId} onAskAgent={onAskAgent} />
    </div>);

};

// ====================== Main App ======================
const App = ({ AgentWorkbenchComponent, agentStationId = "ess-station-01" }) => {
  // Single source of truth: Zustand store (Scene3D reads it directly).
  const activeView = useStore((s) => s.activeView);
  const setActiveView = useStore((s) => s.setActiveView);
  const selectedDevice = useStore((s) => s.selectedDevice);
  const setSelectedDevice = useStore((s) => s.setSelectedDevice);
  const hoverDevice = useStore((s) => s.hoverDevice);
  const setHoverDevice = useStore((s) => s.setHoverDevice);
  const containers = useStore((s) => s.containers);
  const runtimeOverview = useStore((s) => s.runtimeOverview);
  const tempRange = useStore((s) => s.tempRange);
  const setTempRange = useStore((s) => s.setTempRange);
  const alerts = useStore((s) => s.alerts);
  const loadedResources = useStore((s) => s.loadedResources);
  const loadingTotal = useStore((s) => s.loadingTotal);
  const sceneLoading = useStore((s) => s.sceneLoading);
  const sceneReady = useStore((s) => s.sceneReady);
  const loadingStartedAt = useStore((s) => s.loadingStartedAt);
  const minLoadingDurationMs = useStore((s) => s.minLoadingDurationMs);
  const loadingOverlayVisible = useStore((s) => s.loadingOverlayVisible);
  const startSceneLoading = useStore((s) => s.startSceneLoading);
  const finishSceneLoading = useStore((s) => s.finishSceneLoading);
  const hideLoadingOverlay = useStore((s) => s.hideLoadingOverlay);

  // Local-only UI state (not part of the shared scene contract).
  const [chartRange, setChartRange] = useState("24h");
  const [toastVisible, setToastVisible] = useState(true);
  const [selectedCamera, setSelectedCamera] = useState("CAM-02");
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentPrompt, setAgentPrompt] = useState("");
  const selectedContainer = containers.find((container) => container.id === clusterIdForDevice(selectedDevice)) || null;

  useEffect(() => {
    logger.info("app", "Page initialized", { initialView: activeView, selectedDevice });
    startSceneLoading();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!sceneLoading || !sceneReady || loadedResources < loadingTotal) return;
    const elapsed = Date.now() - loadingStartedAt;
    const remaining = Math.max(0, minLoadingDurationMs - elapsed);
    const timer = window.setTimeout(() => finishSceneLoading(), remaining);
    return () => window.clearTimeout(timer);
  }, [finishSceneLoading, loadedResources, loadingStartedAt, loadingTotal, minLoadingDurationMs, sceneLoading, sceneReady]);

  useEffect(() => {
    if (sceneLoading || !loadingOverlayVisible) return;
    const timer = window.setTimeout(() => hideLoadingOverlay(), 420);
    return () => window.clearTimeout(timer);
  }, [hideLoadingOverlay, loadingOverlayVisible, sceneLoading]);

  return (
    <Tooltip.Provider delayDuration={200}>
    <BessTelemetryBridge />
    <div className="grid-main">
      <Header activeView={activeView} onViewChange={setActiveView} agentOpen={agentOpen} onAgentToggle={() => setAgentOpen((value) => !value)} />
      <SettingsPanel />
      <DeviceTree containers={containers} selectedDevice={selectedDevice}
      onSelect={setSelectedDevice} hoverDevice={hoverDevice} onHover={setHoverDevice} />
      <CenterCanvas activeView={activeView} containers={containers}
      selectedDevice={selectedDevice} onSelect={setSelectedDevice}
      hoverDevice={hoverDevice} onHover={setHoverDevice}
      tempRange={tempRange} onTempRangeChange={setTempRange}
      selectedCamera={selectedCamera} onSelectCamera={setSelectedCamera} />
      <RightPanel activeView={activeView} containers={containers} runtimeOverview={runtimeOverview} alerts={alerts}
      onAlertClick={(id) => { setSelectedDevice(id); setAgentPrompt(`分析 ${id} 当前告警并给出处置建议`); setAgentOpen(true); }} tempRange={tempRange}
      selectedCamera={selectedCamera} onSelectCamera={setSelectedCamera} />
      <BottomPanel chartRange={chartRange} onChartRangeChange={setChartRange} selectedDevice={selectedContainer?.id || null} stationId={agentStationId} onAskAgent={(point) => { setAgentPrompt(`分析 ${new Date(point.timestamp).toLocaleString("zh-CN")} 的能量流量异常`); setAgentOpen(true); }} />
      {AgentWorkbenchComponent && <AgentWorkbenchComponent stationId={agentStationId} open={agentOpen} onClose={() => setAgentOpen(false)} container={selectedContainer} alerts={alerts} range={chartRange} initialPrompt={agentPrompt} onLocate={(id) => setSelectedDevice(id)} />}

      {toastVisible && alerts[0] &&
      <Toast
        title={alerts[0].title}
        desc={[alerts[0].detail]}
        time={alerts[0].time}
        severity={alerts[0].severity}
        onClose={() => setToastVisible(false)}
        onLocate={() => {setSelectedDevice(alerts[0].deviceId);setToastVisible(false);}} />

      }
    </div>
    </Tooltip.Provider>);

};


export default App;
