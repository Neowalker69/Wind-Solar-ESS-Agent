import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";

// ====================== Energy Chart (dual line) ======================
const EnergyChart = ({ width = 1500, height = 180, range = "24h" }) => {
  // Generate series
  const data = useMemo(() => {
    const n = 96; // 15-min intervals over 24h
    const grid = [], sub = [], solar = [], wind = [];
    for (let i = 0; i < n; i++) {
      const t = i / n;
      // solar: bell curve centered around noon
      const solarV = Math.max(0, 28 * Math.exp(-Math.pow((t - 0.5) * 4, 2)) + (Math.random() - 0.5) * 2);
      // wind: more variable
      const windV = 12 + Math.sin(t * Math.PI * 3) * 6 + Math.cos(t * Math.PI * 7) * 3 + Math.random() * 2;
      // grid demand
      const demand = 60 + Math.sin((t - 0.2) * Math.PI * 2) * 18 + (t > 0.7 && t < 0.95 ? 10 : 0);
      grid.push(demand);
      sub.push(solarV + windV);
      solar.push(solarV);
      wind.push(Math.max(0, windV));
    }
    return { grid, sub, solar, wind };
  }, [range]);

  const padding = { l: 50, r: 30, t: 16, b: 28 };
  const W = width, H = height;
  const inner = { w: W - padding.l - padding.r, h: H - padding.t - padding.b };
  const allVals = [...data.grid, ...data.sub];
  const yMin = 0, yMax = Math.max(...allVals) * 1.1;

  const xy = (vals) => vals.map((v, i) => {
    const x = padding.l + (i / (vals.length - 1)) * inner.w;
    const y = padding.t + inner.h - ((v - yMin) / (yMax - yMin)) * inner.h;
    return [x, y];
  });

  const toPath = (pts) => "M " + pts.map(p => p.join(" ")).join(" L ");
  const toArea = (pts) => toPath(pts) + ` L ${pts[pts.length-1][0]} ${padding.t + inner.h} L ${pts[0][0]} ${padding.t + inner.h} Z`;

  const ptsGrid = xy(data.grid);
  const ptsSub = xy(data.sub);
  const ptsSolar = xy(data.solar);
  const ptsWind = xy(data.wind);

  // hover state
  const [hoverIdx, setHoverIdx] = useState(48); // noon

  const onMove = (e) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((x - padding.l) / inner.w) * (data.grid.length - 1));
    if (i >= 0 && i < data.grid.length) setHoverIdx(i);
  };

  const timeLabels = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"];

  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
         onMouseMove={onMove}
         style={{cursor:"crosshair"}}>
      <defs>
        <linearGradient id="gridArea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4"/>
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0"/>
        </linearGradient>
        <linearGradient id="subArea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.4"/>
          <stop offset="100%" stopColor="#00d4ff" stopOpacity="0"/>
        </linearGradient>
      </defs>

      {/* y grid */}
      {[0, 0.25, 0.5, 0.75, 1].map(p => {
        const y = padding.t + inner.h * (1 - p);
        const v = Math.round(yMin + (yMax - yMin) * p);
        return (
          <g key={p}>
            <line x1={padding.l} x2={W - padding.r} y1={y} y2={y} stroke="#1f2738" strokeWidth="0.5" strokeDasharray="2 3"/>
            <text x={padding.l - 8} y={y + 3} fontSize="10" fill="#5d6885" fontFamily="JetBrains Mono" textAnchor="end">{v}</text>
          </g>
        );
      })}

      {/* x labels */}
      {timeLabels.map((t, i) => {
        const x = padding.l + (i / (timeLabels.length - 1)) * inner.w;
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={padding.t + inner.h} y2={padding.t + inner.h + 4} stroke="#2a3245" strokeWidth="0.5"/>
            <text x={x} y={padding.t + inner.h + 18} fontSize="10" fill="#5d6885" fontFamily="JetBrains Mono" textAnchor="middle">{t}</text>
          </g>
        );
      })}

      {/* y-axis label */}
      <text x={padding.l - 36} y={padding.t + 8} fontSize="10" fill="#5d6885" fontFamily="JetBrains Mono">MW</text>

      {/* Areas */}
      <path d={toArea(ptsGrid)} fill="url(#gridArea)"/>
      <path d={toArea(ptsSub)} fill="url(#subArea)"/>

      {/* Lines */}
      <path d={toPath(ptsGrid)} fill="none" stroke="#3b82f6" strokeWidth="1.5"/>
      <path d={toPath(ptsSub)} fill="none" stroke="#00d4ff" strokeWidth="1.5"/>
      <path d={toPath(ptsSolar)} fill="none" stroke="#facc15" strokeWidth="1" opacity="0.7" strokeDasharray="2 2"/>
      <path d={toPath(ptsWind)} fill="none" stroke="#10b981" strokeWidth="1" opacity="0.7" strokeDasharray="2 2"/>

      {/* Hover line + dots */}
      {hoverIdx != null && (
        <g>
          <line x1={ptsGrid[hoverIdx][0]} x2={ptsGrid[hoverIdx][0]} y1={padding.t} y2={padding.t + inner.h}
                stroke="#00d4ff" strokeWidth="0.8" strokeDasharray="3 3" opacity="0.5"/>
          <circle cx={ptsGrid[hoverIdx][0]} cy={ptsGrid[hoverIdx][1]} r="3.5" fill="#3b82f6" stroke="#0a0e1a" strokeWidth="1"/>
          <circle cx={ptsSub[hoverIdx][0]} cy={ptsSub[hoverIdx][1]} r="3.5" fill="#00d4ff" stroke="#0a0e1a" strokeWidth="1"/>

          {/* tooltip */}
          {(() => {
            const x = ptsGrid[hoverIdx][0];
            const right = x > W * 0.65;
            const tx = right ? x - 150 : x + 12;
            const ty = padding.t + 10;
            const hh = Math.floor((hoverIdx / data.grid.length) * 24);
            const mm = Math.round(((hoverIdx / data.grid.length) * 24 - hh) * 60);
            return (
              <g>
                <rect x={tx} y={ty} width="138" height="74" fill="rgba(10,14,26,0.95)" stroke="#00d4ff" strokeWidth="0.5" rx="3"/>
                <text x={tx + 8} y={ty + 14} fontSize="10" fill="#9aa5bf" fontFamily="JetBrains Mono">
                  {String(hh).padStart(2,'0')}:{String(mm).padStart(2,'0')}
                </text>
                <line x1={tx + 8} x2={tx + 130} y1={ty + 18} y2={ty + 18} stroke="#2a3245"/>
                <g fontSize="10" fontFamily="JetBrains Mono">
                  <circle cx={tx + 12} cy={ty + 30} r="3" fill="#3b82f6"/>
                  <text x={tx + 20} y={ty + 33} fill="#9aa5bf">电网需求</text>
                  <text x={tx + 130} y={ty + 33} fill="#e6ebf5" textAnchor="end" fontWeight="600">{Math.round(data.grid[hoverIdx])} MW</text>

                  <circle cx={tx + 12} cy={ty + 44} r="3" fill="#00d4ff"/>
                  <text x={tx + 20} y={ty + 47} fill="#9aa5bf">新能源出力</text>
                  <text x={tx + 130} y={ty + 47} fill="#e6ebf5" textAnchor="end" fontWeight="600">{Math.round(data.sub[hoverIdx])} MW</text>

                  <circle cx={tx + 12} cy={ty + 58} r="3" fill="#facc15"/>
                  <text x={tx + 20} y={ty + 61} fill="#9aa5bf">光伏</text>
                  <text x={tx + 130} y={ty + 61} fill="#e6ebf5" textAnchor="end" fontWeight="600">{Math.round(data.solar[hoverIdx])} MW</text>
                </g>
              </g>
            );
          })()}
        </g>
      )}

      {/* "Now" line */}
      <g>
        <line x1={padding.l + (48/95) * inner.w} x2={padding.l + (48/95) * inner.w}
              y1={padding.t} y2={padding.t + inner.h}
              stroke="#f59e0b" strokeWidth="1" strokeDasharray="4 3" opacity="0.8"/>
        <text x={padding.l + (48/95) * inner.w + 6} y={padding.t + 12} fontSize="9" fill="#f59e0b" fontFamily="JetBrains Mono">NOW</text>
      </g>

      {/* Event markers on x-axis */}
      <g>
        <circle cx={padding.l + (30/95) * inner.w} cy={padding.t + inner.h + 2} r="3" fill="#ef4444">
          <animate attributeName="r" values="3;5;3" dur="1.5s" repeatCount="indefinite"/>
        </circle>
        <circle cx={padding.l + (60/95) * inner.w} cy={padding.t + inner.h + 2} r="3" fill="#f59e0b"/>
        <circle cx={padding.l + (74/95) * inner.w} cy={padding.t + inner.h + 2} r="3" fill="#f59e0b"/>
      </g>
    </svg>
  );
};

