import { afterEach, beforeEach, describe, expect, it, jest as vi } from "@jest/globals"

import {
  clearAgentSession,
  ensureAgentSession,
  isStaleSessionError,
  loadAgentRun,
  resolveAgentToken,
  streamAgentRun,
  submitAgentTurn
} from "../src/agent-workbench/agent-stream-client"
import type { AgentStreamEvent } from "../src/agent-workbench/contracts"
import { restoreGlobalStubs, stubGlobal } from "./test-global-stubs"

let storage: MemoryStorage

beforeEach(() => {
  storage = new MemoryStorage()
  stubGlobal("sessionStorage", storage)
})

afterEach(() => restoreGlobalStubs())

describe("Agent stream client", () => {
  it("reconnects a cleanly closed non-terminal stream from the last sequence", async () => {
    const urls: string[] = []
    const requests: RequestInit[] = []
    const first = sseResponse(event(1, "response.delta", { delta: "当前" }))
    const second = sseResponse(event(2, "run.completed", { status: "completed" }))
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      urls.push(String(input))
      requests.push(init ?? {})
      return urls.length === 1 ? first : second
    })
    stubGlobal("fetch", fetchMock)
    const received: AgentStreamEvent[] = []

    const sequence = await streamAgentRun({
      runId: "run-reconnect-1",
      token: "test-token",
      signal: new AbortController().signal,
      onEvents: (events) => received.push(...events)
    })

    expect(sequence).toBe(2)
    expect(urls).toHaveLength(2)
    expect(urls[1]).toContain("afterSequence=1")
    expect(requests[1].headers).toMatchObject({
      Accept: "text/event-stream",
      Authorization: "Bearer test-token",
      "Last-Event-ID": "1"
    })
    expect(received.map((item) => item.type)).toEqual(["response.delta", "run.completed"])
  })

  it("creates, caches and clears a station-scoped Agent session", async () => {
    const fetchMock = vi.fn(async () => envelope({ session: { session_id: "session-a" } }, 201))
    stubGlobal("fetch", fetchMock)

    const first = await ensureAgentSession("station-a", "token-a")
    const cached = await ensureAgentSession("station-a", "token-a")
    clearAgentSession("station-a")

    expect(first).toBe("session-a")
    expect(cached).toBe("session-a")
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(storage.getItem("digitalTwin.agentSessionId:station-a")).toBeNull()
  })

  it("uses an explicitly stored access token without bootstrapping", async () => {
    storage.setItem("station.accessToken", "stored-token")
    const fetchMock = vi.fn()
    stubGlobal("fetch", fetchMock)

    await expect(resolveAgentToken()).resolves.toBe("stored-token")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("submits turns and loads snapshots through authenticated Control endpoints", async () => {
    const responses = [
      envelope({ run: { run_id: "run-a", session_id: "session-a", status: "running" } }, 202),
      envelope({ snapshot: { run_id: "run-a", session_id: "session-a", run_status: "completed" } })
    ]
    const fetchMock = vi.fn(async (
      _input: string | URL | Request,
      _init?: RequestInit
    ) => responses.shift() as Response)
    stubGlobal("fetch", fetchMock)

    await expect(submitAgentTurn("session-a", { text: "查询状态" }, "token-a")).resolves.toMatchObject({
      runId: "run-a",
      sessionId: "session-a",
      streamUrl: "/api/v1/sessions/session-a/runs/run-a"
    })
    await expect(loadAgentRun("run-a", "session-a", "token-a")).resolves.toMatchObject({
      runId: "run-a",
      status: "completed"
    })

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/sessions/session-a/turns",
      "/api/v1/sessions/session-a/runs/run-a"
    ])
  })

  it("normalizes stale-session error envelopes for automatic recovery", async () => {
    stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        error: { code: "agent_session_not_found", message: "session missing" }
      }), { status: 404, headers: { "Content-Type": "application/json" } }))
    )

    let received: unknown
    try {
      await submitAgentTurn("missing", {}, "token-a")
    } catch (error) {
      received = error
    }

    expect(isStaleSessionError(received)).toBe(true)
  })
})

function event(
  sequence: number,
  type: AgentStreamEvent["type"],
  payload: Record<string, unknown>
): AgentStreamEvent {
  return { sequence, type, payload }
}

function sseResponse(streamEvent: AgentStreamEvent): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        new TextEncoder().encode(`data: ${JSON.stringify(streamEvent)}\n\n`)
      )
      controller.close()
    }
  })
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" }
  })
}

function envelope(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { "Content-Type": "application/json" }
  })
}

class MemoryStorage implements Storage {
  private values = new Map<string, string>()

  get length(): number {
    return this.values.size
  }

  clear(): void {
    this.values.clear()
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null
  }

  removeItem(key: string): void {
    this.values.delete(key)
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }
}
