import type { AgentStreamEvent } from "./contracts"

export class AgentSseParser {
  private readonly decoder = new TextDecoder()
  private buffer = ""

  push(chunk: Uint8Array): AgentStreamEvent[] {
    this.buffer += this.decoder.decode(chunk, { stream: true })
    // 保留块尾的 CR，等下一块到达后再判断它属于 CRLF 还是独立换行。
    this.buffer = this.buffer.replace(/\r\n/g, "\n").replace(/\r(?!$)/g, "\n")
    const frames = this.buffer.split("\n\n")
    this.buffer = frames.pop() ?? ""
    return frames.flatMap((frame) => this.parseFrame(frame))
  }

  finish(): AgentStreamEvent[] {
    this.buffer += this.decoder.decode()
    this.buffer = this.buffer.replace(/\r\n?/g, "\n")
    if (!this.buffer.trim()) return []
    const frame = this.buffer
    this.buffer = ""
    return this.parseFrame(frame)
  }

  private parseFrame(frame: string): AgentStreamEvent[] {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n")
    if (!data) return []
    try {
      return [JSON.parse(data) as AgentStreamEvent]
    } catch {
      return []
    }
  }
}
