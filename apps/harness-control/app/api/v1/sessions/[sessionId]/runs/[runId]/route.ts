import { NextResponse } from "next/server"

import type { RuntimeEvent } from "../../../../../../../src/contracts/control"
import { createRuntimeClient } from "../../../../../../../src/server/runtime-client"
import {
  authenticateControlRequest,
  authorizeControlSession,
  controlAuthErrorResponse
} from "../../../../../../../src/server/control-auth"

interface RouteContext {
  params: Promise<{ sessionId: string; runId: string }>
}

export async function GET(request: Request, context: RouteContext): Promise<NextResponse> {
  const { sessionId, runId } = await context.params
  try {
    const identity = authenticateControlRequest(request)
    authorizeControlSession(identity, sessionId)
  } catch (error) {
    return controlAuthErrorResponse(error) as NextResponse
  }
  const runtimeClient = createRuntimeClient()
  if (request.headers.get("Accept")?.includes("text/event-stream")) {
    const querySequence = Number(new URL(request.url).searchParams.get("afterSequence") ?? 0)
    const headerSequence = Number(request.headers.get("Last-Event-ID") ?? 0)
    const afterSequence = Math.max(
      Number.isFinite(querySequence) ? querySequence : 0,
      Number.isFinite(headerSequence) ? headerSequence : 0
    )
    return streamRuntimeEvents(runtimeClient, sessionId, runId, afterSequence) as unknown as NextResponse
  }
  const snapshot = await runtimeClient.getRuntimeSnapshot(sessionId, runId)

  return NextResponse.json({ data: { snapshot }, meta: {} })
}

function streamRuntimeEvents(
  runtimeClient: ReturnType<typeof createRuntimeClient>,
  sessionId: string,
  runId: string,
  afterSequence: number
): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      let currentSequence = afterSequence
      try {
        for await (const event of runtimeClient.streamRunEvents(runId, afterSequence)) {
          if (event.session_id !== sessionId) throw new Error("runtime_stream_session_mismatch")
          const projected = projectAgentEvent(event)
          currentSequence = Math.max(currentSequence, projected.sequence)
          controller.enqueue(encoder.encode(
            `id: ${projected.sequence}\nevent: ${projected.type}\ndata: ${JSON.stringify(projected)}\n\n`
          ))
        }
      } catch (error) {
        const sequence = currentSequence + 1
        const projected = {
          sequence,
          type: "error",
          runId,
          conversationId: sessionId,
          payload: { message: error instanceof Error ? error.message : "runtime_stream_failed" }
        }
        controller.enqueue(encoder.encode(
          `id: ${sequence}\nevent: error\ndata: ${JSON.stringify(projected)}\n\n`
        ))
      } finally {
        controller.close()
      }
    }
  })
  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no"
    }
  })
}

function projectAgentEvent(event: RuntimeEvent) {
  const sourceType = String(event.payload.event_type ?? "")
  const common = {
    eventId: event.event_id,
    sequence: event.sequence,
    runId: event.run_id,
    conversationId: event.session_id,
    timestamp: event.occurred_at
  }
  if (sourceType === "RunStart") return { ...common, type: "run.started", payload: { status: "queued" } }
  if (sourceType === "IntentClassified") return { ...common, type: "phase.changed", status: "planning", payload: { label: "已识别查询意图", status: "planning", ...event.payload } }
  if (sourceType === "BeforeToolDiscovery" || sourceType === "model.completed") return { ...common, type: "phase.changed", status: "planning", payload: { label: "Agent 正在规划", status: "planning", ...event.payload } }
  if (sourceType === "BeforeToolCall") return { ...common, type: "tool.started", status: "executing", payload: { label: `调用 ${String(event.payload.tool_id ?? "工具")}`, toolLabel: event.payload.tool_id, status: "executing", ...event.payload } }
  if (sourceType === "ObservationCaptured") return { ...common, type: "tool.progress", status: "executing", observationId: String(event.payload.observation_id ?? "") || undefined, payload: { label: "已记录工具观测", status: "executing", ...event.payload } }
  if (sourceType === "tool.completed") return { ...common, type: "tool.completed", status: String(event.payload.status ?? "completed"), observationId: String(event.payload.observation_id ?? "") || undefined, payload: { label: `${String(event.payload.tool_id ?? "工具")} 执行完成`, toolLabel: event.payload.tool_id, ...event.payload } }
  if (sourceType === "assistant.started") return { ...common, type: "response.started", payload: {} }
  if (sourceType === "assistant.delta") return { ...common, type: "response.delta", payload: { delta: event.payload.delta ?? "" } }
  if (sourceType === "assistant.completed") return { ...common, type: "response.completed", payload: { content: event.payload.content ?? "", reasoningSummary: event.payload.reasoning_summary ?? "" } }
  if (sourceType === "RunStop") return { ...common, type: "run.completed", payload: { status: "completed", completedAt: event.occurred_at } }
  if (sourceType === "RunFailed") return { ...common, type: "error", payload: { message: "Agent 运行失败", ...event.payload } }
  if (sourceType === "Heartbeat") return { ...common, type: "heartbeat", payload: {} }
  // Runtime sequence numbers are also the reconnect cursor. Even an internal
  // event must advance the browser reducer, otherwise every later event waits
  // forever behind the missing sequence number.
  return { ...common, type: "heartbeat", payload: { sourceEventType: sourceType || "unknown" } }
}
