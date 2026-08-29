import { describe, expect, it } from "@jest/globals"

import {
  calculateDrainSize,
  drainStreamingText,
  shouldReleaseActiveMessage
} from "../src/agent-workbench/stream-buffer"

describe("Agent visual streaming buffer", () => {
  it("adapts drain size to backlog", () => {
    expect(calculateDrainSize(80)).toBe(8)
    expect(calculateDrainSize(300)).toBe(24)
    expect(calculateDrainSize(900)).toBe(64)
  })

  it("drains received text without duplicating displayed content", () => {
    const first = drainStreamingText("当前储能系统运行正常", "")
    const second = drainStreamingText("当前储能系统运行正常", first.displayedText)

    expect(first.displayedText).toBe("当前储能系统运行正常".slice(0, 8))
    expect(second.displayedText).toBe("当前储能系统运行正常")
    expect(second.pendingLength).toBe(0)
  })

  it("keeps draining queued text incrementally after response completion", () => {
    const content = "这是一个需要继续逐步展示的完整回答"
    const state = drainStreamingText(content, "", true)

    expect(state.displayedText).toBe(content.slice(0, 8))
    expect(state.pendingLength).toBe(content.length - 8)
  })

  it("keeps the active message until the run reaches a terminal state", () => {
    expect(shouldReleaseActiveMessage("streaming", true, 0)).toBe(false)
  })

  it("releases the active message after the completed run text is drained", () => {
    expect(shouldReleaseActiveMessage("completed", true, 0)).toBe(true)
  })

  it("replaces display text when the canonical response no longer shares its prefix", () => {
    const state = drainStreamingText("权威最终回答", "旧的局部回答")

    expect(state).toEqual({ displayedText: "权威最终回答", pendingLength: 0 })
  })

  it("drains a 10000-character response within the 150ms completion budget", () => {
    const content = "储能设备状态与权威证据。".repeat(1000).slice(0, 10000)
    let displayed = ""
    const startedAt = performance.now()
    while (displayed.length < content.length) {
      displayed = drainStreamingText(content, displayed).displayedText
    }
    const completed = drainStreamingText(content, displayed, true)
    const elapsedMs = performance.now() - startedAt

    expect(completed.displayedText).toBe(content)
    expect(completed.pendingLength).toBe(0)
    expect(elapsedMs).toBeLessThan(150)
  })
})
