import { describe, expect, it } from "@jest/globals"

import {
  createAgentRunState,
  reduceAgentStreamEvents
} from "../src/agent-workbench/stream-reducer"
import type { AgentStreamEvent } from "../src/agent-workbench/contracts"

function event(
  sequence: number,
  type: AgentStreamEvent["type"],
  payload: Record<string, unknown> = {}
): AgentStreamEvent {
  return {
    eventId: `run-1:${sequence}`,
    sequence,
    eventSequence: sequence,
    runId: "run-1",
    conversationId: "session-1",
    messageId: "message-1",
    type,
    timestamp: `2026-08-02T00:00:0${sequence}+00:00`,
    payload
  }
}

describe("Agent stream reducer", () => {
  it("buffers out-of-order events and commits only a contiguous sequence", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")

    const buffered = reduceAgentStreamEvents(initial, [
      event(2, "response.delta", { delta: "系统" })
    ])
    const completed = reduceAgentStreamEvents(buffered, [
      event(1, "response.started")
    ])

    expect(buffered.lastSequence).toBe(0)
    expect(buffered.receivedText).toBe("")
    expect(completed.lastSequence).toBe(2)
    expect(completed.receivedText).toBe("系统")
  })

  it("deduplicates replayed events", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const delta = event(1, "response.delta", { delta: "储能" })

    const state = reduceAgentStreamEvents(initial, [delta, delta])

    expect(state.receivedText).toBe("储能")
    expect(state.lastSequence).toBe(1)
  })

  it("does not reactivate a cancelled run when late deltas arrive", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const cancelled = reduceAgentStreamEvents(initial, [
      event(1, "run.cancelled", { status: "cancelled" })
    ])
    const late = reduceAgentStreamEvents(cancelled, [
      event(2, "response.delta", { delta: "迟到内容" })
    ])

    expect(late.status).toBe("cancelled")
    expect(late.receivedText).toBe("")
  })

  it("keeps execution timeline separate from response deltas and heartbeats", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "phase.changed", {
        label: "正在读取实时遥测",
        summary: "读取 A-03 温度和运行状态",
        status: "running",
        stepId: "telemetry"
      }),
      event(2, "response.delta", { delta: "当前" }),
      event(3, "heartbeat")
    ])

    expect(state.execution.currentLabel).toBe("正在读取实时遥测")
    expect(state.execution.events).toHaveLength(1)
    expect(state.receivedText).toBe("当前")
  })

  it("accepts a canonical response completion after run completion without reactivating", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "run.completed", { status: "completed" }),
      event(2, "response.completed", { content: "最终完整回答" })
    ])

    expect(state.status).toBe("completed")
    expect(state.receivedText).toBe("最终完整回答")
    expect(state.responseCompleted).toBe(true)
  })

  it("merges tool progress into one timeline item instead of duplicating the step", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "tool.started", {
        label: "读取实时遥测",
        summary: "开始读取 A-03 温度",
        status: "running",
        stepId: "tool:telemetry",
        toolLabel: "实时遥测"
      }),
      event(2, "tool.progress", {
        label: "读取实时遥测",
        summary: "已读取温度与功率",
        status: "running",
        stepId: "tool:telemetry",
        toolLabel: "实时遥测"
      }),
      event(3, "tool.completed", {
        label: "读取实时遥测",
        summary: "实时遥测读取完成",
        status: "completed",
        stepId: "tool:telemetry",
        toolLabel: "实时遥测"
      })
    ])

    expect(state.execution.events).toHaveLength(1)
    expect(state.execution.events[0]).toMatchObject({
      sequence: 3,
      stepId: "tool:telemetry",
      status: "completed",
      summary: "实时遥测读取完成",
      toolLabel: "实时遥测"
    })
  })

  it("projects workflow step lifecycle events into one ordered timeline item", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "workflow.step.started", {
        label: "关联影响因素",
        summary: "开始关联环境与负载",
        status: "running",
        stepId: "workflow:correlation"
      }),
      event(2, "workflow.step.completed", {
        label: "关联影响因素",
        summary: "已完成环境与负载关联",
        status: "completed",
        stepId: "workflow:correlation"
      })
    ])

    expect(state.execution.events).toHaveLength(1)
    expect(state.execution.events[0]).toMatchObject({
      sequence: 2,
      stepId: "workflow:correlation",
      status: "completed"
    })
  })

  it("keeps error terminal when completion and response events arrive late", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "error", { message: "上游模型不可用" }),
      event(2, "response.delta", { delta: "迟到内容" }),
      event(3, "run.completed", { status: "completed" })
    ])

    expect(state.status).toBe("error")
    expect(state.receivedText).toBe("")
    expect(state.errorMessage).toBe("上游模型不可用")
  })

  it("maps planning and approval phases without touching response text", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const planning = reduceAgentStreamEvents(initial, [
      event(1, "phase.changed", {
        label: "正在理解任务",
        status: "planning",
        stepId: "intent"
      })
    ])
    const approval = reduceAgentStreamEvents(planning, [
      event(2, "phase.changed", {
        label: "等待确认",
        status: "waiting_approval",
        stepId: "approval"
      })
    ])

    expect(planning.status).toBe("planning")
    expect(approval.status).toBe("waiting_approval")
    expect(approval.receivedText).toBe("")
  })

  it("keeps completed terminal against late start, cancellation and error events", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "run.completed", { completedAt: "2026-08-02T00:00:01+00:00" }),
      event(2, "run.started"),
      event(3, "response.started"),
      event(4, "run.cancelled"),
      event(5, "error", { message: "迟到错误" })
    ])

    expect(state.status).toBe("completed")
    expect(state.completedAt).toBe("2026-08-02T00:00:01+00:00")
    expect(state.errorMessage).toBe("")
  })

  it("keeps cancelled terminal against late response completion and run completion", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "run.cancelled"),
      event(2, "response.started"),
      event(3, "response.completed", { content: "迟到最终内容" }),
      event(4, "run.completed")
    ])

    expect(state.status).toBe("cancelled")
    expect(state.receivedText).toBe("")
  })

  it("merges reasoning and workflow lifecycle fields with safe defaults", () => {
    const initial = createAgentRunState("run-1", "session-1", "message-1")
    const state = reduceAgentStreamEvents(initial, [
      event(1, "reasoning.summary", {
        summary: "已关联温度、功率和环境因素",
        status: "running",
        stepId: "reasoning"
      }),
      event(2, "workflow.started", {
        label: "执行诊断工作流",
        status: "running",
        stepId: "workflow:diagnosis"
      }),
      event(3, "workflow.completed", {
        label: "执行诊断工作流",
        summary: "诊断工作流完成",
        status: "completed",
        stepId: "workflow:diagnosis",
        completedAt: "2026-08-02T00:00:03+00:00",
        durationMs: 2000
      }),
      event(4, "phase.changed")
    ])

    expect(state.reasoningSummary).toBe("已关联温度、功率和环境因素")
    expect(state.execution.events).toHaveLength(3)
    expect(state.execution.events[1]).toMatchObject({
      status: "completed",
      durationMs: 2000,
      completedAt: "2026-08-02T00:00:03+00:00"
    })
    expect(state.execution.events[2].label).toBe("Agent 正在处理")
  })
})
