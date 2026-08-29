import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it } from "@jest/globals"

import { AgentStreamingWorkbench, buildAgentRequest } from "../src/agent-workbench/AgentStreamingWorkbench"
import { useAgentWorkbenchStore } from "../src/agent-workbench/agent-workbench-store"
import { AgentExecutionStatus } from "../src/agent-workbench/components/AgentExecutionStatus"
import { StreamMarkdownRenderer } from "../src/agent-workbench/components/StreamMarkdownRenderer"
import type { AgentRunState, AgentStreamEvent } from "../src/agent-workbench/contracts"
import { createAgentRunState, reduceAgentStreamEvents } from "../src/agent-workbench/stream-reducer"

const startedAt = "2026-08-03T01:00:00.000Z"

beforeEach(() => {
  useAgentWorkbenchStore.setState({
    stationId: "ess-station-01",
    draft: "",
    messages: [],
    activeMessageId: ""
  })
})

describe("Response Streaming 方案 A 组件渲染", () => {
  it("inherits the selected device for implicit device queries but not broad queries", () => {
    const container = { id: "A-03", stationDeviceId: "ess-station-01.container-a-03" }

    const broad = buildAgentRequest("总结当前总体运行情况", "ess-station-01", container, [], "24h")
    const implicit = buildAgentRequest("当前温度是多少", "ess-station-01", container, [], "24h")
    const scoped = buildAgentRequest("查询 A-03 当前状态", "ess-station-01", container, [], "24h")

    expect(broad.context).not.toHaveProperty("selected_asset_id")
    expect((broad.tool_refs as Array<{ tool_id: string }>).map((item) => item.tool_id)).toContain("asset.list_assets")
    expect((broad.tool_refs as Array<{ tool_id: string }>).map((item) => item.tool_id)).not.toContain("telemetry.get_latest_value")
    expect(implicit.context).toHaveProperty("selected_asset_id", "ess-station-01.container-a-03")
    expect((implicit.tool_refs as Array<{ tool_id: string }>).map((item) => item.tool_id)).toContain("telemetry.get_latest_value")
    expect(scoped.context).toHaveProperty("selected_asset_id", "ess-station-01.container-a-03")
    expect((scoped.tool_refs as Array<{ tool_id: string }>).map((item) => item.tool_id)).toContain("telemetry.get_latest_value")

    const alias = buildAgentRequest("查询 A03 当前状态", "ess-station-01", container, [], "24h")
    expect(alias.context).toHaveProperty("selected_asset_id", "ess-station-01.container-a-03")

    const otherDevice = buildAgentRequest("查询 A24 当前状态", "ess-station-01", container, [], "24h")
    expect(otherDevice.context).not.toHaveProperty("selected_asset_id")
    expect((otherDevice.tool_refs as Array<{ tool_id: string }>).map((item) => item.tool_id)).toContain("telemetry.get_latest_value")
  })

  it("renders completed execution copy, fixed duration and timeline semantics", () => {
    const run = completedRun()
    const html = renderToStaticMarkup(
      createElement(AgentExecutionStatus, { run, startedAt })
    )

    expect(html).toContain("已完成思考和执行")
    expect(html).toContain("00m 05s")
    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain("执行事件时间线")
    expect(html).toContain("读取设备实时遥测")
    expect(html).toContain("实时遥测")
  })

  it("renders all non-success status copies without exposing hidden reasoning", () => {
    const copies = [
      ["queued", "任务已提交"],
      ["connecting", "正在连接 Agent"],
      ["planning", "思考与执行中"],
      ["waiting_approval", "等待确认后继续执行"],
      ["reconnecting", "正在恢复思考和执行"],
      ["cancelled", "已停止思考和执行"],
      ["failed", "思考和执行未完成"],
      ["error", "思考和执行未完成"]
    ] as const

    for (const [status, expected] of copies) {
      const run = { ...completedRun(), status, completedAt: undefined } as AgentRunState
      const html = renderToStaticMarkup(
        createElement(AgentExecutionStatus, { run, startedAt })
      )
      expect(html).toContain(expected)
      expect(html).not.toContain("raw_prompt")
    }
  })

  it("renders pending, running, waiting, cancelled and error timeline nodes", () => {
    const statuses = ["pending", "running", "waiting", "cancelled", "error"]
    const run = {
      ...completedRun(),
      status: "executing",
      completedAt: undefined,
      execution: {
        currentLabel: "正在执行分析",
        events: statuses.map((status, index) => ({
          id: `event-${index}`,
          sequence: index + 1,
          stepId: `step-${index}`,
          type: "workflow.step.started" as const,
          label: `步骤 ${index + 1}`,
          summary: index === 0 ? "" : `状态 ${status}`,
          status,
          timestamp: index === 0 ? undefined : `2026-08-03T01:00:0${index}.000Z`,
          toolLabel: index === 1 ? "诊断工具" : undefined
        }))
      }
    } satisfies AgentRunState

    const html = renderToStaticMarkup(
      createElement(AgentExecutionStatus, { run, startedAt })
    )

    for (const status of statuses) expect(html).toContain(`data-status="${status}"`)
    expect(html).toContain("--:--:--")
    expect(html).toContain("诊断工具")
  })

  it("renders stable and active Markdown blocks separately while streaming", () => {
    const streaming = renderToStaticMarkup(
      createElement(StreamMarkdownRenderer, {
        content: "第一段\n\n**正在生成",
        completed: false
      })
    )
    const completed = renderToStaticMarkup(
      createElement(StreamMarkdownRenderer, {
        content: "|设备|状态|\n|---|---|\n|A-03|正常|",
        completed: true
      })
    )

    expect(streaming).toContain("agent-markdown-active")
    expect(streaming).toContain("第一段")
    expect(completed).toContain("<table>")
    expect(completed).toContain("A-03")
  })

  it("renders the scheme-A workbench shell and complete composer", () => {
    const run = completedRun()
    useAgentWorkbenchStore.setState({
      messages: [
        {
          id: "user-1",
          role: "user",
          content: "分析 A-03 温度异常",
          displayedText: "分析 A-03 温度异常",
          createdAt: startedAt
        },
        {
          id: "assistant-1",
          role: "assistant",
          content: "",
          displayedText: "温度异常与散热效率下降有关。",
          createdAt: startedAt,
          run
        }
      ]
    })

    const html = renderToStaticMarkup(
      createElement(AgentStreamingWorkbench, {
        open: true,
        onClose: () => undefined,
        onLocate: () => undefined,
        stationId: "ess-station-01",
        range: "24h"
      })
    )

    expect(html).toContain("agent-streaming-workbench open")
    expect(html).toContain("RESPONSE STREAMING · 方案 A")
    expect(html).toContain('aria-label="打开工具"')
    expect(html).toContain('aria-label="语音输入"')
    expect(html).toContain("内容由 AI 生成")
  })

  it("keeps station quick prompts free of fabricated asset ids", () => {
    const html = renderToStaticMarkup(
      createElement(AgentStreamingWorkbench, {
        open: true,
        onClose: () => undefined,
        onLocate: () => undefined,
        stationId: "ess-station-01",
        range: "24h"
      })
    )

    for (const prompt of ["总结当前活动告警", "检索储能系统操作规程", "检查当前会话与场站上下文", "给出当前告警处置建议"]) {
      expect(html).toContain(prompt)
    }
    expect(html).not.toContain("pump-101")
  })

  it("renders a completed 10000-character Markdown response within 200ms", () => {
    const content = Array.from({ length: 400 }, (_, index) => `## 证据 ${index}\n\nA-01 温度 **${40 + (index % 20)}°C**。`).join("\n\n").slice(0, 10000)
    const startedAt = performance.now()
    const html = renderToStaticMarkup(
      createElement(StreamMarkdownRenderer, { content, completed: true })
    )
    const elapsedMs = performance.now() - startedAt

    expect(html).toContain("证据 0")
    expect(html).toContain("A-01")
    expect(elapsedMs).toBeLessThan(200)
  })
})

