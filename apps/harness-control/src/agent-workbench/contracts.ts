export type AgentRunStatus =
  | "queued"
  | "connecting"
  | "planning"
  | "executing"
  | "streaming"
  | "waiting_approval"
  | "reconnecting"
  | "completed"
  | "cancelled"
  | "error"
  | "failed"

export type AgentStreamEventType =
  | "run.started"
  | "phase.changed"
  | "reasoning.summary"
  | "workflow.started"
  | "workflow.step.started"
  | "workflow.step.completed"
  | "workflow.completed"
  | "tool.started"
  | "tool.progress"
  | "tool.completed"
  | "response.started"
  | "response.delta"
  | "response.completed"
  | "run.completed"
  | "run.cancelled"
  | "error"
  | "heartbeat"
  | "scene.action"

export interface AgentStreamEvent {
  eventId?: string
  sequence: number
  eventSequence?: number
  runId?: string
  conversationId?: string
  messageId?: string
  traceId?: string
  observationId?: string
  type: AgentStreamEventType
  timestamp?: string
  payload: Record<string, unknown>
  status?: string
  action?: { command?: string; assetId?: string; sceneNodeId?: string }
}

export interface AgentTurnAccepted {
  runId: string
  sessionId: string
  messageId: string
  status: AgentRunStatus
  streamUrl: string
}

export interface AgentExecutionEvent {
  id: string
  sequence: number
  stepId: string
  type: AgentStreamEventType
  label: string
  summary: string
  status: string
  timestamp?: string
  completedAt?: string
  durationMs?: number
  toolLabel?: string
}

export interface AgentExecutionState {
  currentLabel: string
  events: AgentExecutionEvent[]
}

export interface AgentRunState {
  runId: string
  conversationId: string
  messageId: string
  status: AgentRunStatus
  lastSequence: number
  receivedText: string
  responseCompleted: boolean
  reasoningSummary: string
  execution: AgentExecutionState
  pendingEvents: Record<number, AgentStreamEvent>
  errorMessage: string
  completedAt?: string
}