// ====================== Donut Chart for energy mix ======================
const DonutChart = ({ data, size = 100 }) => {
  const total = data.reduce((s, d) => s + d.value, 0);
  let acc = 0;
  const r = size / 2 - 8;
  const cx = size / 2, cy = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1f2738" strokeWidth="12"/>
      {data.map((d, i) => {
        const start = acc / total;
        acc += d.value;
        const end = acc / total;
        const a1 = start * Math.PI * 2 - Math.PI / 2;
        const a2 = end * Math.PI * 2 - Math.PI / 2;
        const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
        const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
        const large = end - start > 0.5 ? 1 : 0;
        return (
          <path key={i} d={`M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`}
                fill="none" stroke={d.color} strokeWidth="12" strokeLinecap="round"
                style={{filter: `drop-shadow(0 0 6px ${d.color})`}}/>
        );
      })}
    </svg>
  );
};

// ====================== Scatter Plot (cell extremes) ======================
const ScatterExtreme = ({ width = 320, height = 180 }) => {
  // each point = one cell: x = cluster idx, y = temp; size = abs diff from cluster median
  const data = useMemo(() => {
    const pts = [];
    for (let c = 0; c < 10; c++) {
      // cluster c has different median
      const median = c === 2 ? 52 : c === 6 ? 41 : 28 + Math.random() * 4;
      const n = 18;
      for (let i = 0; i < n; i++) {
        const offset = (Math.random() - 0.5) * (c === 2 ? 14 : c === 6 ? 8 : 3);
        pts.push({ cluster: c, temp: median + offset, isExtreme: Math.abs(offset) > 5 });
      }
    }
    return pts;
  }, []);
  const padding = {l: 32, r: 12, t: 12, b: 24};
  const inner = {w: width - padding.l - padding.r, h: height - padding.t - padding.b};
  const yMin = 10, yMax = 60;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
      {/* grid */}
      {[0, 0.25, 0.5, 0.75, 1].map(p => {
        const y = padding.t + inner.h * (1-p);
        const v = Math.round(yMin + (yMax - yMin) * p);
        return (
          <g key={p}>
            <line x1={padding.l} x2={width-padding.r} y1={y} y2={y} stroke="#1f2738" strokeDasharray="2 3" strokeWidth="0.5"/>
            <text x={padding.l - 6} y={y+3} fontSize="9" fontFamily="JetBrains Mono" fill="#5d6885" textAnchor="end">{v}℃</text>
          </g>
        );
      })}
      {/* X labels (cluster) */}
      {Array.from({length: 10}).map((_, c) => {
        const x = padding.l + (c / 9) * inner.w;
        return (
          <text key={c} x={x} y={height - 6} fontSize="9" fontFamily="JetBrains Mono" fill="#5d6885" textAnchor="middle">A-{String(c+1).padStart(2,'0')}</text>
        );
      })}
      {/* threshold lines */}
      <line x1={padding.l} x2={width-padding.r}
            y1={padding.t + inner.h - ((45-yMin)/(yMax-yMin))*inner.h}
            y2={padding.t + inner.h - ((45-yMin)/(yMax-yMin))*inner.h}
            stroke="#f59e0b" strokeDasharray="3 3" strokeWidth="0.6" opacity="0.6"/>
      <text x={width-padding.r-2} y={padding.t + inner.h - ((45-yMin)/(yMax-yMin))*inner.h - 3}
            fontSize="8" fill="#f59e0b" fontFamily="JetBrains Mono" textAnchor="end">告警 45℃</text>
      {/* points */}
      {data.map((p, i) => {
        const x = padding.l + (p.cluster / 9) * inner.w + (Math.random()-0.5)*8;
        const y = padding.t + inner.h - ((p.temp-yMin)/(yMax-yMin))*inner.h;
        const c = p.temp > 50 ? "#ef4444" : p.temp > 40 ? "#f97316" : p.temp > 35 ? "#facc15" : p.temp > 25 ? "#10b981" : "#06b6d4";
        return (
          <circle key={i} cx={x} cy={y} r={p.isExtreme ? 3 : 1.5} fill={c}
                  opacity={p.isExtreme ? 0.95 : 0.55}
                  style={p.isExtreme ? {filter: `drop-shadow(0 0 4px ${c})`} : {}}>
            {p.isExtreme && <animate attributeName="r" values={`3;${4.5};3`} dur="1.6s" repeatCount="indefinite"/>}
          </circle>
        );
      })}
    </svg>
  );
};