describe("Agent workbench store", () => {
  it("updates station, draft, messages and active run without replacing unrelated messages", () => {
    const store = useAgentWorkbenchStore.getState()
    store.setStation("station-b")
    useAgentWorkbenchStore.getState().setDraft("查询告警")
    useAgentWorkbenchStore.getState().appendMessages([
      {
        id: "user-store",
        role: "user",
        content: "查询告警",
        displayedText: "查询告警",
        createdAt: startedAt
      }
    ])
    useAgentWorkbenchStore.getState().updateMessage("user-store", { displayedText: "查询活动告警" })
    useAgentWorkbenchStore.getState().updateMessage("user-store", (message) => ({ ...message, content: "查询活动告警" }))
    useAgentWorkbenchStore.getState().setActiveMessageId("assistant-store")

    const state = useAgentWorkbenchStore.getState()
    expect(state.stationId).toBe("station-b")
    expect(state.draft).toBe("查询告警")
    expect(state.messages.at(-1)).toMatchObject({
      id: "user-store",
      content: "查询活动告警",
      displayedText: "查询活动告警"
    })
    expect(state.activeMessageId).toBe("assistant-store")
  })
})

function completedRun(): AgentRunState {
  return reduceAgentStreamEvents(
    createAgentRunState("run-ui", "session-ui", "message-ui"),
    [
      streamEvent(1, "tool.started", {
        label: "读取设备实时遥测",
        summary: "正在读取 A-03 温度与功率",
        status: "running",
        stepId: "tool:telemetry",
        toolLabel: "实时遥测"
      }),
      streamEvent(2, "tool.completed", {
        label: "读取设备实时遥测",
        summary: "温度与功率读取完成",
        status: "completed",
        stepId: "tool:telemetry",
        toolLabel: "实时遥测",
        durationMs: 1250
      }),
      streamEvent(3, "response.completed", {
        content: "温度异常与散热效率下降有关。"
      }),
      streamEvent(4, "run.completed", {
        status: "completed",
        completedAt: "2026-08-03T01:00:05.000Z"
      })
    ]
  )
}

function streamEvent(
  sequence: number,
  type: AgentStreamEvent["type"],
  payload: Record<string, unknown>
): AgentStreamEvent {
  return {
    eventId: `run-ui:${sequence}`,
    sequence,
    eventSequence: sequence,
    runId: "run-ui",
    conversationId: "session-ui",
    messageId: "message-ui",
    type,
    timestamp: `2026-08-03T01:00:0${sequence}.000Z`,
    payload
  }
}
