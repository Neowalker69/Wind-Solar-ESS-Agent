import { describe, expect, it } from "@jest/globals"

import {
  approvalSnapshotSchema,
  createSessionInputSchema,
  runtimeEventSchema,
  toRuntimeTurnRequest,
  turnInputSchema
} from "../src/contracts/control"

describe("Harness Control I/O contracts", () => {
  it("accepts a browser session and context projection", () => {
    const result = createSessionInputSchema.safeParse({
      user: { user_id: "operator-1", role: "operator", site_id: "site-a" },
      context: { selected_asset_id: "pump-101", environment: "dev" }
    })

    expect(result.success).toBe(true)
  })

  it("rejects a session without a user identity", () => {
    const result = createSessionInputSchema.safeParse({
      context: { selected_asset_id: "pump-101" }
    })

    expect(result.success).toBe(false)
  })

  it("accepts explicit tool and skill references without exposing handlers", () => {
    const request = turnInputSchema.parse({
      text: "检查泵的当前状态",
      context: { selected_asset_id: "pump-101", environment: "dev" },
      tool_refs: [{ tool_id: "asset.get_status", version: "1.0.0" }],
      skill_refs: [{ skill_id: "diagnosis.basic", version: "1.0.0" }],
      policy: { visible_tool_ids: ["asset.get_status"], workflow_stage: "diagnosis" },
      approval: { status: "not_required" }
    })

    const runtimeRequest = toRuntimeTurnRequest("session-1", request)

    expect(runtimeRequest.session_id).toBe("session-1")
    expect(runtimeRequest.tool_refs).toEqual([{ tool_id: "asset.get_status", version: "1.0.0" }])
    expect(runtimeRequest).not.toHaveProperty("handler")
  })

  it("rejects browser-provided handler or connector configuration", () => {
    const result = turnInputSchema.safeParse({
      text: "检查泵的当前状态",
      context: {},
      tool_refs: [{ tool_id: "asset.get_status", version: "1.0.0" }],
      skill_refs: [],
      policy: { visible_tool_ids: ["asset.get_status"] },
      approval: { status: "not_required" },
      handler: "dangerous.module:handle"
    })

    expect(result.success).toBe(false)
  })

  it("rejects invalid approval decisions", () => {
    expect(approvalSnapshotSchema.safeParse({ status: "approved" }).success).toBe(false)
    expect(approvalSnapshotSchema.safeParse({ status: "required" }).success).toBe(true)
  })

  it("accepts only declared runtime event types", () => {
    expect(runtimeEventSchema.safeParse({
      event_id: "event-1",
      event_type: "tool.completed",
      session_id: "session-1",
      run_id: "run-1",
      sequence: 1,
      occurred_at: "2026-07-11T00:00:00Z",
      payload: { tool_id: "asset.get_status" }
    }).success).toBe(true)
    expect(runtimeEventSchema.safeParse({
      event_id: "event-1",
      event_type: "connector.internal_error",
      session_id: "session-1",
      run_id: "run-1",
      sequence: 1,
      occurred_at: "2026-07-11T00:00:00Z",
      payload: {}
    }).success).toBe(false)
  })
})
