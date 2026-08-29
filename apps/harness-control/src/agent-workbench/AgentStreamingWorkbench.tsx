"use client"

import {
  Bot,
  CheckCheck,
  ChevronDown,
  CircleStop,
  Copy,
  Mic,
  Send,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  UserRound,
  Wrench,
  X
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import {
  clearAgentSession,
  ensureAgentSession,
  isStaleSessionError,
  loadAgentRun,
  resolveAgentToken,
  streamAgentRun,
  submitAgentTurn
} from "./agent-stream-client"
import { useAgentWorkbenchStore } from "./agent-workbench-store"
import { AgentExecutionStatus } from "./components/AgentExecutionStatus"
import { StreamMarkdownRenderer } from "./components/StreamMarkdownRenderer"
import type { AgentStreamEvent } from "./contracts"
import { createAgentRunState, reduceAgentStreamEvents } from "./stream-reducer"
import { drainStreamingText, shouldReleaseActiveMessage } from "./stream-buffer"

interface DeviceContext {
  id?: string
  stationDeviceId?: string
  soc?: number
  soh?: number
  power?: number
  temp?: number
  severity?: string
  updatedAt?: string
}

interface AlertContext {
  id?: string
  title?: string
  deviceId?: string
  stationDeviceId?: string
}

export interface AgentStreamingWorkbenchProps {
  open: boolean
  onClose: () => void
  container?: DeviceContext | null
  alerts?: AlertContext[]
  range?: string
  initialPrompt?: string
  onLocate: (assetId: string) => void
  stationId?: string
}

export function AgentStreamingWorkbench({
  open,
  onClose,
  container,
  alerts = [],
  range = "24h",
  initialPrompt = "",
  onLocate,
  stationId = "ess-station-01"
}: AgentStreamingWorkbenchProps) {
  const draft = useAgentWorkbenchStore((state) => state.draft)
  const setDraft = useAgentWorkbenchStore((state) => state.setDraft)
  const messageCount = useAgentWorkbenchStore((state) => state.messages.length)
  const activeMessageId = useAgentWorkbenchStore((state) => state.activeMessageId)
  const appendMessages = useAgentWorkbenchStore((state) => state.appendMessages)
  const updateMessage = useAgentWorkbenchStore((state) => state.updateMessage)
  const setActiveMessageId = useAgentWorkbenchStore((state) => state.setActiveMessageId)
  const setStation = useAgentWorkbenchStore((state) => state.setStation)
  const [error, setError] = useState("")
  const [followMode, setFollowMode] = useState(true)
  const [newContent, setNewContent] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const workbenchRef = useRef<HTMLElement>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const activeRunIdRef = useRef("")
  const pendingEventsRef = useRef<AgentStreamEvent[]>([])
  const eventFlushRef = useRef<number | null>(null)
  const resumeStationRef = useRef("")

  const messageIds = useMemo(
    () => useAgentWorkbenchStore.getState().messages.map((message) => message.id),
    [messageCount]
  )

  useEffect(() => setStation(stationId), [setStation, stationId])
  useEffect(() => {
    if (initialPrompt) setDraft(initialPrompt)
  }, [initialPrompt, setDraft])

  const closeWorkbench = useCallback(() => {
    const activeElement = document.activeElement
    if (
      activeElement instanceof HTMLElement
      && workbenchRef.current?.contains(activeElement)
    ) {
      activeElement.blur()
    }
    onClose()
  }, [onClose])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeWorkbench()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [closeWorkbench, open])

  useEffect(() => () => controllerRef.current?.abort(), [])

  useEffect(() => {
    if (!activeMessageId) return
    const timer = window.setInterval(() => {
      let drained = false
      updateMessage(activeMessageId, (message) => {
        if (!message.run) return message
        const result = drainStreamingText(
          message.run.receivedText,
          message.displayedText,
          message.run.responseCompleted
        )
        drained = shouldReleaseActiveMessage(
          message.run.status,
          message.run.responseCompleted,
          result.pendingLength
        )
        if (result.displayedText === message.displayedText) return message
        return { ...message, displayedText: result.displayedText }
      })
      if (drained) setActiveMessageId("")
    }, 40)
    return () => window.clearInterval(timer)
  }, [activeMessageId, setActiveMessageId, updateMessage])

  const revealLatest = useCallback(() => {
    const list = listRef.current
    if (!list) return
    if (followMode) {
      list.scrollTo({ top: list.scrollHeight, behavior: "smooth" })
    } else {
      setNewContent(true)
    }
  }, [followMode])

  const scrollToLatest = () => {
    const list = listRef.current
    if (!list) return
    setFollowMode(true)
    setNewContent(false)
    list.scrollTo({ top: list.scrollHeight, behavior: "smooth" })
  }

  const flushEvents = useCallback(() => {
    eventFlushRef.current = null
    const events = pendingEventsRef.current.splice(0)
    if (!events.length) return
    const messageId = useAgentWorkbenchStore.getState().activeMessageId
    if (!messageId) return
    for (const event of events) {
      if (event.type === "scene.action" && event.action?.command === "highlight_asset" && event.action.assetId) {
        onLocate(event.action.assetId)
      }
    }
    updateMessage(messageId, (message) => {
      if (!message.run) return message
      return { ...message, run: reduceAgentStreamEvents(message.run, events) }
    })
  }, [onLocate, updateMessage])

  const queueEvents = useCallback(
    (events: AgentStreamEvent[]) => {
      pendingEventsRef.current.push(...events)
      if (eventFlushRef.current === null) {
        eventFlushRef.current = window.setTimeout(flushEvents, 40)
      }
    },
    [flushEvents]
  )

  useEffect(() => {
    if (resumeStationRef.current === stationId) return
    resumeStationRef.current = stationId
    const runId = sessionStorage.getItem(activeRunKey(stationId))
    if (!runId) return
    const controller = new AbortController()
    controllerRef.current = controller

    const resume = async () => {
      try {
        const token = await resolveAgentToken(controller.signal)
        const sessionId = await ensureAgentSession(stationId, token, controller.signal)
        const snapshot = await loadAgentRun(runId, sessionId, token, controller.signal)
        const assistantId = `assistant_recovered_${runId}`
        const run = reduceAgentStreamEvents(
          createAgentRunState(runId, snapshot.sessionId, snapshot.clientMessageId),
          snapshot.events
        )
        if (!useAgentWorkbenchStore.getState().messages.some((message) => message.id === assistantId)) {
          appendMessages([
            {
              id: assistantId,
              role: "assistant",
              content: "",
              displayedText: "",
              createdAt: new Date().toISOString(),
              run
            }
          ])
        }
        setActiveMessageId(assistantId)
        if (["completed", "cancelled", "failed", "error"].includes(run.status)) {
          sessionStorage.removeItem(activeRunKey(stationId))
          return
        }
        activeRunIdRef.current = runId
        await streamAgentRun({
          runId,
          sessionId,
          token,
          signal: controller.signal,
          afterSequence: run.lastSequence,
          onEvents: queueEvents,
          onConnectionState: (state) => {
            if (state !== "reconnecting") return
            updateMessage(assistantId, (message) =>
              message.run
                ? { ...message, run: { ...message.run, status: "reconnecting" } }
                : message
            )
          }
        })
        if (eventFlushRef.current !== null) window.clearTimeout(eventFlushRef.current)
        flushEvents()
        sessionStorage.removeItem(activeRunKey(stationId))
      } catch (resumeError) {
        if (!(resumeError instanceof DOMException && resumeError.name === "AbortError")) {
          setError(`恢复 Agent 运行失败：${errorMessage(resumeError)}`)
        }
      } finally {
        activeRunIdRef.current = ""
        controllerRef.current = null
      }
    }
    void resume()
  }, [appendMessages, flushEvents, queueEvents, setActiveMessageId, stationId, updateMessage])

  const runMessage = async (rawInput: string) => {
    const input = rawInput.trim()
    if (!input || activeMessageId) return
    const request = buildAgentRequest(input, stationId, container, alerts, range)
    const clientMessageId = globalThis.crypto?.randomUUID?.() ?? `msg_${Date.now()}`
    const now = new Date().toISOString()
    const assistantId = `assistant_${clientMessageId}`
    appendMessages([
      {
        id: `user_${clientMessageId}`,
        role: "user",
        content: input,
        displayedText: input,
        createdAt: now
      },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        displayedText: "",
        createdAt: now
      }
    ])
    setActiveMessageId(assistantId)
    setDraft("")
    setError("")
    const controller = new AbortController()
    controllerRef.current = controller

    try {
      const token = await resolveAgentToken(controller.signal)
      const accepted = await submitWithStaleSessionRecovery(
        stationId,
        request,
        token,
        controller.signal
      )
      activeRunIdRef.current = accepted.runId
      sessionStorage.setItem(activeRunKey(stationId), accepted.runId)
      const run = createAgentRunState(accepted.runId, accepted.sessionId, accepted.messageId)
      updateMessage(assistantId, { run })
      await streamAgentRun({
        runId: accepted.runId,
        streamUrl: accepted.streamUrl,
        sessionId: accepted.sessionId,
        token,
        signal: controller.signal,
        onEvents: queueEvents,
        onConnectionState: (connectionState) => {
          updateMessage(assistantId, (message) => {
            if (!message.run || ["completed", "cancelled", "failed", "error"].includes(message.run.status)) return message
            const status = connectionState === "reconnecting" ? "reconnecting" : message.run.status
            return { ...message, run: { ...message.run, status } }
          })
        }
      })
      if (eventFlushRef.current !== null) window.clearTimeout(eventFlushRef.current)
      flushEvents()
      sessionStorage.removeItem(activeRunKey(stationId))
    } catch (requestError) {
      if (eventFlushRef.current !== null) window.clearTimeout(eventFlushRef.current)
      flushEvents()
      const cancelled = requestError instanceof DOMException && requestError.name === "AbortError"
      updateMessage(assistantId, (message) => ({
        ...message,
        displayedText: message.displayedText,
        run: message.run
          ? {
              ...message.run,
              status: cancelled ? "cancelled" : "error",
              responseCompleted: true,
              receivedText:
                message.run.receivedText || (cancelled ? "已停止生成。" : "本次分析未完成。"),
              errorMessage: cancelled ? "" : errorMessage(requestError)
            }
          : undefined
      }))
      if (!useAgentWorkbenchStore.getState().messages.find((message) => message.id === assistantId)?.run) {
        updateMessage(assistantId, {
          displayedText: cancelled ? "已停止生成。" : "本次分析未完成。"
        })
        setActiveMessageId("")
      }
      if (!cancelled) setError(errorMessage(requestError))
      sessionStorage.removeItem(activeRunKey(stationId))
    } finally {
      activeRunIdRef.current = ""
      controllerRef.current = null
    }
  }

  const stopRun = async () => {
    const runId = activeRunIdRef.current
    const messageId = useAgentWorkbenchStore.getState().activeMessageId
    const completedAt = new Date().toISOString()
    controllerRef.current?.abort()
    if (messageId) {
      updateMessage(messageId, (message) => ({
        ...message,
        displayedText: message.run?.receivedText || message.displayedText,
        run: message.run
          ? {
              ...message.run,
              status: "cancelled",
              responseCompleted: true,
              completedAt
            }
          : message.run
      }))
      setActiveMessageId("")
    }
    if (runId) sessionStorage.removeItem(activeRunKey(stationId))
  }

  const quickPrompts = container?.id
    ? ["分析当前告警", "查询最近实时遥测", "总结设备运行状态", "给出处置建议"]
    : ["总结当前活动告警", "检索储能系统操作规程", "检查当前会话与场站上下文", "给出当前告警处置建议"]

  return (
    <aside ref={workbenchRef} className={`agent-workbench agent-streaming-workbench ${open ? "open" : ""}`} inert={!open} aria-label="AI Agent 工作台">
      <header className="agent-workbench-header">
        <div className="agent-title-icon"><Bot size={18} /></div>
        <div><b>AI Agent 工作台</b><small>RESPONSE STREAMING · 方案 A</small></div>
        <button type="button" onClick={closeWorkbench} aria-label="关闭 AI Agent 工作台"><X size={17} /></button>
      </header>
      <div className="agent-context-bar">
        <strong>智能运维助手</strong>
        <span className="agent-online"><i />在线</span>
        <span>场站：{stationId}</span>
        <span>数据时效：近{range}</span>
        {container?.id && <span>设备：{container.id}</span>}
      </div>
      <div
        className="agent-message-list"
        ref={listRef}
        aria-live="polite"
        onScroll={(event) => {
          const target = event.currentTarget
          const following = target.scrollHeight - target.scrollTop - target.clientHeight <= 80
          setFollowMode(following)
          if (following) setNewContent(false)
        }}
      >
        {messageIds.map((messageId) => (
          <StreamingMessage key={messageId} messageId={messageId} onContent={revealLatest} />
        ))}
      </div>
      {newContent && (
        <button className="agent-new-content" type="button" onClick={scrollToLatest}>
          <ChevronDown size={13} />有新内容
        </button>
      )}
      <div className="agent-quick-prompts">
        {quickPrompts.map((prompt) => <button type="button" key={prompt} onClick={() => setDraft(prompt)}>{prompt}</button>)}
      </div>
      <form className="agent-composer" onSubmit={(event) => { event.preventDefault(); void runMessage(draft) }}>
        {error && <div className="agent-error"><span>{error}</span><button type="button" onClick={() => setError("")}><X size={13} /></button></div>}
        <div className="agent-composer-shell">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="请输入问题或对 Agent 下达指令…"
            rows={1}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                void runMessage(draft)
              }
            }}
          />
          <div className="agent-composer-toolbar">
            <button className="agent-composer-tool" type="button" aria-label="打开工具">
              <Wrench size={14} /><span>工具</span><ChevronDown size={12} />
            </button>
            <div className="agent-composer-actions">
              <button className="agent-composer-mic" type="button" aria-label="语音输入"><Mic size={17} /></button>
              {activeMessageId
                ? <button className="agent-send stop" type="button" onClick={() => void stopRun()} aria-label="停止生成"><CircleStop size={18} /></button>
                : <button className="agent-send" type="submit" disabled={!draft.trim()} aria-label="发送消息"><Send size={18} /></button>}
            </div>
          </div>
        </div>
      </form>
      <footer className="agent-workbench-footer"><ShieldCheck size={12} />内容由 AI 生成，请结合实际情况分析使用</footer>
    </aside>
  )
}

