import type { AgentStreamEvent, AgentTurnAccepted } from "./contracts"
import { AgentSseParser } from "./sse-parser"

const TOKEN_KEY = "station.accessToken"
let runtimeToken = ""

interface GatewayError extends Error {
  code?: string
  traceId?: string
  status?: number
}

async function readEnvelope<T>(response: Response): Promise<T> {
  const envelope = await response.json().catch(() => null)
  if (!response.ok || envelope?.error) {
    const error = new Error(
      envelope?.error?.message ?? envelope?.detail ?? `Agent Gateway HTTP ${response.status}`
    ) as GatewayError
    error.code = envelope?.error?.code ?? envelope?.detail
    error.traceId = envelope?.trace_id
    error.status = response.status
    throw error
  }
  if (!envelope || !("data" in envelope)) throw new Error("Agent Gateway 返回了无效响应")
  return envelope.data as T
}

export async function resolveAgentToken(signal?: AbortSignal): Promise<string> {
  const stored = sessionStorage.getItem(TOKEN_KEY)
  if (stored) return stored
  if (runtimeToken) return runtimeToken
  throw new Error("Control 需要有效的登录凭据")
}

function sessionKey(siteId: string): string {
  return `digitalTwin.agentSessionId:${siteId}`
}

export function clearAgentSession(siteId: string): void {
  sessionStorage.removeItem(sessionKey(siteId))
}

export async function ensureAgentSession(
  siteId: string,
  token: string,
  signal?: AbortSignal
): Promise<string> {
  const current = sessionStorage.getItem(sessionKey(siteId))
  if (current) return current
  const response = await fetch("/api/v1/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      user: {
        user_id: jwtSubject(token),
        role: "operator",
        site_id: siteId
      },
      context: { environment: "dev", attributes: { trusted_site_id: siteId } }
    }),
    signal
  })
  const payload = await readEnvelope<{ session: { session_id: string } }>(response)
  sessionStorage.setItem(sessionKey(siteId), payload.session.session_id)
  return payload.session.session_id
}

export async function submitAgentTurn(
  sessionId: string,
  request: Record<string, unknown>,
  token: string,
  signal?: AbortSignal
): Promise<AgentTurnAccepted> {
  const response = await fetch(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/turns`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(request),
      signal
    }
  )
  const payload = await readEnvelope<{
    run: { run_id: string; session_id: string; status: string }
  }>(response)
  return {
    runId: payload.run.run_id,
    sessionId: payload.run.session_id,
    messageId: `message_${payload.run.run_id}`,
    status: payload.run.status as AgentTurnAccepted["status"],
    streamUrl: `/api/v1/sessions/${encodeURIComponent(payload.run.session_id)}/runs/${encodeURIComponent(payload.run.run_id)}`
  }
}

export interface StreamAgentRunOptions {
  runId: string
  sessionId?: string
  streamUrl?: string
  token: string
  signal: AbortSignal
  afterSequence?: number
  onEvents: (events: AgentStreamEvent[]) => void
  onConnectionState?: (state: "connecting" | "connected" | "reconnecting") => void
}

export async function streamAgentRun(options: StreamAgentRunOptions): Promise<number> {
  let lastSequence = options.afterSequence ?? 0
  let attempt = 0
  let terminalReceived = false
  while (!options.signal.aborted) {
    options.onConnectionState?.(attempt ? "reconnecting" : "connecting")
    try {
      const baseUrl = options.streamUrl ?? `/api/v1/sessions/${encodeURIComponent(options.sessionId ?? "")}/runs/${encodeURIComponent(options.runId)}`
      const separator = baseUrl.includes("?") ? "&" : "?"
      const response = await fetch(`${baseUrl}${separator}afterSequence=${lastSequence}`, {
        headers: {
          Accept: "text/event-stream",
          Authorization: `Bearer ${options.token}`,
          ...(lastSequence ? { "Last-Event-ID": String(lastSequence) } : {})
        },
        signal: options.signal
      })
      if (!response.ok) await readEnvelope(response)
      if (!response.body) throw new Error("浏览器不支持 Agent 流式响应")
      options.onConnectionState?.("connected")
      const parser = new AgentSseParser()
      const reader = response.body.getReader()
      while (true) {
        const { value, done } = await reader.read()
        const events = value ? parser.push(value) : []
        if (events.length) {
          lastSequence = Math.max(lastSequence, ...events.map((event) => event.sequence))
          terminalReceived ||= events.some(isTerminalEvent)
          options.onEvents(events)
        }
        if (done) {
          const finalEvents = parser.finish()
          if (finalEvents.length) {
            lastSequence = Math.max(lastSequence, ...finalEvents.map((event) => event.sequence))
            terminalReceived ||= finalEvents.some(isTerminalEvent)
            options.onEvents(finalEvents)
          }
          if (terminalReceived) return lastSequence
          throw new Error("Agent SSE closed before a terminal event")
        }
      }
    } catch (error) {
      if (options.signal.aborted || isAbortError(error)) throw error
      if (attempt >= 5) throw error
      attempt += 1
      options.onConnectionState?.("reconnecting")
      await abortableDelay(Math.min(5_000, 250 * 2 ** (attempt - 1)), options.signal)
    }
  }
  throw new DOMException("Aborted", "AbortError")
}

function isTerminalEvent(event: AgentStreamEvent): boolean {
  return ["run.completed", "run.cancelled", "error"].includes(event.type)
}

export async function loadAgentRun(
  runId: string,
  sessionId: string,
  token: string,
  signal?: AbortSignal
): Promise<{
  runId: string
  sessionId: string
  clientMessageId: string
  status: string
  events: AgentStreamEvent[]
}> {
  const response = await fetch(`/api/v1/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal
  })
  const payload = await readEnvelope<{
    snapshot: { session_id: string; run_id: string; run_status: string }
  }>(response)
  return {
    runId: payload.snapshot.run_id,
    sessionId: payload.snapshot.session_id,
    clientMessageId: `message_${payload.snapshot.run_id}`,
    status: payload.snapshot.run_status,
    events: []
  }
}

export function isStaleSessionError(error: unknown): boolean {
  const gatewayError = error as GatewayError
  return gatewayError?.status === 404 && String(gatewayError.code).includes("agent_session_not_found")
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError"
}

function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = globalThis.setTimeout(resolve, milliseconds)
    signal.addEventListener(
      "abort",
      () => {
        globalThis.clearTimeout(timer)
        reject(new DOMException("Aborted", "AbortError"))
      },
      { once: true }
    )
  })
}

function jwtSubject(token: string): string {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))
    if (payload.sub) return String(payload.sub)
  } catch {
    // The server remains authoritative and will reject malformed credentials.
  }
  return "invalid-subject"
}
