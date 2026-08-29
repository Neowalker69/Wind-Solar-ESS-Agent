import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { Icon } from "./components";

// ===================== LiveClock (local copy for video view) =====================
const LiveClock = ({ style }) => {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString("zh-CN", { hour12: false }));
  useEffect(() => {
    const t = setInterval(() => setTime(new Date().toLocaleTimeString("zh-CN", { hour12: false })), 1000);
    return () => clearInterval(t);
  }, []);
  return <span style={style}>{time}</span>;
};

// ===================== Video Monitoring view + panel =====================

// ------- Camera scene SVG per location type (so feeds look different) -------
const CameraSceneSVG = ({ type = "storage", severity = "normal" }) => {
  const sevColor = severity === "critical" ? "#ef4444" : severity === "warning" ? "#f59e0b" : "#10b981";

  // Each scene is rendered into 320x180 viewBox
  if (type === "storage") {
    return (
      <>
        {/* sky / floor */}
        <rect x="0" y="0" width="320" height="180" fill="#0a1124"/>
        <path d="M 0 120 L 80 90 L 240 90 L 320 120 L 320 180 L 0 180 Z" fill="#0f1828" stroke="#1f2738" strokeWidth="0.5"/>
        {/* line markings on ground */}
        <path d="M 0 145 L 320 130" stroke="#1f2738" strokeWidth="0.4" strokeDasharray="2 4"/>
        {/* containers */}
        {[40, 110, 180, 250].map((x, i) => (
          <g key={i}>
            <rect x={x} y={62} width="56" height="32" fill="#1e293b"
              stroke={i === 1 ? sevColor : "#475569"} strokeWidth={i === 1 ? 1.5 : 0.6}/>
            {/* ridges */}
            {[0.25, 0.5, 0.75].map(p => (
              <line key={p} x1={x + 56*p} y1="64" x2={x + 56*p} y2="92" stroke="#0a0e1a" strokeWidth="0.4"/>
            ))}
            {/* label */}
            <rect x={x+4} y={66} width="14" height="5" fill="rgba(0,0,0,0.6)"/>
            <text x={x+11} y={70} fontSize="3.5" fill={i === 1 ? sevColor : "#94a3b8"} textAnchor="middle" fontFamily="JetBrains Mono">A-0{i+2}</text>
            {/* status LED */}
            <circle cx={x+50} cy={68} r="1" fill={i === 1 ? sevColor : "#10b981"}>
              {i === 1 && <animate attributeName="opacity" values="1;0.3;1" dur="0.8s" repeatCount="indefinite"/>}
            </circle>
          </g>
        ))}
        {/* heat shimmer on critical container */}
        {severity === "critical" && (
          <g opacity="0.6">
            {[0, 1, 2].map(i => (
              <circle key={i} cx={110 + 18 + i*8} cy={58} r="1.5" fill="#ef4444">
                <animate attributeName="cy" values={`58;${30 - i*4};58`} dur={`${1.8 + i*0.3}s`} repeatCount="indefinite" begin={`${i*0.5}s`}/>
                <animate attributeName="opacity" values="0.6;0;0.6" dur={`${1.8 + i*0.3}s`} repeatCount="indefinite" begin={`${i*0.5}s`}/>
              </circle>
            ))}
          </g>
        )}
      </>
    );
  }

  if (type === "wind") {
    return (
      <>
        <rect x="0" y="0" width="320" height="180" fill="#0a1428"/>
        {/* horizon */}
        <path d="M 0 140 L 320 130 L 320 180 L 0 180 Z" fill="#0d1828"/>
        {/* turbines */}
        {[
          {x: 90, scale: 1.2, dur: 4},
          {x: 200, scale: 1, dur: 3.5},
          {x: 270, scale: 0.8, dur: 5},
        ].map((t, i) => (
          <g key={i} transform={`translate(${t.x} 140) scale(${t.scale})`}>
            {/* tower */}
            <path d="M -1.5 0 L 1.5 0 L 0.8 -70 L -0.8 -70 Z" fill="#cbd5e1"/>
            {/* hub */}
            <circle cx="0" cy="-72" r="2.5" fill="#94a3b8"/>
            {/* blades */}
            <g style={{transformOrigin: `0 -72px`, animation: `spin-slow ${t.dur}s linear infinite`}}>
              {[0, 120, 240].map(a => (
                <path key={a} d="M 0 -72 Q 3 -84 0 -110 Q -1.5 -84 0 -72"
                  transform={`rotate(${a} 0 -72)`} fill="#e2e8f0"/>
              ))}
            </g>
            {/* status LED */}
            <circle cx="2" cy="-68" r="1" fill={i === 0 && severity === "warning" ? "#f59e0b" : "#10b981"}>
              {i === 0 && severity === "warning" && <animate attributeName="opacity" values="1;0.3;1" dur="1s" repeatCount="indefinite"/>}
            </circle>
          </g>
        ))}
        {/* AI box on warning turbine */}
        {severity === "warning" && (
          <rect x="60" y="38" width="60" height="100" fill="none" stroke="#f59e0b" strokeWidth="1.2" strokeDasharray="3 2">
            <animate attributeName="opacity" values="1;0.4;1" dur="1.2s" repeatCount="indefinite"/>
          </rect>
        )}
      </>
    );
  }

  if (type === "pv") {
    return (
      <>
        <rect x="0" y="0" width="320" height="180" fill="#0a1124"/>
        <path d="M 0 60 L 320 50 L 320 180 L 0 180 Z" fill="#0d1828"/>
        {/* PV rows */}
        {[0, 1, 2, 3].map(row => {
          const baseY = 80 + row * 25;
          return Array.from({length: 6}).map((_, col) => {
            const x = -10 + col * 60 + row * 8;
            const w = 50, h = 16;
            return (
              <g key={`${row}-${col}`}>
                <path d={`M ${x} ${baseY} L ${x+w} ${baseY-6} L ${x+w} ${baseY+h-6} L ${x} ${baseY+h} Z`}
                  fill="#0f1e3a" stroke="#3b82f6" strokeWidth="0.5"/>
                <path d={`M ${x} ${baseY} L ${x+w} ${baseY-6} L ${x+w} ${baseY+h-6} L ${x} ${baseY+h} Z`}
                  fill="url(#pvShimmer)" opacity="0.5"/>
              </g>
            );
          });
        })}
        <defs>
          <linearGradient id="pvShimmer" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#60a5fa" stopOpacity="0"/>
            <stop offset="50%" stopColor="#60a5fa" stopOpacity="0.5"/>
            <stop offset="100%" stopColor="#60a5fa" stopOpacity="0"/>
          </linearGradient>
        </defs>
      </>
    );
  }

  if (type === "substation") {
    return (
      <>
        <rect x="0" y="0" width="320" height="180" fill="#0a1124"/>
        <path d="M 0 130 L 320 130 L 320 180 L 0 180 Z" fill="#0d1828"/>
        {/* tower structure */}
        {[40, 130, 220].map((x, i) => (
          <g key={i}>
            <line x1={x} y1="20" x2={x} y2="130" stroke="#94a3b8" strokeWidth="2"/>
            {/* cross arms */}
            {[40, 60, 80].map(y => (
              <line key={y} x1={x-14} y1={y} x2={x+14} y2={y} stroke="#94a3b8" strokeWidth="1.4"/>
            ))}
            {/* insulators */}
            {[40, 60, 80].map(y => (
              <g key={y}>
                <line x1={x-14} y1={y} x2={x-14} y2={y+4} stroke="#cbd5e1" strokeWidth="0.6"/>
                <line x1={x+14} y1={y} x2={x+14} y2={y+4} stroke="#cbd5e1" strokeWidth="0.6"/>
              </g>
            ))}
          </g>
        ))}
        {/* transmission lines */}
        {[44, 64, 84].map(y => (
          <path key={y} d={`M 26 ${y+4} Q 85 ${y+10} 116 ${y+4} Q 175 ${y+10} 206 ${y+4} Q 265 ${y+10} 294 ${y+4}`}
            stroke="#60a5fa" strokeWidth="0.5" fill="none" opacity="0.7"/>
        ))}
        {/* transformer */}
        <rect x="105" y="105" width="32" height="24" fill="#334155" stroke="#64748b" strokeWidth="0.6"/>
        <line x1="121" y1="105" x2="121" y2="84" stroke="#94a3b8" strokeWidth="1.5"/>
      </>
    );
  }

  if (type === "gate") {
    return (
      <>
        <rect x="0" y="0" width="320" height="180" fill="#0a1124"/>
        {/* sky gradient */}
        <rect x="0" y="0" width="320" height="100" fill="url(#gateSky)"/>
        <defs>
          <linearGradient id="gateSky" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#1a2960" stopOpacity="0.4"/>
            <stop offset="100%" stopColor="#0a1124" stopOpacity="0"/>
          </linearGradient>
        </defs>
        {/* road */}
        <path d="M 60 180 L 130 80 L 190 80 L 260 180 Z" fill="#1a1f2e"/>
        {/* lane markings */}
        {[0.3, 0.5, 0.7, 0.9].map((p, i) => (
          <line key={i}
            x1={160 - p * 100/2} y1={80 + p * 100}
            x2={160 + p * 100/2} y2={80 + p * 100}
            stroke="#facc15" strokeWidth="0.4" strokeDasharray="3 4" opacity="0.5"/>
        ))}
        {/* gate posts */}
        <rect x="100" y="60" width="6" height="50" fill="#475569" stroke="#94a3b8" strokeWidth="0.4"/>
        <rect x="214" y="60" width="6" height="50" fill="#475569" stroke="#94a3b8" strokeWidth="0.4"/>
        {/* gate beam */}
        <rect x="100" y="62" width="120" height="3" fill="#facc15" stroke="#0a0e1a" strokeWidth="0.3"/>
        {/* sign */}
        <rect x="138" y="40" width="44" height="14" fill="#1e293b" stroke="#475569" strokeWidth="0.4"/>
        <text x="160" y="50" fontSize="5" fill="#10b981" textAnchor="middle" fontFamily="JetBrains Mono">ENTRY</text>
        {/* guard light */}
        <circle cx="103" cy="60" r="1.5" fill="#10b981">
          <animate attributeName="opacity" values="1;0.4;1" dur="2s" repeatCount="indefinite"/>
        </circle>
        <circle cx="217" cy="60" r="1.5" fill="#10b981"/>
      </>
    );
  }

  // corridor
  return (
    <>
      <rect x="0" y="0" width="320" height="180" fill="#0a1124"/>
      {/* perspective corridor */}
      <path d="M 0 30 L 320 30 L 240 90 L 80 90 Z" fill="#1a2540"/>
      <path d="M 0 180 L 320 180 L 240 90 L 80 90 Z" fill="#0d1828"/>
      {/* side walls */}
      <path d="M 0 30 L 80 90 L 80 180 L 0 180 Z" fill="#0a1124"/>
      <path d="M 320 30 L 240 90 L 240 180 L 320 180 Z" fill="#0a1124"/>
      {/* lights */}
      {[90, 145, 200].map(y => (
        <ellipse key={y} cx="160" cy={y} rx="20" ry="2" fill="#facc15" opacity="0.3"/>
      ))}
      {/* depth lines */}
      {[0.2, 0.4, 0.6, 0.8].map(p => (
        <line key={p}
          x1={80 + p*80} x2={240 - p*80}
          y1={90 + p*90} y2={90 + p*90}
          stroke="#1f2738" strokeWidth="0.4"/>
      ))}
      {/* door at end */}
      <rect x="148" y="56" width="24" height="34" fill="#1e293b" stroke="#475569" strokeWidth="0.4"/>
    </>
  );
};

