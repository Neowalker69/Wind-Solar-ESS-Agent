import { describe, expect, it, jest } from "@jest/globals"
import { AgentSseParser } from "../src/agent-workbench/sse-parser"
import { createAgentRunState, reduceAgentStreamEvents } from "../src/agent-workbench/stream-reducer"
import { createControlSessionId } from "../src/server/control-auth"
import { controlAuthHeaders } from "./control-auth-helper"

controlAuthHeaders()
const currentSessionId = createControlSessionId({
  userId: "operator-1",
  role: "operator",
  tenantId: "tenant_lab"
})

jest.unstable_mockModule("../src/server/runtime-client", () => ({
  createRuntimeClient: () => ({
    streamRunEvents: async function *(runId: string, afterSequence = 0) {
      if (runId === "run-error") {
        if (afterSequence < 1) {
          yield {
            event_id: "run-error:1",
            event_type: "run.accepted",
            session_id: currentSessionId,
            run_id: "run-error",
            occurred_at: "2026-08-22T03:00:00.000Z",
            payload: { event_type: "RunStart" },
            sequence: 1
          }
        }
        throw new Error("runtime stream disconnected")
      }
      const events = [{
        event_id: "run-1:1",
        event_type: "run.accepted",
        session_id: currentSessionId,
        run_id: "run-1",
        occurred_at: "2026-08-22T02:00:00.000Z",
        payload: { event_type: "RunStart" },
        sequence: 1
      }, {
        event_id: "run-1:2",
        event_type: "tool.completed",
        session_id: currentSessionId,
        run_id: "run-1",
        occurred_at: "2026-08-22T02:00:01.000Z",
        payload: { event_type: "tool.completed", tool_id: "asset.get_asset", status: "ok" },
        sequence: 2
      }, {
        event_id: "run-1:3",
        event_type: "tool.completed",
        session_id: currentSessionId,
        run_id: "run-1",
        occurred_at: "2026-08-22T02:00:02.000Z",
        payload: { event_type: "AfterToolCall", tool_id: "asset.get_asset", status: "ok" },
        sequence: 3
      }, {
        event_id: "run-1:4",
        event_type: "plan.updated",
        session_id: currentSessionId,
        run_id: "run-1",
        occurred_at: "2026-08-22T02:00:03.000Z",
        payload: { event_type: "assistant.started" },
        sequence: 4
      }, {
        event_id: "run-1:5",
        event_type: "plan.updated",
        session_id: currentSessionId,
        run_id: "run-1",
        occurred_at: "2026-08-22T02:00:04.000Z",
        payload: { event_type: "assistant.delta", delta: "设备运行正常" },
        sequence: 5
      }, {
        event_id: "run-1:6",
        event_type: "plan.updated",
        session_id: currentSessionId,
        run_id: "run-1",
        occurred_at: "2026-08-22T02:00:05.000Z",
        payload: { event_type: "assistant.completed", content: "设备运行正常" },
        sequence: 6
      }, {
        event_id: "run-1:7",
        event_type: "run.completed",
        session_id: currentSessionId,
        run_id: "run-1",
        occurred_at: "2026-08-22T02:00:06.000Z",
        payload: { event_type: "RunStop" },
        sequence: 7
      }]
      for (const event of events) {
        if (event.sequence > afterSequence) yield event
      }
    },
    getRuntimeSnapshot: async () => ({
      session_id: currentSessionId,
      run_id: "run-1",
      context: { selected_asset_id: "pump-101", environment: "dev" },
      tools: [{ tool_id: "opcua_read_node", version: "0.1.0", display_name: "读取节点", description: "读取 OPC UA 节点" }],
      skills: [],
      run_status: "running"
    })
  })
}))

const { GET } = await import("../app/api/v1/sessions/[sessionId]/runs/[runId]/route")

describe("Runtime Snapshot route", () => {
  it("returns the server-side projected context, tool and skill catalog", async () => {
    const response = await GET(new Request(`http://localhost/api/v1/sessions/${currentSessionId}/runs/run-1`, {
      headers: controlAuthHeaders()
    }), {
      params: Promise.resolve({ sessionId: currentSessionId, runId: "run-1" })
    })

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      data: {
        snapshot: {
          session_id: currentSessionId,
          context: { selected_asset_id: "pump-101" },
          tools: [{ tool_id: "opcua_read_node", version: "0.1.0" }]
        }
      }
    })
  })

  it("bridges the authenticated Runtime stream as browser SSE", async () => {
    const response = await GET(new Request(`http://localhost/api/v1/sessions/${currentSessionId}/runs/run-1?afterSequence=1`, {
      headers: { ...controlAuthHeaders(), Accept: "text/event-stream", "Last-Event-ID": "2" }
    }), {
      params: Promise.resolve({ sessionId: currentSessionId, runId: "run-1" })
    })

    expect(response.headers.get("Content-Type")).toContain("text/event-stream")
    const body = await response.text()
    expect(body).not.toContain('id: 1\n')
    expect(body).not.toContain('id: 2\n')
    expect(body).toContain('id: 7\n')
    expect(body).toContain('"type":"run.completed"')
  })

  it("keeps the browser stream consumable when the Runtime emits an internal event", async () => {
    const response = await GET(new Request(`http://localhost/api/v1/sessions/${currentSessionId}/runs/run-1`, {
      headers: { ...controlAuthHeaders(), Accept: "text/event-stream" }
    }), {
      params: Promise.resolve({ sessionId: currentSessionId, runId: "run-1" })
    })

    const parser = new AgentSseParser()
    const bytes = new TextEncoder().encode(await response.text())
    const events = [...parser.push(bytes), ...parser.finish()]
    const state = reduceAgentStreamEvents(
      createAgentRunState("run-1", currentSessionId, "message-1"),
      events
    )

    expect(state.status).toBe("completed")
    expect(state.lastSequence).toBe(7)
    expect(state.receivedText).toBe("设备运行正常")
    expect(state.pendingEvents).toEqual({})
  })

  it("delivers a terminal error after the Runtime stream fails following progress", async () => {
    const response = await GET(new Request(`http://localhost/api/v1/sessions/${currentSessionId}/runs/run-error`, {
      headers: { ...controlAuthHeaders(), Accept: "text/event-stream" }
    }), {
      params: Promise.resolve({ sessionId: currentSessionId, runId: "run-error" })
    })

    const parser = new AgentSseParser()
    const bytes = new TextEncoder().encode(await response.text())
    const events = [...parser.push(bytes), ...parser.finish()]
    const state = reduceAgentStreamEvents(
      createAgentRunState("run-error", currentSessionId, "message-error"),
      events
    )

    expect(state.status).toBe("error")
    expect(state.lastSequence).toBe(2)
    expect(state.errorMessage).toBe("runtime stream disconnected")
    expect(state.pendingEvents).toEqual({})
  })
})
