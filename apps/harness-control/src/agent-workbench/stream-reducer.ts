import type {
  AgentExecutionEvent,
  AgentRunState,
  AgentRunStatus,
  AgentStreamEvent
} from "./contracts"

const TERMINAL_STATUSES = new Set<AgentRunStatus>([
  "completed",
  "cancelled",
  "error",
  "failed"
])

const EXECUTION_TYPES = new Set([
  "phase.changed",
  "reasoning.summary",
  "workflow.started",
  "workflow.step.started",
  "workflow.step.completed",
  "workflow.completed",
  "tool.started",
  "tool.progress",
  "tool.completed"
])

export function createAgentRunState(
  runId: string,
  conversationId: string,
  messageId: string
): AgentRunState {
  return {
    runId,
    conversationId,
    messageId,
    status: "queued",
    lastSequence: 0,
    receivedText: "",
    responseCompleted: false,
    reasoningSummary: "",
    execution: { currentLabel: "任务已创建", events: [] },
    pendingEvents: {},
    errorMessage: ""
  }
}

export function reduceAgentStreamEvents(
  state: AgentRunState,
  incoming: AgentStreamEvent[]
): AgentRunState {
  let next = { ...state, pendingEvents: { ...state.pendingEvents } }
  for (const event of incoming) {
    if (event.sequence <= next.lastSequence || next.pendingEvents[event.sequence]) continue
    next.pendingEvents[event.sequence] = event
  }
  while (next.pendingEvents[next.lastSequence + 1]) {
    const sequence = next.lastSequence + 1
    const event = next.pendingEvents[sequence]
    delete next.pendingEvents[sequence]
    next = applyAgentStreamEvent(next, event)
    next.lastSequence = sequence
  }
  return next
}

function applyAgentStreamEvent(state: AgentRunState, event: AgentStreamEvent): AgentRunState {
  const payload = event.payload ?? {}
  const terminal = TERMINAL_STATUSES.has(state.status)
  if (event.type === "response.delta") {
    if (terminal) return state
    return {
      ...state,
      status: "streaming",
      receivedText: state.receivedText + String(payload.delta ?? "")
    }
  }
  if (event.type === "response.started") {
    return terminal ? state : { ...state, status: "streaming" }
  }
  if (event.type === "response.completed") {
    if (terminal && state.status !== "completed") return state
    return {
      ...state,
      responseCompleted: true,
      receivedText: String(payload.content ?? state.receivedText),
      reasoningSummary: String(payload.reasoningSummary ?? state.reasoningSummary)
    }
  }
  if (event.type === "run.completed") {
    if (terminal) return state
    return {
      ...state,
      status: "completed",
      responseCompleted: true,
      completedAt: String(payload.completedAt ?? event.timestamp ?? "") || undefined
    }
  }
  if (event.type === "run.cancelled") {
    if (terminal) return state
    return {
      ...state,
      status: "cancelled",
      responseCompleted: true,
      completedAt: String(payload.completedAt ?? event.timestamp ?? "") || undefined
    }
  }
  if (event.type === "error") {
    if (terminal) return state
    return {
      ...state,
      status: "error",
      responseCompleted: true,
      completedAt: String(event.timestamp ?? "") || undefined,
      errorMessage: String(payload.message ?? "Agent 任务执行失败")
    }
  }
  if (event.type === "run.started") {
    return terminal ? state : { ...state, status: "queued" }
  }
  if (EXECUTION_TYPES.has(event.type)) {
    const executionEvent = projectExecutionEvent(event)
    return {
      ...state,
      status: statusFromExecution(String(event.status ?? payload.status ?? "executing"), state.status),
      reasoningSummary:
        event.type === "reasoning.summary"
          ? String(payload.summary ?? state.reasoningSummary)
          : state.reasoningSummary,
      execution: {
        currentLabel:
          event.type === "tool.progress"
            ? state.execution.currentLabel
            : executionEvent.label,
        events: upsertExecutionEvent(state.execution.events, executionEvent)
      }
    }
  }
  return state
}

function projectExecutionEvent(event: AgentStreamEvent): AgentExecutionEvent {
  const payload = event.payload ?? {}
  return {
    id: event.eventId ?? `${event.runId ?? "run"}:${event.sequence}`,
    sequence: event.sequence,
    stepId: String(payload.stepId ?? event.eventId ?? `${event.type}:${event.sequence}`),
    type: event.type,
    label: String(payload.label ?? "Agent 正在处理"),
    summary: String(payload.summary ?? ""),
    status: String(payload.status ?? event.status ?? "running"),
    timestamp: event.timestamp,
    completedAt: payload.completedAt ? String(payload.completedAt) : undefined,
    durationMs:
      typeof payload.durationMs === "number" ? payload.durationMs : undefined,
    toolLabel: payload.toolLabel ? String(payload.toolLabel) : undefined
  }
}

function upsertExecutionEvent(
  events: AgentExecutionEvent[],
  incoming: AgentExecutionEvent
): AgentExecutionEvent[] {
  const index = events.findIndex((event) => event.stepId === incoming.stepId)
  if (index < 0) return [...events, incoming]
  const current = events[index]
  const next = [...events]
  next[index] = {
    ...current,
    ...incoming,
    id: current.id,
    timestamp: current.timestamp ?? incoming.timestamp
  }
  return next
}

function statusFromExecution(status: string, current: AgentRunStatus): AgentRunStatus {
  if (TERMINAL_STATUSES.has(current)) return current
  if (status === "planning") return "planning"
  if (status === "waiting_approval") return "waiting_approval"
  return "executing"
}
