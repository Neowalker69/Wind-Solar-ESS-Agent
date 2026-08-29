import { describe, expect, it, jest as vi } from "@jest/globals"

import {
  createRuntimeClient,
  fromGrpcRuntimeEvent,
  fromGrpcRuntimeSnapshot,
  GrpcRuntimeClient,
  projectRuntimeStartError,
  type RuntimeGrpcTransport,
  toGrpcStartTurnRequest
} from "../src/server/runtime-client"

describe("gRPC Runtime Client mappings", () => {
  it("projects provider failures into a stable gateway error", () => {
    expect(projectRuntimeStartError({
      code: 2,
      details: "Unexpected ModelProviderError: bailian request failed before receiving a response"
    })).toEqual({
      status: 502,
      code: "model_provider_unavailable",
      message: "模型服务暂不可用，请稍后重试"
    })
  })

  it("converts Control I/O into the versioned StartTurn transport request", () => {
    const request = toGrpcStartTurnRequest({
      session_id: "session-1",
      text: "检查泵状态",
      context: { selected_asset_id: "pump-101", environment: "dev" },
      tool_refs: [{ tool_id: "opcua_read_node", version: "0.1.0" }],
      skill_refs: [],
      policy: { visible_tool_ids: ["opcua_read_node"], workflow_stage: "data.query" },
      approval: { status: "not_required" }
    })

    expect(request).toMatchObject({
      sessionId: "session-1",
      toolRefs: [{ toolId: "opcua_read_node", version: "0.1.0" }],
      approval: { status: "APPROVAL_STATUS_NOT_REQUIRED" }
    })
    expect(request).not.toHaveProperty("handler")
  })

  it("projects a Runtime Snapshot without leaking transport-only fields", () => {
    const snapshot = fromGrpcRuntimeSnapshot({
      sessionId: "session-1",
      runId: "run-1",
      context: { selectedAssetId: "pump-101", environment: "dev", attributes: {} },
      tools: [{
        toolId: "opcua_read_node",
        version: "0.1.0",
        displayName: "读取节点",
        description: "读取 OPC UA 节点",
        inputSchema: { fields: {} },
        outputSchema: { fields: {} }
      }],
      skills: [],
      runStatus: "RUN_STATUS_RUNNING"
    })

    expect(snapshot).toMatchObject({
      session_id: "session-1",
      run_id: "run-1",
      context: { selected_asset_id: "pump-101", environment: "dev" },
      tools: [{ tool_id: "opcua_read_node", version: "0.1.0" }],
      run_status: "running"
    })
  })

  it("preserves the authoritative Runtime event sequence", () => {
    expect(fromGrpcRuntimeEvent({
      eventId: "run-1:17",
      eventType: "RUNTIME_EVENT_TYPE_PLAN_UPDATED",
      sessionId: "session-1",
      runId: "run-1",
      sequence: 17,
      payload: { fields: {} }
    })).toMatchObject({ sequence: 17 })
  })

  it("uses the gRPC transport for StartTurn and Runtime Snapshot", async () => {
    const transport: RuntimeGrpcTransport = {
      StartTurn: vi.fn((_request: object, callback: (error: Error | null, response: unknown) => void) => callback(null, {
        runId: "run-1",
        sessionId: "session-1",
        status: "RUN_STATUS_RUNNING"
      })),
      StreamRunEvents: vi.fn(() => emptyGrpcStream()),
      GetRuntimeSnapshot: vi.fn((_request: object, callback: (error: Error | null, response: unknown) => void) => callback(null, {
        sessionId: "session-1",
        runId: "run-1",
        context: {},
        tools: [],
        skills: [],
        runStatus: "RUN_STATUS_COMPLETED"
      }))
    }
    const client = new GrpcRuntimeClient("unused", transport)

    await expect(client.startTurn({
      session_id: "session-1",
      text: "检查泵状态",
      context: {},
      tool_refs: [],
      skill_refs: [],
      policy: { visible_tool_ids: [] },
      approval: { status: "not_required" }
    })).resolves.toMatchObject({ run_id: "run-1", status: "running" })
    await expect(client.getRuntimeSnapshot("session-1", "run-1"))
      .resolves.toMatchObject({ run_status: "completed" })

    await collectAsync(client.streamRunEvents("run-1", 12))
    expect(transport.StreamRunEvents).toHaveBeenCalledWith({ runId: "run-1", afterSequence: 12 })
  })

  it("maps numeric enum values returned by the real proto-loader transport", async () => {
    const transport: RuntimeGrpcTransport = {
      StartTurn: vi.fn((_request: object, callback: (error: Error | null, response: unknown) => void) => callback(null, {
        runId: "run-real",
        sessionId: "session-real",
        status: 4
      })),
      StreamRunEvents: vi.fn(() => emptyGrpcStream()),
      GetRuntimeSnapshot: vi.fn((_request: object, callback: (error: Error | null, response: unknown) => void) => callback(null, {
        sessionId: "session-real",
        runId: "run-real",
        context: {},
        tools: [],
        skills: [],
        runStatus: 4
      }))
    }
    const client = new GrpcRuntimeClient("unused", transport)

    await expect(client.startTurn({
      session_id: "session-real",
      text: "检查会话",
      context: {},
      tool_refs: [],
      skill_refs: [],
      policy: { visible_tool_ids: [] },
      approval: { status: "not_required" }
    })).resolves.toMatchObject({ status: "completed" })
    await expect(client.getRuntimeSnapshot("session-real", "run-real"))
      .resolves.toMatchObject({ run_status: "completed" })
    expect(fromGrpcRuntimeEvent({
      eventId: "event-real",
      eventType: 8,
      sessionId: "session-real",
      runId: "run-real",
      payload: {}
    })).toMatchObject({ event_type: "run.completed" })
  })

  it("propagates a gRPC transport failure and keeps the test-only client isolated", async () => {
    const transport: RuntimeGrpcTransport = {
      StartTurn: vi.fn((_request: object, callback: (error: Error | null, response: unknown) => void) => callback(new Error("runtime unavailable"), null)),
      StreamRunEvents: vi.fn(() => emptyGrpcStream()),
      GetRuntimeSnapshot: vi.fn()
    }
    const client = new GrpcRuntimeClient("unused", transport)

    await expect(client.startTurn({
      session_id: "session-1",
      text: "检查泵状态",
      context: {},
      tool_refs: [],
      skill_refs: [],
      policy: { visible_tool_ids: [] },
      approval: { status: "not_required" }
    })).rejects.toThrow("runtime unavailable")
    await expect(createRuntimeClient().getRuntimeSnapshot("session-1", "run-1"))
      .resolves.toMatchObject({ run_status: "running" })
  })
})

function emptyGrpcStream() {
  return {
    async *[Symbol.asyncIterator]() {}
  } as unknown as import("@grpc/grpc-js").ClientReadableStream<unknown>
}

async function collectAsync<T>(events: AsyncIterable<T>): Promise<T[]> {
  const collected: T[] = []
  for await (const event of events) collected.push(event)
  return collected
}
