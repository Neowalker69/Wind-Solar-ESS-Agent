import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { ENERGY_SERIES, mergeEnergyPoints, summarizeEnergyFlow } from "./digitalTwinAdapters";
import { loadEnergyHistory, loadLatestEnergyPoint } from "./energyFlowClient";

const WIDTH = 1200;
const HEIGHT = 132;
const PAD = { left: 42, right: 38, top: 12, bottom: 22 };

function linePath(points, key, rightAxis = false) {
  const innerWidth = WIDTH - PAD.left - PAD.right;
  const innerHeight = HEIGHT - PAD.top - PAD.bottom;
  return points.map((point, index) => {
    const x = PAD.left + (index / Math.max(1, points.length - 1)) * innerWidth;
    const value = Number(point[key]) || 0;
    const y = rightAxis ? PAD.top + (1 - value / 100) * innerHeight : PAD.top + (1 - (value + 100) / 220) * innerHeight;
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

const metric = (value, unit = "MWh") => `${value >= 1000 ? (value / 1000).toFixed(1) : value.toFixed(1)} ${value >= 1000 ? "GWh" : unit}`;

export function EnergyFlowTrend({ range, onRangeChange, selectedDevice, stationId = "ess-station-01", onAskAgent }) {
  const [visible, setVisible] = useState(() => new Set(ENERGY_SERIES.map((series) => series.key)));
  const [hoverIndex, setHoverIndex] = useState(null);
  const [points, setPoints] = useState([]);
  const [dataState, setDataState] = useState({ status: "loading", source: "station", message: "" });
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [clock, setClock] = useState(Date.now());
  const chartRef = useRef(null);
  const summary = useMemo(() => summarizeEnergyFlow(points), [points]);
  const hoverPoint = hoverIndex == null ? null : points[hoverIndex];
  const latestTimestamp = points.at(-1)?.timestamp;
  const delayed = range === "realtime" && dataState.source === "station" && (!latestTimestamp || clock - Date.parse(latestTimestamp) > 15_000);
  const freshnessLabel = dataState.status === "error"
    ? "数据源异常"
    : delayed
      ? "数据延迟"
      : range === "realtime" ? "实时数据" : "权威数据";

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 5_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    const scope = selectedDevice || stationId;
    setHoverIndex(null);
    setDataState((current) => ({ ...current, status: "loading", message: "" }));
    loadEnergyHistory(range, scope).then((nextPoints) => {
      if (!active) return;
      if (!nextPoints.length) {
        setPoints([]);
        setDataState({ status: "empty", source: "station", message: "所选区间暂无遥测数据" });
        return;
      }
      setPoints(nextPoints);
      setDataState({ status: "ready", source: "station", message: "" });
    }).catch((error) => {
      if (!active) return;
      setPoints([]);
      setDataState({ status: "error", source: "station", message: error.message || "权威趋势数据源不可用" });
    });
    return () => { active = false; };
  }, [range, refreshNonce, selectedDevice, stationId]);

  useEffect(() => {
    if (range !== "realtime") return undefined;
    const scope = selectedDevice || stationId;
    const controller = new AbortController();
    const append = async () => {
      try {
        const incoming = await loadLatestEnergyPoint(scope, controller.signal);
        setPoints((current) => mergeEnergyPoints(current, incoming, 3000));
      } catch (error) {
        if (error.name !== "AbortError") setDataState((current) => ({ ...current, status: "reconnecting", message: "实时数据连接中断，正在重试" }));
      }
    };
    const timer = window.setInterval(append, 5_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [range, selectedDevice, stationId]);
  const toggleSeries = (key) => setVisible((current) => {
    if (current.has(key) && current.size === 1) return current;
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  return (
    <section className="energy-flow-trend" aria-label="能量流量趋势">
      <header>
        <div><b>能量流向趋势</b><small>ENERGY FLOW TREND · {selectedDevice || "全站"}</small></div>
        <div className="energy-range" role="tablist" aria-label="趋势时间范围">{["realtime", "6h", "24h", "7d", "30d"].map((item) => <button role="tab" aria-selected={range === item} className={range === item ? "active" : ""} type="button" key={item} onClick={() => onRangeChange(item)}>{item === "realtime" ? "实时" : item}</button>)}</div>
        <div className="energy-legend">{ENERGY_SERIES.map((series) => <button type="button" key={series.key} className={visible.has(series.key) ? "active" : ""} onClick={() => toggleSeries(series.key)}><i style={{ background: series.color }} />{series.label}</button>)}</div>
        <span className={`energy-freshness ${delayed ? "delayed" : ""}`}><i /><span>{freshnessLabel}</span></span>
      </header>
      {dataState.status === "loading" && <div className="energy-state loading" aria-live="polite">正在加载趋势数据</div>}
      {dataState.status === "empty" && <div className="energy-state"><span>{dataState.message}</span><button type="button" onClick={() => setRefreshNonce((value) => value + 1)}><RefreshCw size={12} />重试</button></div>}
      {["error", "reconnecting"].includes(dataState.status) && <div className="energy-state warning"><span>{dataState.message}</span><button type="button" onClick={() => setRefreshNonce((value) => value + 1)}><RefreshCw size={12} />重试真实数据</button></div>}
      <div className="energy-chart-wrap" ref={chartRef} onPointerMove={(event) => { const rect = chartRef.current.getBoundingClientRect(); setHoverIndex(Math.max(0, Math.min(points.length - 1, Math.round(((event.clientX - rect.left) / rect.width) * (points.length - 1))))); }} onPointerLeave={() => setHoverIndex(null)}>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" role="img" aria-label="光伏、风电、储能、负荷与 SOC 趋势">
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => <line key={ratio} x1={PAD.left} x2={WIDTH - PAD.right} y1={PAD.top + ratio * (HEIGHT - PAD.top - PAD.bottom)} y2={PAD.top + ratio * (HEIGHT - PAD.top - PAD.bottom)} className="energy-grid-line" />)}
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={PAD.top + (100 / 220) * (HEIGHT - PAD.top - PAD.bottom)} y2={PAD.top + (100 / 220) * (HEIGHT - PAD.top - PAD.bottom)} className="energy-zero-line" />
          {ENERGY_SERIES.filter((series) => visible.has(series.key)).map((series) => <path key={series.key} d={linePath(points, series.key, series.rightAxis)} fill="none" stroke={series.color} strokeWidth={series.rightAxis ? 1.5 : 1.15} strokeDasharray={series.rightAxis ? "5 3" : undefined} opacity="0.9" vectorEffect="non-scaling-stroke" />)}
          <text x="4" y="16" className="energy-axis-label">MW</text><text x={WIDTH - 28} y="16" className="energy-axis-label">SOC</text>
          {hoverIndex != null && <line x1={PAD.left + (hoverIndex / Math.max(1, points.length - 1)) * (WIDTH - PAD.left - PAD.right)} x2={PAD.left + (hoverIndex / Math.max(1, points.length - 1)) * (WIDTH - PAD.left - PAD.right)} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="energy-hover-line" />}
        </svg>
        {hoverPoint && <div className="energy-tooltip" style={{ left: `${Math.min(78, Math.max(10, (hoverIndex / points.length) * 100))}%` }}><b>{new Date(hoverPoint.timestamp).toLocaleString("zh-CN", { hour12: false })}</b>{ENERGY_SERIES.filter((series) => visible.has(series.key)).map((series) => <span key={series.key}><i style={{ background: series.color }} />{series.label}<strong>{hoverPoint[series.key]?.toFixed(1) ?? "—"} {series.unit}</strong></span>)}<button type="button" onClick={() => onAskAgent?.(hoverPoint)}><RefreshCw size={12} />询问 Agent</button></div>}
      </div>
      <div className="energy-summary"><span><i style={{ background: "#31c6f4" }} />光伏发电量 <b>{metric(summary.pvMwh)}</b></span><span><i style={{ background: "#3b82f6" }} />风电发电量 <b>{metric(summary.windMwh)}</b></span><span><i style={{ background: "#22c997" }} />充/放电 <b>{metric(summary.chargeMwh)} / {metric(summary.dischargeMwh)}</b></span><span><i style={{ background: "#f5a623" }} />负荷/上网 <b>{metric(summary.loadMwh)} / {metric(summary.gridMwh)}</b></span><span><AlertTriangle size={12} />等效循环 <b>{summary.equivalentCycles.toFixed(2)} 次</b></span></div>
    </section>
  );
}
