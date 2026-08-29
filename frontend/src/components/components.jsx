import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  Search, Bell, Settings, User, ChevronDown, ChevronRight, ChevronUp, ChevronLeft,
  Wind, Sun, BatteryCharging, Zap, Play, Pause, SkipBack, SkipForward, TriangleAlert,
  Flame, Map, LayoutGrid, Layers, Cpu, Crosshair, Target, Eye, Activity, Cloud,
  Thermometer, RefreshCw, Expand, X, Maximize2, Minimize2, Filter, Gauge, Radio,
  SignalHigh, Download, Share2, Info,
  Tag, Camera, Video, Power, Monitor,
  Plus, Minus,
} from "lucide-react";
import { sparklineGeometry } from "../features/chartGeometry";

// ====================== Icons (lucide-react backed; same prop API) ======================
// Maps the legacy `name` keys to lucide components so all existing call-sites keep working.
const LUCIDE = {
  search: Search, bell: Bell, settings: Settings, user: User,
  chevD: ChevronDown, chevR: ChevronRight, chevUp: ChevronUp, chevDn: ChevronDown, chevL: ChevronLeft,
  wind: Wind, sun: Sun, battery: BatteryCharging, bolt: Zap, zap: Zap,
  play: Play, pause: Pause, skipB: SkipBack, skipF: SkipForward,
  alert: TriangleAlert, triangleAlert: TriangleAlert, flame: Flame, map: Map,
  grid: LayoutGrid, layers: Layers, cpu: Cpu, target: Target, crosshair: Crosshair,
  eye: Eye, activity: Activity, cloud: Cloud, thermo: Thermometer, thermometer: Thermometer,
  refresh: RefreshCw, expand: Expand, x: X, maximize: Maximize2, minimize: Minimize2,
  filter: Filter, gauge: Gauge, radio: Radio, signal: SignalHigh,
  download: Download, share: Share2, info: Info,
  tag: Tag, camera: Camera, video: Video, power: Power, monitor: Monitor,
  plus: Plus, minus: Minus,
};

const Icon = ({ name, size = 16, color = "currentColor", strokeWidth = 1.7 }) => {
  const Cmp = LUCIDE[name];
  if (!Cmp) return null;
  return <Cmp size={size} color={color} strokeWidth={strokeWidth} style={{ flexShrink: 0 }} />;
};

// ====================== Sparkline ======================
const Sparkline = ({ data, color = "var(--brand-primary)", fill = true, height = 40 }) => {
  const w = 200, h = height;
  const { points, path, area } = sparklineGeometry(data, w, h);
  if (!points.length) return null;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`sp-grad-${color.replace(/[^a-z0-9]/gi,'')}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#sp-grad-${color.replace(/[^a-z0-9]/gi,'')})`} />}
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" />
      <circle cx={points[points.length-1][0]} cy={points[points.length-1][1]} r="2.5" fill={color}>
        <animate attributeName="r" values="2.5;4;2.5" dur="1.5s" repeatCount="indefinite"/>
      </circle>
    </svg>
  );
};

// ====================== Metric Card ======================
const MetricCard = ({ title, value, unit, trend, sparkline, severity = "normal", icon, sparkColor, valueSize = "var(--text-3xl)" }) => {
  const severityColor = {
    normal: "var(--status-normal)",
    warning: "var(--status-warning)",
    critical: "var(--status-critical)",
  }[severity];
  return (
    <div className="card" style={{padding: "14px 16px", position: "relative", overflow: "hidden"}}>
      <span className="corner-deco tl"/><span className="corner-deco tr"/>
      <span className="corner-deco bl"/><span className="corner-deco br"/>
      <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4}}>
        <div style={{fontSize: "var(--text-sm)", color: "var(--text-secondary)", letterSpacing: "0.05em"}}>{title}</div>
        {icon && <div style={{color: severityColor, opacity: 0.7}}><Icon name={icon} size={16}/></div>}
      </div>
      <div style={{display: "flex", alignItems: "baseline", gap: 8, marginTop: 6}}>
        <span className="display-num" style={{fontSize: valueSize}}>{value}</span>
        {unit && <span style={{color: "var(--text-secondary)", fontSize: "var(--text-sm)", fontFamily: "var(--ff-mono)"}}>{unit}</span>}
        {trend && (
          <span style={{
            marginLeft: "auto", fontSize: "var(--text-xs)",
            color: trend.direction === "up" ? "var(--status-normal)" : trend.direction === "down" ? "var(--status-critical)" : "var(--text-tertiary)",
            display: "inline-flex", alignItems: "center", gap: 2,
            fontFamily: "var(--ff-mono)"
          }}>
            {trend.direction === "up" ? "↗" : trend.direction === "down" ? "↘" : "→"} {trend.value}
          </span>
        )}
      </div>
      {sparkline && <div style={{marginTop: 8}}><Sparkline data={sparkline} color={sparkColor || severityColor}/></div>}
    </div>
  );
};

