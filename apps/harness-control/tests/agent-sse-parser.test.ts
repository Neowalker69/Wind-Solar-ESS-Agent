import { describe, expect, it } from "@jest/globals"

import { AgentSseParser } from "../src/agent-workbench/sse-parser"

describe("Agent SSE parser", () => {
  it("preserves incomplete frames across network chunks", () => {
    const parser = new AgentSseParser()

    expect(parser.push(new TextEncoder().encode("id: 1\nevent: response.delta\ndata: {\"sequence\":1,"))).toEqual([])
    const events = parser.push(new TextEncoder().encode("\"type\":\"response.delta\",\"payload\":{\"delta\":\"当前\"}}\n\n"))

    expect(events).toHaveLength(1)
    expect(events[0].payload).toEqual({ delta: "当前" })
  })

  it("decodes a Chinese character split between UTF-8 chunks", () => {
    const parser = new AgentSseParser()
    const bytes = new TextEncoder().encode(
      "data: {\"sequence\":1,\"type\":\"response.delta\",\"payload\":{\"delta\":\"储\"}}\n\n"
    )
    const splitAt = bytes.indexOf(0xe5) + 1

    expect(parser.push(bytes.slice(0, splitAt))).toEqual([])
    const events = parser.push(bytes.slice(splitAt))

    expect(events[0].payload).toEqual({ delta: "储" })
  })

  it("keeps SSE frames separate when CRLF is split between network chunks", () => {
    const parser = new AgentSseParser()
    const encoder = new TextEncoder()

    expect(parser.push(encoder.encode(
      'data: {"sequence":1,"type":"response.delta","payload":{"delta":"A"}}\r\n\r'
    ))).toEqual([])
    const events = parser.push(encoder.encode(
      '\ndata: {"sequence":2,"type":"run.completed","payload":{}}\r\n\r\n'
    ))

    expect(events).toMatchObject([
      { sequence: 1, type: "response.delta" },
      { sequence: 2, type: "run.completed" }
    ])
  })

  it("ignores heartbeat comments without producing visible events", () => {
    const parser = new AgentSseParser()

    expect(parser.push(new TextEncoder().encode(": keep-alive\n\n"))).toEqual([])
  })

  it("flushes a valid final frame without a trailing separator", () => {
    const parser = new AgentSseParser()
    parser.push(new TextEncoder().encode(
      "event: run.completed\r\ndata: {\"sequence\":1,\"type\":\"run.completed\",\"payload\":{}}"
    ))

    expect(parser.finish()).toMatchObject([
      { sequence: 1, type: "run.completed", payload: {} }
    ])
    expect(parser.finish()).toEqual([])
  })

  it("drops non-data and malformed JSON frames", () => {
    const parser = new AgentSseParser()

    expect(parser.push(new TextEncoder().encode("event: heartbeat\n\n"))).toEqual([])
    expect(parser.push(new TextEncoder().encode("data: {invalid}\n\n"))).toEqual([])
  })
})