// ====================== Multi-series realtime (overview) ======================
const RealtimeMultiLine = ({ height = 60, data, colors }) => {
  const w = 320;
  const padding = {l: 4, r: 4, t: 6, b: 4};
  const inner = {w: w - padding.l - padding.r, h: height - padding.t - padding.b};
  const keys = Object.keys(data).filter((key) => data[key].some(Number.isFinite));

  const allValues = keys.flatMap((key) => data[key]).filter(Number.isFinite);
  const yMin = Math.min(...allValues, 0);
  const yMax = Math.max(...allValues, 1);
  const yRange = yMax - yMin || 1;

  const xy = (vals) => vals.filter(Number.isFinite).map((v, i, finiteValues) => {
    const x = padding.l + (finiteValues.length === 1 ? 0.5 : i / (finiteValues.length - 1)) * inner.w;
    const y = padding.t + inner.h - ((v - yMin) / yRange) * inner.h;
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
      <defs>
        {keys.map((key) => <linearGradient key={key} id={`multi-${key}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={colors[key]} stopOpacity="0.4"/>
          <stop offset="100%" stopColor={colors[key]} stopOpacity="0"/>
        </linearGradient>)}
      </defs>

      {/* area fills (last point markers + lines) */}
      {keys.map(k => (
        <polyline key={k} points={xy(data[k])} fill="none" stroke={colors[k]} strokeWidth="1.2"
                  style={{filter: `drop-shadow(0 0 3px ${colors[k]})`}}/>
      ))}
      {/* End dots */}
      {keys.map(k => {
        const values = data[k].filter(Number.isFinite);
        const v = values.at(-1);
        const x = padding.l + (values.length === 1 ? inner.w / 2 : inner.w);
        const y = padding.t + inner.h - ((v - yMin) / yRange) * inner.h;
        return (
          <circle key={k} cx={x-2} cy={y} r="2" fill={colors[k]}>
            <animate attributeName="r" values="2;3.5;2" dur="1.5s" repeatCount="indefinite"/>
          </circle>
        );
      })}
    </svg>
  );
};

// ====================== Vertical Temperature Range (gradient = range slider) ======================
const VerticalTempRange = ({ min = 10, max = 60, value = [10, 60], onChange, active = true }) => {
  const trackRef = useRef(null);
  const [drag, setDrag] = useState(null); // 'lo' | 'hi' | null

  // Vertical: top = max, bottom = min
  const pct = (v) => ((max - v) / (max - min)) * 100;

  useEffect(() => {
    if (!drag) return;
    const move = (e) => {
      if (!trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      const p = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
      const v = Math.round(max - p * (max - min));
      const [lo, hi] = value;
      if (drag === "lo") onChange([Math.min(v, hi - 1), hi]);
      else onChange([lo, Math.max(v, lo + 1)]);
    };
    const up = () => setDrag(null);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [drag, value, onChange, min, max]);

  // ticks: every 10 deg
  const ticks = [];
  for (let v = min; v <= max; v += 10) ticks.push(v);

  // Y positions for handles (0% = top = max, 100% = bottom = min)
  const yHi = pct(value[1]); // top handle
  const yLo = pct(value[0]); // bottom handle

  return (
    <div style={{display:"flex", gap:14, alignItems:"stretch", padding:"4px 0"}}>
      {/* Track */}
      <div ref={trackRef}
           style={{
             position:"relative", width: 14,
             height: 160,
             borderRadius: 7,
             background: "linear-gradient(to top, #1e3a8a 0%, #1e40af 11%, #3b82f6 22%, #06b6d4 33%, #10b981 44%, #84cc16 56%, #facc15 67%, #f97316 78%, #ef4444 89%, #b91c1c 100%)",
             boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.08), inset 0 0 12px rgba(0,0,0,0.4)",
             cursor: active ? "pointer" : "default",
           }}
           onMouseDown={active ? (e) => {
             // click on track moves nearest handle
             const rect = trackRef.current.getBoundingClientRect();
             const p = (e.clientY - rect.top) / rect.height;
             const v = Math.round(max - p * (max - min));
             const distLo = Math.abs(v - value[0]);
             const distHi = Math.abs(v - value[1]);
             setDrag(distLo < distHi ? "lo" : "hi");
           } : undefined}>
        {/* dimming mask above hi (out of range — hot side) */}
        <div style={{
          position:"absolute", left:0, right:0, top:0,
          height: `${yHi}%`,
          background: "rgba(5,8,15,0.7)",
          borderRadius: "7px 7px 0 0",
          transition: drag ? "none" : "height 200ms ease",
        }}/>
        {/* dimming mask below lo (out of range — cold side) */}
        <div style={{
          position:"absolute", left:0, right:0, bottom:0,
          height: `${100 - yLo}%`,
          background: "rgba(5,8,15,0.7)",
          borderRadius: "0 0 7px 7px",
          transition: drag ? "none" : "height 200ms ease",
        }}/>

        {/* High handle */}
        <div onMouseDown={active ? (e) => { e.stopPropagation(); setDrag("hi"); } : undefined}
             style={{
               position:"absolute", left:"50%", top:`${yHi}%`,
               transform:"translate(-50%, -50%)",
               width: 26, height: 14, borderRadius: 4,
               background: "#0a0e1a",
               border: "1.5px solid var(--brand-primary)",
               boxShadow: "0 0 10px rgba(0,212,255,0.7), inset 0 0 4px rgba(0,212,255,0.3)",
               cursor: active ? (drag === "hi" ? "grabbing" : "grab") : "default",
               display: "flex", alignItems: "center", justifyContent: "center",
               opacity: active ? 1 : 0.5,
             }}>
          <span style={{fontSize:9, fontFamily:"var(--ff-mono)", color:"var(--brand-primary)", fontWeight:700, letterSpacing:"-0.05em"}}>
            {value[1]}°
          </span>
        </div>

        {/* Low handle */}
        <div onMouseDown={active ? (e) => { e.stopPropagation(); setDrag("lo"); } : undefined}
             style={{
               position:"absolute", left:"50%", top:`${yLo}%`,
               transform:"translate(-50%, -50%)",
               width: 26, height: 14, borderRadius: 4,
               background: "#0a0e1a",
               border: "1.5px solid var(--brand-primary)",
               boxShadow: "0 0 10px rgba(0,212,255,0.7), inset 0 0 4px rgba(0,212,255,0.3)",
               cursor: active ? (drag === "lo" ? "grabbing" : "grab") : "default",
               display: "flex", alignItems: "center", justifyContent: "center",
               opacity: active ? 1 : 0.5,
             }}>
          <span style={{fontSize:9, fontFamily:"var(--ff-mono)", color:"var(--brand-primary)", fontWeight:700, letterSpacing:"-0.05em"}}>
            {value[0]}°
          </span>
        </div>
      </div>

      {/* Tick scale */}
      <div style={{position:"relative", height: 160, display:"flex", flexDirection:"column", justifyContent:"space-between", fontFamily:"var(--ff-mono)", fontSize: 10}}>
        {ticks.slice().reverse().map((v, i) => {
          const inRange = v >= value[0] && v <= value[1];
          return (
            <div key={v} style={{display:"flex", alignItems:"center", gap:4, lineHeight:1}}>
              <span style={{width:6, height:1, background: inRange ? "var(--brand-primary)" : "var(--text-tertiary)", opacity: inRange ? 1 : 0.5}}/>
              <span style={{color: inRange ? "var(--text-secondary)" : "var(--text-tertiary)", opacity: inRange ? 1 : 0.6}}>{v}℃</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ====================== Temperature bar (legacy horizontal, kept for back-compat) ======================
const TempBar = () => {
  const stops = ["#1e3a8a","#1e40af","#3b82f6","#06b6d4","#10b981","#84cc16","#facc15","#f97316","#ef4444","#b91c1c"];
  return (
    <div style={{display:"flex", flexDirection:"column", gap:6}}>
      <div style={{display:"flex", justifyContent:"space-between", fontSize:"var(--text-xs)", color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>
        <span>10℃</span><span>30℃</span><span>55℃+</span>
      </div>
      <div style={{display:"flex", height:8, borderRadius:4, overflow:"hidden"}}>
        {stops.map((c, i) => <div key={i} style={{flex:1, background:c}}/>)}
      </div>
    </div>
  );
};


export { EnergyChart, DonutChart, ScatterExtreme, RealtimeMultiLine, VerticalTempRange, TempBar };