// ====================== Status pill ======================
const StatusPill = ({ severity, label }) => (
  <span className={`pill ${severity}`}>
    <span className="dot"/>{label}
  </span>
);

// ====================== Range Slider (dual handle) ======================
const RangeSlider = ({ min = 10, max = 60, value = [10, 60], onChange, unit = "℃", colorGradient }) => {
  const trackRef = useRef(null);
  const [drag, setDrag] = useState(null); // 'lo' | 'hi' | null
  const [hover, setHover] = useState(null);

  const pct = (v) => ((v - min) / (max - min)) * 100;

  useEffect(() => {
    if (!drag) return;
    const move = (e) => {
      const rect = trackRef.current.getBoundingClientRect();
      const p = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const v = Math.round(min + p * (max - min));
      const [lo, hi] = value;
      if (drag === "lo") onChange([Math.min(v, hi - 1), hi]);
      else onChange([lo, Math.max(v, lo + 1)]);
    };
    const up = () => setDrag(null);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [drag, value, onChange, min, max]);

  return (
    <div style={{padding: "4px 0"}}>
      {/* track */}
      <div ref={trackRef} className="range-track" style={{margin: "8px 8px 4px"}}>
        <div className="range-fill" style={{left: `${pct(value[0])}%`, right: `${100 - pct(value[1])}%`}}/>
        <div className="range-handle" style={{left: `${pct(value[0])}%`}}
             onMouseDown={() => setDrag("lo")}
             onMouseEnter={() => setHover("lo")} onMouseLeave={() => setHover(null)}>
          {(drag === "lo" || hover === "lo") && (
            <div style={{position:"absolute", bottom:18, left:"50%", transform:"translateX(-50%)", background:"rgba(10,14,26,0.96)", border:"1px solid var(--brand-primary)", borderRadius:4, padding:"2px 6px", fontSize:10, fontFamily:"var(--ff-mono)", color:"#00d4ff", whiteSpace:"nowrap"}}>{value[0]}{unit}</div>
          )}
        </div>
        <div className="range-handle" style={{left: `${pct(value[1])}%`}}
             onMouseDown={() => setDrag("hi")}
             onMouseEnter={() => setHover("hi")} onMouseLeave={() => setHover(null)}>
          {(drag === "hi" || hover === "hi") && (
            <div style={{position:"absolute", bottom:18, left:"50%", transform:"translateX(-50%)", background:"rgba(10,14,26,0.96)", border:"1px solid var(--brand-primary)", borderRadius:4, padding:"2px 6px", fontSize:10, fontFamily:"var(--ff-mono)", color:"#00d4ff", whiteSpace:"nowrap"}}>{value[1]}{unit}</div>
          )}
        </div>
      </div>
      <div style={{display:"flex", justifyContent:"space-between", fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", padding:"0 4px"}}>
        <span>{min}{unit}</span>
        <span style={{color:"var(--brand-primary)"}}>{value[0]} — {value[1]}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
};

// ====================== Gas Gauge (concentration bar) ======================
const GasGauge = ({ name, formula, value, unit, threshold, color = "#00d4ff", warn = false }) => {
  const pct = Math.min(100, (value / threshold) * 100);
  const sev = pct > 100 ? "critical" : pct > 70 ? "warning" : "normal";
  const sevColor = sev === "critical" ? "#ef4444" : sev === "warning" ? "#f59e0b" : color;
  return (
    <div style={{padding: "6px 0"}}>
      <div style={{display:"flex", alignItems:"baseline", justifyContent:"space-between", marginBottom: 3}}>
        <div style={{display:"flex", alignItems:"baseline", gap:6}}>
          <span style={{fontSize:11, color:"var(--text-secondary)"}}>{name}</span>
          <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>{formula}</span>
        </div>
        <span style={{fontSize:11, fontFamily:"var(--ff-mono)", color: sevColor, fontWeight:600}}>
          {value} <span style={{fontSize:9, color:"var(--text-tertiary)"}}>{unit}</span>
        </span>
      </div>
      <div style={{height: 4, background:"#1f2738", borderRadius: 2, position:"relative", overflow:"hidden"}}>
        <div style={{position:"absolute", left:0, top:0, bottom:0, width:`${pct}%`, background: sevColor, borderRadius:2, boxShadow: `0 0 6px ${sevColor}`, transition:"width 400ms ease"}}/>
        {/* threshold tick */}
        <div style={{position:"absolute", left:"100%", top:-1, bottom:-1, width:1, background:"var(--text-tertiary)", opacity:0.6}}/>
      </div>
      <div style={{display:"flex", justifyContent:"space-between", fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", marginTop: 2}}>
        <span>0</span><span>阈值 {threshold}</span>
      </div>
    </div>
  );
};

// ====================== Mini segmented bar ======================
const SegmentedBar = ({ segments }) => {
  const total = segments.reduce((s, x) => s + x.value, 0);
  return (
    <div>
      <div style={{display:"flex", height:14, borderRadius:3, overflow:"hidden", border:"1px solid var(--border-divider)"}}>
        {segments.map((s, i) => (
          <div key={i} title={`${s.label}: ${s.value}`} style={{
            flex: s.value / total,
            background: s.color,
            boxShadow: `inset 0 0 6px ${s.color}80`,
            transition: "flex 400ms ease"
          }}/>
        ))}
      </div>
      <div style={{display:"flex", flexWrap:"wrap", gap:"6px 12px", marginTop:8, fontSize:10, fontFamily:"var(--ff-mono)"}}>
        {segments.map((s, i) => (
          <div key={i} style={{display:"flex", alignItems:"center", gap:5}}>
            <span style={{width:8, height:8, background:s.color, borderRadius:2, boxShadow:`0 0 4px ${s.color}`}}/>
            <span style={{color:"var(--text-secondary)"}}>{s.label}</span>
            <span style={{color:"var(--text-primary)", fontWeight:600}}>{s.value}</span>
            <span style={{color:"var(--text-tertiary)"}}>({((s.value/total)*100).toFixed(0)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ====================== Camera Feed (placeholder with effects) ======================
const CameraFeed = ({ name, location, status = "live", scanLine = true, selected = false, onClick, severity = "normal" }) => {
  const sevColor = severity === "critical" ? "#ef4444" : severity === "warning" ? "#f59e0b" : "#10b981";
  return (
    <div onClick={onClick} style={{
      position: "relative",
      border: `1px solid ${selected ? "var(--brand-primary)" : "var(--border-primary)"}`,
      borderRadius: "var(--r-md)",
      overflow: "hidden",
      cursor: "pointer",
      background: "#0a0e1a",
      boxShadow: selected ? "var(--glow-primary)" : "none",
      transition: "all 200ms ease",
      aspectRatio: "16 / 9",
    }}>
      {/* Simulated camera content */}
      <svg viewBox="0 0 320 180" width="100%" height="100%" preserveAspectRatio="xMidYMid slice" style={{display:"block"}}>
        <defs>
          <linearGradient id={`cam-${name}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#1a2540"/>
            <stop offset="100%" stopColor="#050810"/>
          </linearGradient>
        </defs>
        <rect width="320" height="180" fill={`url(#cam-${name})`}/>
        {/* ground */}
        <path d="M 0 130 L 60 100 L 260 100 L 320 130 L 320 180 L 0 180 Z" fill="#0a1124" stroke="#1f2738"/>
        {/* container shapes */}
        <rect x="60" y="80" width="64" height="34" fill="#1e293b" stroke={sevColor} strokeWidth="0.6"/>
        <rect x="135" y="78" width="64" height="36" fill="#1e293b" stroke="#475569" strokeWidth="0.5"/>
        <rect x="210" y="80" width="64" height="34" fill="#1e293b" stroke="#475569" strokeWidth="0.5"/>
        {/* alarm highlight */}
        {severity === "critical" && (
          <rect x="58" y="78" width="68" height="38" fill="none" stroke="#ef4444" strokeWidth="1.5">
            <animate attributeName="opacity" values="1;0.3;1" dur="1s" repeatCount="indefinite"/>
          </rect>
        )}
        {/* scan line */}
        {scanLine && (
          <rect x="0" width="320" height="2" fill="rgba(0,212,255,0.4)">
            <animate attributeName="y" values="0;180;0" dur="6s" repeatCount="indefinite"/>
          </rect>
        )}
        {/* noise dots */}
        {Array.from({length: 20}).map((_, i) => (
          <circle key={i} cx={Math.random()*320} cy={Math.random()*180} r="0.5" fill="#fff" opacity={Math.random()*0.3}/>
        ))}
      </svg>

      {/* overlay header */}
      <div style={{position:"absolute", top:6, left:8, right:8, display:"flex", justifyContent:"space-between", alignItems:"center", fontSize:10, fontFamily:"var(--ff-mono)"}}>
        <span style={{display:"flex", alignItems:"center", gap:4, color:"#ef4444", fontWeight:600}}>
          <span style={{width:6, height:6, borderRadius:"50%", background:"#ef4444", boxShadow:"0 0 6px #ef4444", animation:"pulse-soft 1s ease-in-out infinite"}}/>
          REC
        </span>
        <span style={{color:"var(--text-secondary)", background:"rgba(0,0,0,0.6)", padding:"1px 5px", borderRadius:3}}>{name}</span>
      </div>
      {/* overlay footer */}
      <div style={{position:"absolute", bottom:4, left:8, right:8, fontSize:10, fontFamily:"var(--ff-mono)", color:"var(--text-secondary)", display:"flex", justifyContent:"space-between", alignItems:"center", textShadow:"0 1px 2px #000"}}>
        <span>{location}</span>
        <span>{new Date().toLocaleTimeString("zh-CN", {hour12:false})}</span>
      </div>
    </div>
  );
};

// ====================== Toast ======================
const Toast = ({ title, desc, severity = "critical", time, onClose, onLocate }) => (
  <div className={`card toast ${severity}`}>
    <div style={{display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 16px", borderBottom:"1px solid var(--border-divider)"}}>
      <div style={{display:"flex", alignItems:"center", gap:10}}>
        <span style={{width:8, height:8, borderRadius:"50%", background: "var(--status-critical)", boxShadow:"0 0 12px var(--status-critical)", animation:"pulse-soft 1s ease-in-out infinite"}}/>
        <span style={{color: "var(--status-critical)", fontWeight:600, fontSize:"var(--text-sm)", letterSpacing:"0.05em"}}>严重告警 · CRITICAL</span>
      </div>
      <button onClick={onClose} style={{background:"none", border:"none", color:"var(--text-tertiary)", cursor:"pointer"}}><Icon name="x" size={14}/></button>
    </div>
    <div style={{padding:"12px 16px"}}>
      <div style={{fontSize:"var(--text-md)", fontWeight:600, marginBottom:6}}>{title}</div>
      <div style={{fontSize:"var(--text-sm)", color:"var(--text-secondary)", lineHeight:1.6}}>
        {desc.map((line, i) => <div key={i}>· {line}</div>)}
      </div>
      <div style={{fontSize:"var(--text-xs)", color:"var(--text-tertiary)", marginTop:8, fontFamily:"var(--ff-mono)"}}>发生时间：{time}</div>
    </div>
    <div style={{display:"flex", gap:8, padding:"10px 16px", borderTop:"1px solid var(--border-divider)"}}>
      <button className="btn primary" style={{height:28, fontSize:"var(--text-xs)"}} onClick={onLocate}>立即定位</button>
      <button className="btn" style={{height:28, fontSize:"var(--text-xs)"}}>查看详情</button>
      <div style={{flex:1}}/>
      <button className="btn" style={{height:28, fontSize:"var(--text-xs)"}} onClick={onClose}>忽略</button>
    </div>
  </div>
);


export { Icon, Sparkline, MetricCard, StatusPill, RangeSlider, GasGauge, SegmentedBar, CameraFeed, Toast };
