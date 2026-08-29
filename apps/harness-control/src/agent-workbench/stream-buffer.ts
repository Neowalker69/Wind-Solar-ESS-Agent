import type { AgentRunStatus } from "./contracts"

const TERMINAL_RUN_STATUSES = new Set<AgentRunStatus>([
  "completed",
  "cancelled",
  "error",
  "failed"
])

export function calculateDrainSize(backlogLength: number): number {
  if (backlogLength >= 600) return 64
  if (backlogLength >= 200) return 24
  return 8
}

export function shouldReleaseActiveMessage(
  status: AgentRunStatus,
  responseCompleted: boolean,
  pendingLength: number
): boolean {
  return responseCompleted && pendingLength === 0 && TERMINAL_RUN_STATUSES.has(status)
}

export function drainStreamingText(
  receivedText: string,
  displayedText: string,
  _responseCompleted = false
): { displayedText: string; pendingLength: number } {
  if (!receivedText.startsWith(displayedText)) {
    return { displayedText: receivedText, pendingLength: 0 }
  }
  const pendingLength = receivedText.length - displayedText.length
  const drainSize = calculateDrainSize(pendingLength)
  const nextLength = Math.min(receivedText.length, displayedText.length + drainSize)
  return {
    displayedText: receivedText.slice(0, nextLength),
    pendingLength: receivedText.length - nextLength
  }
}