// ------- Camera Feed (rich, with location-aware scene) -------
const CamFeed = ({ cam, selected, main, onClick }) => {
  const sevColor = cam.severity === "critical" ? "#ef4444" : cam.severity === "warning" ? "#f59e0b" : "#10b981";
  return (
    <div onClick={onClick}
         style={{
           position: "relative", aspectRatio: "16 / 9",
           background: "#0a0e1a", overflow: "hidden", cursor: onClick ? "pointer" : "default",
           border: `1.5px solid ${main ? "var(--brand-primary)" : selected ? "var(--brand-primary)" : "var(--border-primary)"}`,
           borderRadius: main ? "var(--r-lg)" : "var(--r-md)",
           boxShadow: main ? "var(--glow-primary)" : selected ? "0 0 8px rgba(0,212,255,0.4)" : "none",
           transition: "all 200ms ease",
         }}>
      <svg viewBox="0 0 320 180" width="100%" height="100%" preserveAspectRatio="xMidYMid slice" style={{display: "block"}}>
        <CameraSceneSVG type={cam.type} severity={cam.severity}/>
        {/* film grain noise */}
        {Array.from({length: main ? 40 : 12}).map((_, i) => (
          <circle key={i} cx={Math.random()*320} cy={Math.random()*180} r="0.4" fill="#fff" opacity={Math.random()*0.25}/>
        ))}
        {/* scan line */}
        <rect x="0" width="320" height="1.5" fill="rgba(0,212,255,0.35)">
          <animate attributeName="y" values="0;180;0" dur="7s" repeatCount="indefinite"/>
        </rect>
      </svg>

      {/* Vignette */}
      <div style={{position:"absolute", inset:0, background:"radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.5) 100%)", pointerEvents:"none"}}/>

      {/* AI bbox on critical */}
      {cam.severity === "critical" && (
        <div style={{
          position: "absolute", top: "30%", left: main ? "32%" : "32%", width: main ? "20%" : "18%", height: main ? "26%" : "26%",
          border: "1.5px solid #ef4444",
          boxShadow: "0 0 12px rgba(239,68,68,0.7), inset 0 0 8px rgba(239,68,68,0.3)",
          animation: "alarm-box 1.2s ease-in-out infinite",
        }}>
          {main && (
            <div style={{position:"absolute", top:-22, left:0, fontSize:10, fontFamily:"var(--ff-mono)", color:"#ef4444", background:"rgba(10,14,26,0.92)", padding:"2px 8px", borderRadius:3, fontWeight:600, letterSpacing:"0.05em", whiteSpace:"nowrap"}}>
              AI · 异常热源 96% · A-03
            </div>
          )}
        </div>
      )}

      {/* Top overlay */}
      <div style={{position:"absolute", top:6, left:8, right:8, display:"flex", justifyContent:"space-between", alignItems:"center", fontSize: main ? 11 : 9, fontFamily:"var(--ff-mono)", pointerEvents:"none"}}>
        <span style={{display:"flex", alignItems:"center", gap:4, color:"#ef4444", fontWeight:700, textShadow:"0 1px 2px #000"}}>
          <span style={{width: main ? 7 : 5, height: main ? 7 : 5, borderRadius:"50%", background:"#ef4444", boxShadow:"0 0 6px #ef4444", animation:"pulse-soft 1s ease-in-out infinite"}}/>
          REC
        </span>
        <span style={{color:"var(--text-secondary)", background:"rgba(0,0,0,0.55)", padding:"1px 6px", borderRadius:3, letterSpacing:"0.05em"}}>{cam.id}</span>
      </div>

      {/* Status pill */}
      {!main && (
        <div style={{position:"absolute", top:6, left:"50%", transform:"translateX(-50%)", pointerEvents:"none"}}>
          <span style={{
            display:"inline-block", width:6, height:6, borderRadius:"50%",
            background: sevColor, boxShadow:`0 0 6px ${sevColor}`,
            animation: cam.severity !== "normal" ? "pulse-soft 1s ease-in-out infinite" : "none",
          }}/>
        </div>
      )}

      {/* Bottom overlay */}
      <div style={{position:"absolute", bottom: main ? 8 : 4, left:8, right:8, fontSize: main ? 11 : 9, fontFamily:"var(--ff-mono)", color:"var(--text-secondary)", display:"flex", justifyContent:"space-between", alignItems:"center", textShadow:"0 1px 2px #000", pointerEvents:"none"}}>
        <span>{cam.location}</span>
        {main && <span style={{color:"var(--brand-primary)"}}>4K · 30 fps</span>}
      </div>
    </div>
  );
};