function StreamingMessage({ messageId, onContent }: { messageId: string; onContent: () => void }) {
  const message = useAgentWorkbenchStore((state) => state.messages.find((item) => item.id === messageId))
  const [feedback, setFeedback] = useState<"up" | "down" | "">("")
  useEffect(() => onContent(), [message?.displayedText, message?.run?.execution.events.length, onContent])
  if (!message) return null
  const time = new Date(message.createdAt).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  })
  if (message.role === "user") {
    return (
      <article className="agent-message user">
        <div className="agent-message-body">
          <div className="agent-message-bubble">{message.displayedText}</div>
          <footer className="agent-message-meta"><time>{time}</time><CheckCheck size={13} aria-label="已发送" /></footer>
        </div>
        <span className="agent-message-avatar user" aria-hidden="true"><UserRound size={17} /></span>
      </article>
    )
  }
  return (
    <article className="agent-turn">
      {message.id !== "welcome" && (
        <AgentExecutionStatus run={message.run} startedAt={message.createdAt} />
      )}
      <div className="agent-message assistant">
        <span className="agent-message-avatar assistant" aria-hidden="true"><Bot size={17} /></span>
        <div className="agent-message-body">
          <div className="agent-message-bubble agent-answer-card">
            {message.displayedText && (
              <StreamMarkdownRenderer
                content={message.displayedText}
                completed={message.run?.responseCompleted ?? true}
              />
            )}
            {!message.displayedText && <span className="agent-streaming-cursor" aria-label="正在等待回答" />}
          </div>
          <footer className="agent-message-meta">
            <time>{time}</time>
            {message.run?.status === "completed" && (
              <div className="agent-message-actions">
                <button type="button" aria-label="复制消息" onClick={() => navigator.clipboard?.writeText(message.displayedText)}><Copy size={13} /></button>
                <button className={feedback === "up" ? "active" : ""} type="button" aria-label="回答有帮助" onClick={() => setFeedback(feedback === "up" ? "" : "up")}><ThumbsUp size={13} /></button>
                <button className={feedback === "down" ? "active" : ""} type="button" aria-label="回答需改进" onClick={() => setFeedback(feedback === "down" ? "" : "down")}><ThumbsDown size={13} /></button>
              </div>
            )}
          </footer>
        </div>
      </div>
    </article>
  )
}

