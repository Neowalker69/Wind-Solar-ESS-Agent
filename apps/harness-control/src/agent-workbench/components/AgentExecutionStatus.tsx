"use client"

import {
  ChevronDown,
  Circle,
  CircleCheck,
  CircleStop,
  CircleX,
  LoaderCircle,
  PauseCircle,
  RotateCw,
  Wrench
} from "lucide-react"
import { memo, useEffect, useId, useRef, useState } from "react"

import type {
  AgentExecutionEvent,
  AgentRunState,
  AgentRunStatus
} from "../contracts"

interface ExecutionStatusCopy {
  title: string
  summary: string
  tone: "running" | "success" | "warning" | "muted" | "error"
}

export function executionStatusCopy(
  status: AgentRunStatus,
  currentLabel = "正在理解任务"
): ExecutionStatusCopy {
  if (status === "completed") {
    return { title: "已完成思考和执行", summary: "思考与执行摘要（点击展开）", tone: "success" }
  }
  if (status === "cancelled") {
    return { title: "已停止思考和执行", summary: "已保留停止前生成的内容", tone: "muted" }
  }
  if (status === "failed" || status === "error") {
    return { title: "思考和执行未完成", summary: "展开查看失败阶段与错误摘要", tone: "error" }
  }
  if (status === "waiting_approval") {
    return { title: "等待确认后继续执行", summary: currentLabel, tone: "warning" }
  }
  if (status === "reconnecting") {
    return { title: "正在恢复思考和执行", summary: "保留已有内容并从断点恢复", tone: "warning" }
  }
  if (status === "queued") {
    return { title: "思考与执行中", summary: "任务已提交", tone: "running" }
  }
  if (status === "connecting") {
    return { title: "思考与执行中", summary: "正在连接 Agent", tone: "running" }
  }
  return { title: "思考与执行中", summary: currentLabel, tone: "running" }
}

