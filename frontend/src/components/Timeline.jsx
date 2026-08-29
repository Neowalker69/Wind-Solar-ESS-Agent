import React, { useRef, useCallback, useEffect } from "react";
import { useStore, severityColor } from "../store";
import { Icon } from "./components";

// Window: 14:00 -> 15:00 (60 min). Map progress(0..1) -> wall-clock readout.
const SPEED_MULT = { "0.5x": 0.5, "1x": 1, "2x": 2, "4x": 4 };
const fmtTime = (p) => {
  const totalSec = Math.round(p * 3600); // 60 min window
  const h = 14 + Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `2026-05-16 ${pad(h)}:${pad(m)}:${pad(s)}`;
};

// ====================== Bottom timeline (scrolling progress bar) ======================
// Renders colored alarm intervals (NOT dot-breakpoints) over the time window,
// a draggable playhead, playback transport + speed control. Reads useStore.
const Timeline = () => {
  const playing = useStore((s) => s.playing);
  const togglePlay = useStore((s) => s.togglePlay);
  const speed = useStore((s) => s.speed);
  const setSpeed = useStore((s) => s.setSpeed);
  const progress = useStore((s) => s.timelineProgress);
  const setProgress = useStore((s) => s.setTimelineProgress);
  const segments = useStore((s) => s.timelineSegments);
  const setSelectedDevice = useStore((s) => s.setSelectedDevice);

  const trackRef = useRef(null);
  const draggingRef = useRef(false);

  // Auto-advance the playhead while playing (scaled by speed). Full window sweeps
  // in ~60s at 1x. Pauses while the user is scrubbing. Wraps 1 -> 0.
  useEffect(() => {
    if (!playing) return;
    const tickMs = 100;
    const mult = SPEED_MULT[speed] ?? 1;
    const step = (tickMs / 1000 / 60) * mult;
    const id = setInterval(() => {
      if (draggingRef.current) return;
      const cur = useStore.getState().timelineProgress;
      setProgress(cur + step >= 1 ? 0 : cur + step);
    }, tickMs);
    return () => clearInterval(id);
  }, [playing, speed, setProgress]);

  const posFromEvent = useCallback((clientX) => {
    const el = trackRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  }, []);

  const onPointerDown = (e) => {
    draggingRef.current = true;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setProgress(posFromEvent(e.clientX));
  };
  const onPointerMove = (e) => {
    if (!draggingRef.current) return;
    setProgress(posFromEvent(e.clientX));
  };
  const onPointerUp = (e) => {
    draggingRef.current = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  };

  const speeds = ["0.5x", "1x", "2x", "4x"];
  const ticks = ["14:00", "14:15", "14:30", "14:45", "15:00"];

  return (
    <div
      style={{
        borderTop: "1px solid var(--border-divider)",
        padding: "10px 20px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        fontWeight: 400,
      }}
    >
      {/* transport */}
      <div style={{ display: "flex", gap: 6 }}>
        <button
          className="btn icon-only"
          style={{ height: 28, width: 28 }}
          onClick={() => setProgress(Math.max(0, progress - 0.05))}
          title="后退"
        >
          <Icon name="skipB" size={12} />
        </button>
        <button
          className="btn primary icon-only"
          style={{ height: 28, width: 28 }}
          onClick={togglePlay}
          title={playing ? "暂停" : "播放"}
        >
          <Icon name={playing ? "pause" : "play"} size={12} />
        </button>
        <button
          className="btn icon-only"
          style={{ height: 28, width: 28 }}
          onClick={() => setProgress(Math.min(1, progress + 0.05))}
          title="前进"
        >
          <Icon name="skipF" size={12} />
        </button>
      </div>

      {/* speed */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
        速度
        <div className="tab-group" style={{ padding: 2 }}>
          {speeds.map((s) => (
            <div
              key={s}
              className={`tab ${speed === s ? "active" : ""}`}
              style={{ padding: "2px 8px", fontSize: 11 }}
              onClick={() => setSpeed(s)}
            >
              {s}
            </div>
          ))}
        </div>
      </div>

      {/* scrolling progress bar */}
      <div style={{ flex: 1, position: "relative", height: 28, margin: "0 8px" }}>
        <div
          ref={trackRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 9,
            height: 10,
            borderRadius: 5,
            overflow: "hidden",
            cursor: "pointer",
            background: "#1f2738",
            border: "1px solid var(--border-divider)",
          }}
        >
          {/* colored alarm intervals */}
          {segments.map((seg, i) => {
            const c = severityColor(seg.severity);
            const isEvent = seg.severity !== "normal";
            return (
              <div
                key={i}
                title={seg.label ? `${seg.label}${seg.time ? " · " + seg.time : ""}` : ""}
                onClick={(e) => {
                  e.stopPropagation();
                  if (seg.deviceId) setSelectedDevice(seg.deviceId);
                }}
                style={{
                  position: "absolute",
                  left: `${seg.from * 100}%`,
                  width: `${(seg.to - seg.from) * 100}%`,
                  top: 0,
                  bottom: 0,
                  background: isEvent
                    ? `linear-gradient(180deg, ${c}cc, ${c}88)`
                    : "transparent",
                  boxShadow: isEvent ? `0 0 8px ${c}88 inset` : "none",
                  cursor: seg.deviceId ? "pointer" : "default",
                }}
              />
            );
          })}
          {/* filled progress overlay */}
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: `${progress * 100}%`,
              background: "rgba(0,212,255,0.18)",
              borderRight: "1px solid rgba(0,212,255,0.5)",
              pointerEvents: "none",
            }}
          />
        </div>

        {/* playhead */}
        <div
          style={{
            position: "absolute",
            left: `${progress * 100}%`,
            top: 4,
            transform: "translateX(-50%)",
            width: 16,
            height: 16,
            borderRadius: "50%",
            background: "var(--brand-primary)",
            boxShadow: "var(--glow-primary)",
            border: "2px solid #0a0e1a",
            pointerEvents: "none",
          }}
        />

        {/* time scale */}
        <div
          style={{
            position: "absolute",
            inset: "22px 0 0 0",
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: "var(--text-tertiary)",
            fontFamily: "var(--ff-mono)",
          }}
        >
          {ticks.map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
      </div>

      {/* current time readout (driven by progress) */}
      <div style={{ fontFamily: "var(--ff-mono)", fontSize: "var(--text-sm)", color: "var(--brand-primary)", letterSpacing: "0.05em" }}>
        {fmtTime(progress)}
      </div>

      {/* active event pills */}
      <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
        <span className="pill critical" style={{ fontSize: 10, height: 20 }}>A-03 失电</span>
        <span className="pill warning" style={{ fontSize: 10, height: 20 }}>风扇异常</span>
        <span className="pill warning" style={{ fontSize: 10, height: 20 }}>高温</span>
      </div>
    </div>
  );
};

export { Timeline };