// ------- Site map (mini, with camera positions) -------
const CameraSiteMap = ({ cameras, selectedId, onSelect }) => {
  return (
    <svg viewBox="0 0 200 130" width="100%" height="130" style={{display:"block"}}>
      <defs>
        <pattern id="smGrid" width="10" height="10" patternUnits="userSpaceOnUse">
          <path d="M 10 0 L 0 0 0 10" stroke="#1f2738" strokeWidth="0.3" fill="none"/>
        </pattern>
      </defs>
      <rect width="200" height="130" fill="rgba(10,14,26,0.5)"/>
      <rect width="200" height="130" fill="url(#smGrid)"/>
      {/* Site outline */}
      <rect x="10" y="10" width="180" height="110" fill="none" stroke="#2a3245" strokeWidth="0.6" strokeDasharray="3 2"/>
      {/* zones */}
      <g opacity="0.6">
        <rect x="14" y="14" width="60" height="36" fill="rgba(96,165,250,0.08)" stroke="#3b82f6" strokeWidth="0.3"/>
        <text x="44" y="32" fontSize="5" fill="#60a5fa" textAnchor="middle" fontFamily="JetBrains Mono">PV</text>
        <rect x="80" y="14" width="106" height="30" fill="rgba(96,165,250,0.05)" stroke="#3b82f6" strokeWidth="0.3"/>
        <text x="133" y="30" fontSize="5" fill="#60a5fa" textAnchor="middle" fontFamily="JetBrains Mono">WIND</text>
        <rect x="14" y="58" width="120" height="32" fill="rgba(249,115,22,0.08)" stroke="#f97316" strokeWidth="0.3"/>
        <text x="74" y="76" fontSize="5" fill="#f97316" textAnchor="middle" fontFamily="JetBrains Mono">ESS</text>
        <rect x="140" y="58" width="46" height="32" fill="rgba(59,130,246,0.08)" stroke="#3b82f6" strokeWidth="0.3"/>
        <text x="163" y="76" fontSize="5" fill="#3b82f6" textAnchor="middle" fontFamily="JetBrains Mono">220kV</text>
      </g>
      {/* camera positions */}
      {cameras.map(c => {
        const sel = c.id === selectedId;
        const col = c.severity === "critical" ? "#ef4444" : c.severity === "warning" ? "#f59e0b" : "#10b981";
        return (
          <g key={c.id} transform={`translate(${c.pos[0]} ${c.pos[1]})`} style={{cursor:"pointer"}}
             onClick={() => onSelect(c.id)}>
            {sel && <circle r="6" fill="none" stroke="var(--brand-primary)" strokeWidth="0.8">
              <animate attributeName="r" values="6;9;6" dur="1.5s" repeatCount="indefinite"/>
              <animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite"/>
            </circle>}
            {/* Cone of view */}
            <path d={`M 0 0 L ${4*Math.cos((c.rot-25)*Math.PI/180)} ${4*Math.sin((c.rot-25)*Math.PI/180)} A 8 8 0 0 1 ${8*Math.cos((c.rot+25)*Math.PI/180)} ${8*Math.sin((c.rot+25)*Math.PI/180)} Z`}
              fill={sel ? "var(--brand-primary)" : col} opacity={sel ? 0.4 : 0.18}/>
            <circle r="2" fill={col} stroke="#0a0e1a" strokeWidth="0.5">
              {c.severity !== "normal" && <animate attributeName="opacity" values="1;0.4;1" dur="1s" repeatCount="indefinite"/>}
            </circle>
            <text y="-4" fontSize="3.5" fill={sel ? "var(--brand-primary)" : "var(--text-secondary)"} textAnchor="middle" fontFamily="JetBrains Mono" fontWeight="600">{c.id.replace("CAM-","C")}</text>
          </g>
        );
      })}
      {/* legend */}
      <g transform="translate(10 122)" fontSize="4" fontFamily="JetBrains Mono" fill="#5d6885">
        <text x="0" y="0">站点平面图 · CAMERA MAP</text>
      </g>
    </svg>
  );
};