export function formatExecutionDuration(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`
}

export const AgentExecutionStatus = memo(function AgentExecutionStatus({
  run,
  startedAt
}: {
  run?: AgentRunState
  startedAt: string
}) {
  const status = run?.status ?? "connecting"
  const terminal = ["completed", "cancelled", "failed", "error"].includes(status)
  const [open, setOpen] = useState(false)
  const contentId = useId()
  const hoveringRef = useRef(false)
  const focusWithinRef = useRef(false)
  const lastInteractionRef = useRef(0)
  const copy = executionStatusCopy(status, run?.execution.currentLabel)

  useEffect(() => {
    if (!terminal || !open) return
    const timer = window.setTimeout(() => {
      const recentlyInteracted = Date.now() - lastInteractionRef.current < 1_500
      if (!hoveringRef.current && !focusWithinRef.current && !recentlyInteracted) {
        setOpen(false)
      }
    }, 650)
    return () => window.clearTimeout(timer)
  }, [open, terminal])

  const toggle = () => {
    lastInteractionRef.current = Date.now()
    setOpen((value) => !value)
  }

  return (
    <section
      className={`agent-execution-card ${copy.tone}`}
      data-status={status}
      aria-label="思考与执行摘要"
      onMouseEnter={() => { hoveringRef.current = true }}
      onMouseLeave={() => { hoveringRef.current = false }}
      onFocusCapture={() => { focusWithinRef.current = true }}
      onBlurCapture={(event) => {
        focusWithinRef.current = event.currentTarget.contains(event.relatedTarget)
      }}
    >
      <button
        className="agent-execution-header"
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={contentId}
      >
        <span className="agent-execution-status-icon" aria-hidden="true">
          <ExecutionStatusIcon status={status} />
        </span>
        <span className="agent-execution-copy">
          <b>{copy.title}</b>
          <small>{copy.summary}</small>
        </span>
        <ExecutionDuration
          startedAt={startedAt}
          completedAt={run?.completedAt}
          stopped={terminal}
        />
        <span className={`agent-execution-chevron ${open ? "open" : ""}`} aria-hidden="true">
          <ChevronDown size={16} />
        </span>
      </button>

      {!terminal && status !== "waiting_approval" && (
        <div className="agent-execution-progress" aria-label="执行中">
          <i />
        </div>
      )}

      <div
        className={`agent-execution-content ${open ? "open" : ""}`}
        id={contentId}
        aria-hidden={!open}
      >
        <div className="agent-execution-content-inner">
          {run?.reasoningSummary && (
            <div className="agent-reasoning-summary">{run.reasoningSummary}</div>
          )}
          {!run?.execution.events.length && (
            <div className="agent-streaming-placeholder">正在建立任务上下文…</div>
          )}
          {!!run?.execution.events.length && (
            <div className="agent-execution-timeline" role="list" aria-label="执行事件时间线">
              {run.execution.events.map((event) => (
                <ExecutionTimelineItem event={event} key={event.stepId} />
              ))}
            </div>
          )}
          {run?.errorMessage && (
            <div className="agent-streaming-inline-error">{run.errorMessage}</div>
          )}
        </div>
      </div>
    </section>
  )
})

const ExecutionTimelineItem = memo(function ExecutionTimelineItem({
  event
}: {
  event: AgentExecutionEvent
}) {
  return (
    <div
      className="agent-execution-event"
      data-status={event.status}
      role="listitem"
    >
      <span className="agent-execution-event-node" aria-hidden="true">
        <ExecutionEventIcon event={event} />
      </span>
      <time>{formatEventTime(event.timestamp)}</time>
      <div className="agent-execution-event-copy">
        <b>{event.label}</b>
        {event.summary && <small>{event.summary}</small>}
        {event.toolLabel && <em><Wrench size={10} />{event.toolLabel}</em>}
      </div>
      {typeof event.durationMs === "number" && (
        <span className="agent-execution-event-duration">
          {formatExecutionDuration(event.durationMs)}
        </span>
      )}
    </div>
  )
})

function ExecutionStatusIcon({ status }: { status: AgentRunStatus }) {
  if (status === "completed") return <CircleCheck size={18} />
  if (status === "cancelled") return <CircleStop size={18} />
  if (status === "failed" || status === "error") return <CircleX size={18} />
  if (status === "waiting_approval") return <PauseCircle size={18} />
  if (status === "reconnecting") return <RotateCw size={18} />
  return <LoaderCircle size={18} />
}

function ExecutionEventIcon({ event }: { event: AgentExecutionEvent }) {
  if (event.status === "completed") return <CircleCheck size={14} />
  if (event.status === "running") return <LoaderCircle size={14} />
  if (event.status === "waiting") return <PauseCircle size={14} />
  if (event.status === "cancelled") return <CircleStop size={14} />
  if (event.status === "error" || event.status === "failed") return <CircleX size={14} />
  return <Circle size={14} />
}

const ExecutionDuration = memo(function ExecutionDuration({
  startedAt,
  completedAt,
  stopped
}: {
  startedAt: string
  completedAt?: string
  stopped: boolean
}) {
  const calculateElapsed = () => {
    const start = Date.parse(startedAt)
    const end = completedAt ? Date.parse(completedAt) : Date.now()
    return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, end - start) : 0
  }
  const [elapsed, setElapsed] = useState(calculateElapsed)

  useEffect(() => {
    setElapsed(calculateElapsed())
    if (stopped) return
    const timer = window.setInterval(() => setElapsed(calculateElapsed()), 1_000)
    return () => window.clearInterval(timer)
  }, [completedAt, startedAt, stopped])

  return <span className="agent-execution-duration">{formatExecutionDuration(elapsed)}</span>
})

function formatEventTime(timestamp?: string): string {
  if (!timestamp) return "--:--:--"
  const value = new Date(timestamp)
  if (Number.isNaN(value.getTime())) return "--:--:--"
  return value.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  })
}