async function submitWithStaleSessionRecovery(
  stationId: string,
  request: Record<string, unknown>,
  token: string,
  signal: AbortSignal
) {
  let sessionId = await ensureAgentSession(stationId, token, signal)
  try {
    return await submitAgentTurn(sessionId, request, token, signal)
  } catch (error) {
    if (!isStaleSessionError(error)) throw error
    clearAgentSession(stationId)
    sessionId = await ensureAgentSession(stationId, token, signal)
    return submitAgentTurn(sessionId, request, token, signal)
  }
}

interface AgentRequestPayload extends Record<string, unknown> {
  text: string
  context: Record<string, unknown>
  tool_refs: Array<{ tool_id: string; version: string }>
  skill_refs: Array<{ skill_id: string; version: string }>
  policy: { visible_tool_ids: string[]; workflow_stage: string }
  approval: { status: string }
}

export function buildAgentRequest(
  input: string,
  stationId: string,
  container: DeviceContext | null | undefined,
  alerts: AlertContext[],
  range: string
): AgentRequestPayload {
  const assetScope = resolveAssetQueryScope(input, container)
  const explicitAssetScope = assetScope.explicit
  const deviceId = assetScope.selected ? container?.stationDeviceId ?? container?.id : undefined
  const toolIds = explicitAssetScope ? CONTROL_AGENT_TOOL_IDS : CONTROL_BROAD_QUERY_TOOL_IDS
  const toolRefs = toolIds.map((toolId) => ({
    tool_id: toolId,
    version: "0.1.0"
  }))
  return {
    text: input,
    context: {
      ...(deviceId ? { selected_asset_id: deviceId } : {}),
      environment: "dev",
      attributes: {
        trusted_site_id: stationId,
        time_range: range,
        selected_alarm_count: String(alerts.length),
        selected_device_updated_at: container?.updatedAt ?? ""
      }
    },
    tool_refs: toolRefs,
    skill_refs: [],
    policy: {
      visible_tool_ids: toolIds,
      workflow_stage: "data.query"
    },
    approval: { status: "not_required" }
  }
}