// ------- Camera dataset -------
const CAMERAS = [
  { id: "CAM-01", type: "gate",       location: "南门主入口",       severity: "normal",   pos: [20, 110], rot: 270, deviceId: "site" },
  { id: "CAM-02", type: "storage",    location: "储能区 A-01~A-05", severity: "critical", pos: [44, 74],  rot: 90,  deviceId: "A-03" },
  { id: "CAM-03", type: "storage",    location: "储能区 A-06~A-10", severity: "normal",   pos: [108, 74], rot: 90,  deviceId: "A-08" },
  { id: "CAM-04", type: "wind",       location: "风机 W-01 / W-02", severity: "normal",   pos: [98, 28],  rot: 270, deviceId: "W-01" },
  { id: "CAM-05", type: "wind",       location: "风机 W-03 / W-04", severity: "warning", pos: [170, 28], rot: 270, deviceId: "W-03" },
  { id: "CAM-06", type: "pv",         location: "光伏阵列 PV-01",   severity: "normal",   pos: [40, 30],  rot: 90,  deviceId: "PV-01" },
  { id: "CAM-07", type: "substation", location: "升压站 220kV",     severity: "normal",   pos: [162, 74], rot: 180, deviceId: "sub" },
  { id: "CAM-08", type: "corridor",   location: "运维通道",         severity: "normal",   pos: [180, 110],rot: 180, deviceId: "site" },
];

