import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "@jest/globals"

import {
  executionStatusCopy,
  formatExecutionDuration
} from "../src/agent-workbench/components/AgentExecutionStatus"

const workbenchSource = readFileSync(
  path.resolve(process.cwd(), "src/agent-workbench/AgentStreamingWorkbench.tsx"),
  "utf8"
)
const workbenchCss = readFileSync(
  path.resolve(process.cwd(), "src/agent-workbench/agent-streaming-workbench.css"),
  "utf8"
)
const executionStatusSource = readFileSync(
  path.resolve(process.cwd(), "src/agent-workbench/components/AgentExecutionStatus.tsx"),
  "utf8"
)

describe("Response Streaming 方案 A UI 契约", () => {
  it("uses the PRD fixed elapsed format and terminal copy", () => {
    expect(formatExecutionDuration(0)).toBe("00m 00s")
    expect(formatExecutionDuration(342_000)).toBe("05m 42s")
    expect(executionStatusCopy("completed").title).toBe("已完成思考和执行")
    expect(executionStatusCopy("cancelled").title).toBe("已停止思考和执行")
    expect(executionStatusCopy("error").title).toBe("思考和执行未完成")
  })

  it("renders separate turn, execution-card, answer-card and avatar layers", () => {
    expect(workbenchSource).toContain('className="agent-turn"')
    expect(executionStatusSource).toContain("agent-execution-card")
    expect(workbenchSource).toContain("agent-message-avatar")
    expect(workbenchSource).toContain("agent-answer-card")
    expect(workbenchSource).toContain("agent-message-actions")
  })

  it("provides the required tool, microphone and send-stop composer controls", () => {
    expect(workbenchSource).toContain('aria-label="打开工具"')
    expect(workbenchSource).toContain('aria-label="语音输入"')
    expect(workbenchSource).toContain('aria-label="发送消息"')
    expect(workbenchSource).toContain('aria-label="停止生成"')
  })

  it("keeps every received response character visible when stop aborts the paint timer", () => {
    expect(workbenchSource).toContain(
      "displayedText: message.run?.receivedText || message.displayedText"
    )
  })

  it("defines the dark-blue design tokens, progress line and restrained motion", () => {
    for (const token of [
      "--agent-bg-page",
      "--agent-bg-panel",
      "--agent-bg-card",
      "--agent-border-default",
      "--agent-blue-500",
      "--agent-green-400",
      "--agent-text-primary"
    ]) {
      expect(workbenchCss).toContain(token)
    }
    expect(workbenchCss).toContain(".agent-execution-progress")
    expect(workbenchCss).toContain("@keyframes execution-event-enter")
    expect(workbenchCss).toContain("@media (prefers-reduced-motion: reduce)")
  })
})