function resolveAssetQueryScope(
  input: string,
  container: DeviceContext | null | undefined
): { explicit: boolean; selected: boolean } {
  const normalized = input.toLocaleLowerCase()
  const references = [container?.id, container?.stationDeviceId].filter(Boolean) as string[]
  const queryAssets = extractAssetReferences(input)
  const selectedAssets = new Set(references.flatMap(extractAssetReferences))
  const selectedMentioned = references.some((reference) => normalized.includes(reference.toLocaleLowerCase()))
    || queryAssets.some((asset) => selectedAssets.has(asset))
  const broad = queryAssets.length === 0 && isBroadAssetQuery(input)
  const selected = selectedMentioned
    || Boolean(container && queryAssets.length === 0 && !broad)
  return { explicit: selected || queryAssets.length > 0, selected }
}

function isBroadAssetQuery(input: string): boolean {
  const normalized = input.toLocaleLowerCase()
  return [
    "总体", "整体", "全场", "全站", "整个场站", "所有设备", "全部设备",
    "设备清单", "系统概况", "overall", "all devices", "all assets", "site-wide"
  ].some((marker) => normalized.includes(marker))
}

function extractAssetReferences(value: string): string[] {
  const references = new Set<string>()
  for (const match of value.matchAll(/(^|[^A-Za-z0-9])(A[-_ ]?0?(?:[1-9]|[12]\d|3[0-2])|(?:PCS|PACK|CELL|STK|CLU)[-_ ]?\d+)(?![A-Za-z0-9])/gi)) {
    const compact = match[2].replace(/[-_ ]/g, "").toLocaleUpperCase()
    if (compact.startsWith("A")) {
      references.add(`A-${Number(compact.slice(1)).toString().padStart(2, "0")}`)
      continue
    }
    const prefix = ["PACK", "CELL", "PCS", "STK", "CLU"].find((candidate) => compact.startsWith(candidate))
    if (prefix) references.add(`${prefix}_${Number(compact.slice(prefix.length)).toString().padStart(2, "0")}`)
  }
  for (const match of value.matchAll(/(^|[^\d])([1-9]|[12]\d|3[0-2])\s*号\s*(?:储能)?(?:集装箱|舱|设备)/g)) {
    references.add(`A-${Number(match[2]).toString().padStart(2, "0")}`)
  }
  return [...references]
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Agent 请求失败"
}

function activeRunKey(stationId: string): string {
  return `digitalTwin.activeRunId:${stationId}`
}

const CONTROL_AGENT_TOOL_IDS = [
  "asset.get_asset",
  "asset.list_assets",
  "asset.get_asset_status",
  "telemetry.get_latest_value",
  "telemetry.get_timeseries",
  "alarm.get_active_alarms",
  "alarm.get_alarm_detail",
  "alarm.get_alarm_history",
  "alarm.get_event_timeline",
  "runtime_context.get_session_context",
  "runtime_context.get_selected_asset_context",
  "runtime_context.get_environment_context",
  "search.search_sop"
]

const CONTROL_BROAD_QUERY_TOOL_IDS = [
  "asset.list_assets",
  "alarm.get_active_alarms",
  "alarm.get_alarm_history",
  "alarm.get_event_timeline",
  "runtime_context.get_session_context",
  "runtime_context.get_selected_asset_context",
  "runtime_context.get_environment_context",
  "search.search_sop"
]