// ------- VIDEO MONITOR MAIN VIEW (replaces the 3D scene when activeView===4) -------
const VideoMonitorView = ({ selectedCamera, onSelectCamera }) => {
  const cams = CAMERAS;
  const mainCam = cams.find(c => c.id === selectedCamera) || cams[1];
  const others = cams.filter(c => c.id !== mainCam.id);

  return (
    <div style={{position:"absolute", inset:0, padding:"54px 18px 18px 18px", display:"grid", gridTemplateColumns:"1fr 248px", gap:14, minHeight:0}}>
      {/* MAIN COLUMN */}
      <div style={{display:"flex", flexDirection:"column", gap:12, minHeight:0}}>
        {/* Main feed */}
        <div style={{position:"relative", flex:1, minHeight:0}}>
          <CamFeed cam={mainCam} main/>
          {/* PTZ */}
          <div style={{position:"absolute", bottom:50, right:18, display:"flex", flexDirection:"column", gap:4, alignItems:"center", background:"rgba(10,14,26,0.65)", padding:8, borderRadius:"var(--r-md)", border:"1px solid var(--border-divider)"}}>
            <div style={{fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", letterSpacing:"0.1em", marginBottom:2}}>PTZ</div>
            <button className="btn icon-only" style={{height:26, width:26, fontSize:13}}>↑</button>
            <div style={{display:"flex", gap:4}}>
              <button className="btn icon-only" style={{height:26, width:26, fontSize:13}}>←</button>
              <button className="btn icon-only" style={{height:26, width:26}}><Icon name="target" size={11}/></button>
              <button className="btn icon-only" style={{height:26, width:26, fontSize:13}}>→</button>
            </div>
            <button className="btn icon-only" style={{height:26, width:26, fontSize:13}}>↓</button>
            <div style={{display:"flex", gap:4, marginTop:4, paddingTop:4, borderTop:"1px solid var(--border-divider)", width:"100%", justifyContent:"center"}}>
              <button className="btn icon-only" style={{height:22, width:26, fontSize:14}}>+</button>
              <button className="btn icon-only" style={{height:22, width:26, fontSize:14}}>−</button>
            </div>
          </div>
          {/* Status bar overlay top */}
          <div style={{position:"absolute", top:14, left:"50%", transform:"translateX(-50%)", display:"flex", gap:8, background:"rgba(10,14,26,0.75)", padding:"5px 12px", borderRadius:"var(--r-full)", border:"1px solid var(--border-divider)", fontSize:10, fontFamily:"var(--ff-mono)"}}>
            <span style={{color:"var(--brand-primary)", fontWeight:600}}>● LIVE</span>
            <span style={{color:"var(--text-tertiary)"}}>|</span>
            <LiveClock style={{color:"var(--text-secondary)"}}/>
            <span style={{color:"var(--text-tertiary)"}}>|</span>
            <span style={{color:"var(--text-secondary)"}}>{mainCam.id}</span>
            <span style={{color:"var(--text-tertiary)"}}>|</span>
            <span style={{color:"var(--text-secondary)"}}>PTZ · 0° / 0°</span>
          </div>
        </div>

        {/* Recording timeline */}
        <div className="card" style={{padding:"10px 14px", background:"rgba(10,14,26,0.6)"}}>
          <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:6}}>
            <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", letterSpacing:"0.1em"}}>录像时间轴 · LAST 24h</span>
            <div style={{display:"flex", gap:4}}>
              <button className="btn" style={{height:22, padding:"0 8px", fontSize:10}}>实时</button>
              <button className="btn" style={{height:22, padding:"0 8px", fontSize:10}}>1h</button>
              <button className="btn" style={{height:22, padding:"0 8px", fontSize:10}}>6h</button>
              <button className="btn active" style={{height:22, padding:"0 8px", fontSize:10}}>24h</button>
            </div>
          </div>
          <div style={{position:"relative", height:32}}>
            {/* track */}
            <div style={{position:"absolute", left:0, right:0, top:10, height:8, background:"linear-gradient(90deg, rgba(0,212,255,0.15), rgba(0,212,255,0.4), rgba(0,212,255,0.15))", borderRadius:2, border:"1px solid var(--border-divider)"}}>
              {/* event markers */}
              {[
                {p:0.12, sev:"info"},
                {p:0.28, sev:"warning"},
                {p:0.41, sev:"warning"},
                {p:0.59, sev:"critical"},
                {p:0.74, sev:"warning"},
                {p:0.89, sev:"info"},
              ].map((m,i) => (
                <div key={i} style={{
                  position:"absolute", left:`${m.p*100}%`, top:-2, bottom:-2,
                  width:3,
                  background: m.sev==="critical"?"#ef4444":m.sev==="warning"?"#f59e0b":"#3b82f6",
                  boxShadow:`0 0 6px ${m.sev==="critical"?"#ef4444":m.sev==="warning"?"#f59e0b":"#3b82f6"}`,
                  transform:"translateX(-50%)",
                }}/>
              ))}
              {/* current playhead */}
              <div style={{position:"absolute", left:"95%", top:-6, bottom:-6, width:2, background:"var(--brand-primary)", boxShadow:"var(--glow-primary)"}}>
                <div style={{position:"absolute", top:-8, left:-5, width:12, height:12, background:"var(--brand-primary)", borderRadius:"50%", border:"2px solid #0a0e1a"}}/>
              </div>
            </div>
            {/* time scale */}
            <div style={{position:"absolute", inset:"22px 0 0 0", display:"flex", justifyContent:"space-between", fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>
              <span>15:00</span><span>21:00</span><span>03:00</span><span>09:00</span><span>15:00</span>
            </div>
          </div>
        </div>

        {/* Thumbnail strip — 4 secondary cameras */}
        <div style={{display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:8, height:104, flexShrink:0}}>
          {others.slice(0, 4).map(c => (
            <CamFeed key={c.id} cam={c} selected={false} onClick={() => onSelectCamera(c.id)}/>
          ))}
        </div>
      </div>

      {/* RIGHT COLUMN: site map + camera list */}
      <div style={{display:"flex", flexDirection:"column", gap:10, minHeight:0}}>
        <div className="card" style={{padding:"10px 12px"}}>
          <div style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", letterSpacing:"0.1em", marginBottom:6}}>站点地图 · MAP</div>
          <CameraSiteMap cameras={cams} selectedId={mainCam.id} onSelect={onSelectCamera}/>
        </div>

        <div className="card" style={{padding:"10px 12px", flex:1, minHeight:0, display:"flex", flexDirection:"column"}}>
          <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:6}}>
            <span style={{fontSize:10, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)", letterSpacing:"0.1em"}}>摄像头列表</span>
            <span style={{fontSize:10, color:"#10b981", fontFamily:"var(--ff-mono)"}}>
              <span style={{display:"inline-block", width:6, height:6, borderRadius:"50%", background:"#10b981", marginRight:4, boxShadow:"0 0 4px #10b981"}}/>
              {cams.length} ONLINE
            </span>
          </div>
          <div style={{flex:1, overflowY:"auto", display:"flex", flexDirection:"column", gap:6, minHeight:0}}>
            {cams.map(c => {
              const sel = c.id === mainCam.id;
              const sevColor = c.severity === "critical" ? "#ef4444" : c.severity === "warning" ? "#f59e0b" : "#10b981";
              return (
                <div key={c.id} onClick={() => onSelectCamera(c.id)}
                  style={{
                    padding:"6px 8px", border:`1px solid ${sel ? "var(--brand-primary)" : "var(--border-divider)"}`,
                    background: sel ? "rgba(0,212,255,0.08)" : c.severity !== "normal" ? `${sevColor}14` : "transparent",
                    borderRadius:"var(--r-md)", cursor:"pointer", display:"flex", alignItems:"center", gap:8,
                  }}>
                  <span style={{width:6, height:6, borderRadius:"50%", background: sevColor, boxShadow:`0 0 6px ${sevColor}`,
                    animation: c.severity !== "normal" ? "pulse-soft 1s ease-in-out infinite" : "none"}}/>
                  <div style={{flex:1, minWidth:0}}>
                    <div style={{fontSize:11, fontFamily:"var(--ff-mono)", color:"var(--text-primary)", fontWeight:600}}>{c.id}</div>
                    <div style={{fontSize:9, color:"var(--text-tertiary)", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis"}}>{c.location}</div>
                  </div>
                  {sel && <Icon name="eye" size={10} color="var(--brand-primary)"/>}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

// ------- VIDEO MONITOR RIGHT PANEL -------
const VideoMonitorPanel = ({ selectedCamera, onSelectCamera }) => {
  const cams = CAMERAS;
  const totalCount = cams.length;
  const criticalCount = cams.filter(c => c.severity === "critical").length;
  const warningCount = cams.filter(c => c.severity === "warning").length;

  // AI detection events
  const events = [
    { id: 1, time: "14:23:08", cam: "CAM-02", severity: "critical", title: "异常热源识别",   detail: "A-03 储能舱 · 热成像红外异常",   conf: 96 },
    { id: 2, time: "14:21:42", cam: "CAM-02", severity: "critical", title: "烟雾轮廓检测",   detail: "A-03 顶部空气抖动 · 疑似挥发",   conf: 87 },
    { id: 3, time: "14:18:51", cam: "CAM-05", severity: "warning",  title: "叶片晃动幅度异常", detail: "W-03 振动 8.2mm 超阈值",          conf: 82 },
    { id: 4, time: "14:12:30", cam: "CAM-01", severity: "info",     title: "人员进入",        detail: "运维 1 人 · 持卡进入",            conf: 99 },
    { id: 5, time: "14:02:14", cam: "CAM-08", severity: "info",     title: "巡检完成",        detail: "2 区域 · 用时 12 分钟",           conf: 95 },
    { id: 6, time: "13:55:09", cam: "CAM-02", severity: "warning",  title: "温度异常上升",     detail: "A-07 风冷区温度抬升至 42℃",      conf: 91 },
  ];

  return (
    <div className="area-right" style={{display:"flex", flexDirection:"column", gap:14, minHeight:0}}>
      {/* Summary */}
      <div className="card" style={{position:"relative", padding:"14px 16px"}}>
        <span className="corner-deco tl"/><span className="corner-deco tr"/>
        <span className="corner-deco bl"/><span className="corner-deco br"/>
        <div className="card-title" style={{marginBottom:12}}>视频监控 · CCTV</div>

        <div style={{display:"flex", alignItems:"baseline", gap:10, marginBottom:4}}>
          <span className="display-num" style={{fontSize:"var(--text-4xl)"}}>{totalCount}</span>
          <span style={{fontSize:"var(--text-sm)", color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>/ {totalCount}</span>
          <span className="pill normal" style={{marginLeft:"auto"}}><span className="dot"/>全部在线</span>
        </div>
        <div style={{fontSize:"var(--text-xs)", color:"var(--text-tertiary)", letterSpacing:"0.08em", textTransform:"uppercase", fontFamily:"var(--ff-mono)"}}>
          摄像头在线 / ONLINE
        </div>

        <div style={{display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:8, marginTop:14}}>
          <div style={{padding:"6px 10px", border:"1px solid rgba(239,68,68,0.35)", borderRadius:"var(--r-md)", background:"rgba(239,68,68,0.08)"}}>
            <div style={{fontSize:9, color:"var(--text-secondary)", fontFamily:"var(--ff-mono)"}}>异常</div>
            <div style={{fontSize:"var(--text-lg)", fontFamily:"var(--ff-display)", fontWeight:600, color:"#ef4444"}}>{criticalCount}</div>
          </div>
          <div style={{padding:"6px 10px", border:"1px solid rgba(245,158,11,0.35)", borderRadius:"var(--r-md)", background:"rgba(245,158,11,0.08)"}}>
            <div style={{fontSize:9, color:"var(--text-secondary)", fontFamily:"var(--ff-mono)"}}>告警</div>
            <div style={{fontSize:"var(--text-lg)", fontFamily:"var(--ff-display)", fontWeight:600, color:"#f59e0b"}}>{warningCount}</div>
          </div>
          <div style={{padding:"6px 10px", border:"1px solid rgba(16,185,129,0.35)", borderRadius:"var(--r-md)", background:"rgba(16,185,129,0.08)"}}>
            <div style={{fontSize:9, color:"var(--text-secondary)", fontFamily:"var(--ff-mono)"}}>正常</div>
            <div style={{fontSize:"var(--text-lg)", fontFamily:"var(--ff-display)", fontWeight:600, color:"#10b981"}}>{totalCount - criticalCount - warningCount}</div>
          </div>
        </div>

        {/* AI summary */}
        <div style={{marginTop:14, paddingTop:10, borderTop:"1px solid var(--border-divider)", display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, fontSize:10, fontFamily:"var(--ff-mono)"}}>
          <div>
            <div style={{color:"var(--text-tertiary)"}}>AI 识别 / 今日</div>
            <div style={{fontSize:"var(--text-md)", color:"var(--brand-primary)", fontWeight:600, marginTop:2}}>147 <span style={{fontSize:9, color:"var(--text-tertiary)"}}>events</span></div>
          </div>
          <div>
            <div style={{color:"var(--text-tertiary)"}}>录像存储</div>
            <div style={{fontSize:"var(--text-md)", color:"var(--text-primary)", fontWeight:600, marginTop:2}}>74% <span style={{fontSize:9, color:"var(--text-tertiary)"}}>11.8 TB</span></div>
          </div>
        </div>
      </div>

      {/* Playback controls */}
      <div className="card" style={{position:"relative", padding:"14px 16px"}}>
        <span className="corner-deco tl"/><span className="corner-deco tr"/>
        <span className="corner-deco bl"/><span className="corner-deco br"/>
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10}}>
          <div className="card-title" style={{margin:0}}>回放控制 · PLAYBACK</div>
          <span style={{fontSize:9, color:"#10b981", fontFamily:"var(--ff-mono)"}}>● REC</span>
        </div>
        <div style={{display:"flex", alignItems:"center", justifyContent:"center", gap:8, padding:"6px 0"}}>
          <button className="btn icon-only" style={{height:30, width:30}}><Icon name="skipB" size={12}/></button>
          <button className="btn primary icon-only" style={{height:36, width:36}}><Icon name="play" size={14}/></button>
          <button className="btn icon-only" style={{height:30, width:30}}><Icon name="skipF" size={12}/></button>
        </div>
        <div style={{display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:4, marginTop:8}}>
          {["0.5x", "1x", "2x", "4x"].map((s, i) => (
            <button key={s} className={`btn ${i === 1 ? "active" : ""}`} style={{height:24, padding:0, fontSize:10, justifyContent:"center"}}>{s}</button>
          ))}
        </div>
        <div style={{marginTop:10, paddingTop:10, borderTop:"1px solid var(--border-divider)", display:"flex", gap:6}}>
          <button className="btn" style={{flex:1, height:28, fontSize:11, justifyContent:"center"}}>截图</button>
          <button className="btn" style={{flex:1, height:28, fontSize:11, justifyContent:"center"}}>下载片段</button>
        </div>
      </div>

      {/* AI Event log */}
      <div className="card" style={{position:"relative", padding:"14px 16px", flex:1, display:"flex", flexDirection:"column", minHeight:0}}>
        <span className="corner-deco tl"/><span className="corner-deco tr"/>
        <span className="corner-deco bl"/><span className="corner-deco br"/>
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10}}>
          <div className="card-title" style={{margin:0}}>AI 事件 · DETECTION</div>
          <span className="pill critical"><span className="dot"/>{events.filter(e => e.severity !== "info").length} 待复核</span>
        </div>
        <div style={{flex:1, overflowY:"auto", display:"flex", flexDirection:"column", gap:8, minHeight:0}}>
          {events.map(e => {
            const color = e.severity === "critical" ? "#ef4444" : e.severity === "warning" ? "#f59e0b" : "#3b82f6";
            return (
              <div key={e.id} onClick={() => onSelectCamera(e.cam)}
                style={{
                  padding:"8px 10px", border:`1px solid ${color}40`, borderRadius:"var(--r-md)",
                  background: `${color}10`, cursor:"pointer",
                }}>
                <div style={{display:"flex", alignItems:"center", gap:6, marginBottom:4}}>
                  <span style={{width:5, height:5, borderRadius:"50%", background:color, boxShadow:`0 0 6px ${color}`}}/>
                  <span style={{fontSize:11, color:color, fontWeight:600}}>{e.title}</span>
                  <span style={{marginLeft:"auto", fontSize:9, color:"var(--text-tertiary)", fontFamily:"var(--ff-mono)"}}>{e.time}</span>
                </div>
                <div style={{display:"flex", alignItems:"center", gap:6, marginLeft:11}}>
                  <span style={{fontSize:10, color:"var(--text-secondary)", fontFamily:"var(--ff-mono)"}}>{e.detail}</span>
                </div>
                <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginLeft:11, marginTop:4, fontSize:9, fontFamily:"var(--ff-mono)"}}>
                  <span style={{color:"var(--text-tertiary)"}}>{e.cam}</span>
                  <span style={{color:color, fontWeight:600}}>置信度 {e.conf}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};


export { CameraSceneSVG, CamFeed, CameraSiteMap, CAMERAS, VideoMonitorView, VideoMonitorPanel };
