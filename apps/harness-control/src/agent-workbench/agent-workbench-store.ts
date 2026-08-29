import { create } from "zustand"

import type { AgentRunState } from "./contracts"

export interface AgentWorkbenchMessage {
  id: string
  role: "assistant" | "user"
  content: string
  displayedText: string
  createdAt: string
  run?: AgentRunState
  elapsedMs?: number
}

interface AgentWorkbenchStore {
  stationId: string
  draft: string
  messages: AgentWorkbenchMessage[]
  activeMessageId: string
  setStation: (stationId: string) => void
  setDraft: (draft: string) => void
  appendMessages: (messages: AgentWorkbenchMessage[]) => void
  updateMessage: (
    messageId: string,
    update: Partial<AgentWorkbenchMessage> | ((message: AgentWorkbenchMessage) => AgentWorkbenchMessage)
  ) => void
  setActiveMessageId: (messageId: string) => void
}

function welcomeMessage(): AgentWorkbenchMessage {
  return {
    id: "welcome",
    role: "assistant",
    content: "您好，我已载入当前场站上下文。请选择设备或直接发起运行分析。",
    displayedText: "您好，我已载入当前场站上下文。请选择设备或直接发起运行分析。",
    createdAt: new Date().toISOString()
  }
}

export const useAgentWorkbenchStore = create<AgentWorkbenchStore>((set) => ({
  stationId: "",
  draft: "",
  messages: [welcomeMessage()],
  activeMessageId: "",
  setStation: (stationId) =>
    set((state) =>
      state.stationId === stationId
        ? state
        : { stationId, messages: [welcomeMessage()], activeMessageId: "", draft: "" }
    ),
  setDraft: (draft) => set({ draft }),
  appendMessages: (messages) => set((state) => ({ messages: [...state.messages, ...messages] })),
  updateMessage: (messageId, update) =>
    set((state) => ({
      messages: state.messages.map((message) => {
        if (message.id !== messageId) return message
        return typeof update === "function" ? update(message) : { ...message, ...update }
      })
    })),
  setActiveMessageId: (activeMessageId) => set({ activeMessageId })
}))
