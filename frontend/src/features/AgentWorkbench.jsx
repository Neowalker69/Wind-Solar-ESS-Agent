import React, { useEffect, useRef, useState } from "react";
import { Bot, Check, ChevronDown, ChevronRight, CircleStop, Copy, ExternalLink, LocateFixed, Send, ShieldAlert, Sparkles, Wrench, X } from "lucide-react";
import { applyRunEventBatch, buildAgentRequest, createRunEventState } from "./digitalTwinAdapters";
import {
  approveAgentAction,
  cancelAgentRun,
  ensureAgentSession,
  loadAgentRun,
  resolveAgentToken,
  streamAgentRun,
  submitAgentMessage,
} from "./agentWorkflowClient.js";

const STATUS_TEXT = {
  planning: "正在规划",
  running: "正在执行",
  completed: "执行完成",
  failed: "执行失败",
  cancelled: "已停止",
};

function applySceneActions(events, onLocate) {
  for (const event of events) {
    if (event.type === "scene.action" && event.action?.command === "highlight_asset" && event.action.assetId) {
      onLocate(event.action.assetId);
    }
  }
}

function ObservationRow({ row }) {
  const [open, setOpen] = useState(false);
  const statusText = row.status === "success" ? "完成" : row.status === "error" ? "失败" : "执行中";
  return (
    <div className="agent-observation" style={{ "--observation-depth": Math.min(row.depth, 4) }} data-kind={row.kind} data-status={row.status}>
      <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span className="agent-observation-dot" />
        <span className="agent-observation-main"><b>{row.name}</b><small>{row.summary}</small></span>
        <span className="agent-observation-meta">{row.durationMs != null ? `${row.durationMs}ms · ` : ""}{statusText}</span>
      </button>
      {open && <div className="agent-observation-details">类型：{row.kind}{row.totalTokens != null ? ` · Token ${row.totalTokens}` : ""}</div>}
    </div>
  );
}

function AgentProcessPanel({ message }) {
  const [open, setOpen] = useState(message.status !== "completed");
  const rows = message.traceRows || [];
  const elapsed = message.elapsedMs != null ? `${(message.elapsedMs / 1000).toFixed(1)}s` : "--";
  return (
    <section className={`agent-process-panel ${message.status}`} aria-label="Agent 执行过程">
      <button className="agent-process-header" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="agent-process-state"><Sparkles size={14} />{STATUS_TEXT[message.status] || "Agent 执行过程"}</span>
        <span>{rows.length ? `${rows.length} 个步骤 · ${elapsed}` : elapsed}</span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="agent-process-content">
          <div className="agent-reasoning-summary">{message.reasoningSummary || "正在理解问题并组织可审计的执行步骤。"}</div>
          {rows.map((row) => <ObservationRow key={row.observationId} row={row} />)}
          {message.traceUrl && <a className="agent-trace-link" href={message.traceUrl} target="_blank" rel="noreferrer"><ExternalLink size={13} />在本地 Langfuse 查看完整 Trace</a>}
        </div>
      )}
    </section>
  );
}

function SuggestionCard({ container, onLocate, onConfirm }) {
  if (!container || container.severity === "normal") return null;
  return (
    <article className={`agent-suggestion ${container.severity}`}>
      <header><ShieldAlert size={15} /><b>建议优先处理 {container.id} 运行异常</b></header>
      <p>当前 SOC {container.soc}%、温度 {container.temp}℃。建议核对热管理与充放电策略，并保留现场确认环节。</p>
      <div><button type="button" onClick={() => onLocate(container.id)}><LocateFixed size={14} />定位设备</button><button type="button" className="primary" onClick={onConfirm}><Wrench size={14} />生成工单</button></div>
    </article>
  );
}

export function AgentWorkbench({ open, onClose, container, alerts, range, initialPrompt, onLocate, stationId = "ess-station-01" }) {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState(() => [{ id: "welcome", role: "assistant", content: "您好，我已载入当前场站上下文。选择设备后可以直接发起诊断。", createdAt: new Date().toISOString(), status: "completed" }]);
  const [generationState, setGenerationState] = useState("ready");
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [latestRunId, setLatestRunId] = useState(() => sessionStorage.getItem("digitalTwin.lastRunId") || "");
  const abortRef = useRef(null);
  const activeRunRef = useRef("");
  const messageListRef = useRef(null);
  const pendingEventsRef = useRef([]);
  const eventFlushRef = useRef(null);

  useEffect(() => {
    if (initialPrompt) setDraft(initialPrompt);
  }, [initialPrompt]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event) => {
      if (event.key !== "Escape") return;
      if (confirmOpen) setConfirmOpen(false);
      else onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [confirmOpen, onClose, open]);

  useEffect(() => {
    if (generationState === "ready") messageListRef.current?.scrollTo({ top: messageListRef.current.scrollHeight, behavior: "smooth" });
  }, [generationState, messages.length]);

  useEffect(() => {
    const runId = sessionStorage.getItem("digitalTwin.activeRunId");
    if (!runId) return undefined;
    const controller = new AbortController();
    const assistantId = `assistant_${runId}`;
    const resume = async () => {
      try {
        const token = await resolveAgentToken(controller.signal);
        const snapshot = await loadAgentRun(runId, token, controller.signal);
        let state = applyRunEventBatch(createRunEventState(runId), snapshot.events || []);
        applySceneActions(state.sceneActions.map((action) => ({ type: "scene.action", action })), onLocate);
        const updateMessage = () => {
          const langfuse = state.externalObservability?.langfuse;
          setMessages((items) => {
            const next = {
              id: assistantId,
              runId,
              role: "assistant",
              content: state.message?.content || "上次 Agent 运行已恢复。",
              createdAt: new Date().toISOString(),
              status: state.status,
              reasoningSummary: state.message?.reasoningSummary,
              traceRows: state.observations,
              traceUrl: langfuse?.trace_url,
            };
            return items.some((item) => item.runId === runId)
              ? items.map((item) => item.runId === runId ? { ...item, ...next } : item)
              : [...items, next];
          });
        };
        updateMessage();
        if (["completed", "failed", "cancelled"].includes(state.status)) {
          sessionStorage.removeItem("digitalTwin.activeRunId");
          return;
        }
        activeRunRef.current = runId;
        abortRef.current = controller;
        setGenerationState("sending");
        await streamAgentRun(runId, token, controller.signal, (events) => {
          state = applyRunEventBatch(state, events);
          updateMessage();
        }, fetch, state.lastEventId);
        sessionStorage.removeItem("digitalTwin.activeRunId");
      } catch (resumeError) {
        if (resumeError.name !== "AbortError") setError(`恢复 Agent 运行失败：${resumeError.message}`);
      } finally {
        activeRunRef.current = "";
        abortRef.current = null;
        setGenerationState("ready");
      }
    };
    resume();
    return () => controller.abort();
  }, [onLocate]);

  const runMessage = async (text) => {
    const input = text.trim();
    if (!input || generationState !== "ready") return;
    const userMessage = { id: `user_${Date.now()}`, role: "user", content: input, createdAt: new Date().toISOString(), status: "completed" };
    const assistantId = `assistant_pending_${Date.now()}`;
    let runState = null;
    setMessages((items) => [...items, userMessage, { id: assistantId, role: "assistant", content: "", createdAt: new Date().toISOString(), status: "queued", reasoningSummary: "请求已排队。" }]);
    setDraft("");
    setError("");
    setGenerationState("sending");
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = performance.now();
    const flushEvents = () => {
      eventFlushRef.current = null;
      const events = pendingEventsRef.current.splice(0);
      if (!events.length) return;
      if (!runState) return;
      runState = applyRunEventBatch(runState, events);
      const langfuse = runState.externalObservability?.langfuse;
      setMessages((items) => items.map((message) => message.id === assistantId ? {
        ...message,
        status: runState.status,
        content: runState.message?.content || message.content,
        reasoningSummary: runState.message?.reasoningSummary || events.find((event) => event.summary)?.summary || message.reasoningSummary,
        traceRows: runState.observations,
        elapsedMs: Math.round(performance.now() - startedAt),
        traceUrl: langfuse?.trace_url || message.traceUrl,
      } : message));
    };
    const queueEvents = (events) => {
      applySceneActions(events, onLocate);
      pendingEventsRef.current.push(...events);
      if (!eventFlushRef.current) eventFlushRef.current = window.setTimeout(flushEvents, 50);
    };
    try {
      const request = buildAgentRequest(input, { container, alerts, range, stationId });
      const token = await resolveAgentToken(controller.signal);
      const sessionId = await ensureAgentSession(request.context.site_id, token, controller.signal);
      const accepted = await submitAgentMessage(sessionId, request, token, controller.signal);
      const runId = accepted.runId;
      runState = createRunEventState(runId);
      activeRunRef.current = runId;
      setLatestRunId(runId);
      sessionStorage.setItem("digitalTwin.activeRunId", runId);
      sessionStorage.setItem("digitalTwin.lastRunId", runId);
      setMessages((items) => items.map((message) => message.id === assistantId ? { ...message, runId } : message));
      await streamAgentRun(runId, token, controller.signal, queueEvents);
      if (eventFlushRef.current) window.clearTimeout(eventFlushRef.current);
      flushEvents();
      sessionStorage.removeItem("digitalTwin.activeRunId");
    } catch (requestError) {
      const cancelled = requestError.name === "AbortError";
      if (eventFlushRef.current) window.clearTimeout(eventFlushRef.current);
      flushEvents();
      setMessages((items) => items.map((message) => message.id === assistantId ? { ...message, status: cancelled ? "cancelled" : "failed", content: cancelled ? "已停止生成，已完成的过程信息已保留。" : "本次分析未完成。", elapsedMs: Math.round(performance.now() - startedAt) } : message));
      if (!cancelled) setError(`${requestError.message}${requestError.traceId ? ` · Trace ${requestError.traceId}` : ""}`);
      if (!cancelled) sessionStorage.removeItem("digitalTwin.activeRunId");
    } finally {
      activeRunRef.current = "";
      abortRef.current = null;
      setGenerationState("ready");
    }
  };

  const stopRun = async () => {
    const runId = activeRunRef.current;
    abortRef.current?.abort();
    if (!runId) return;
    try {
      const token = await resolveAgentToken();
      await cancelAgentRun(runId, token);
    } catch (cancelError) {
      setError(cancelError.message);
    }
  };

  const quickPrompts = container ? ["分析当前告警", "查询最近遥测", "给出处置建议", "总结 24h 趋势"] : ["检查场站运行状态", "总结当前告警", "分析能量流向", "生成值班摘要"];
  return (
    <aside className={`agent-workbench ${open ? "open" : ""}`} aria-hidden={!open} aria-label="AI Agent 工作台">
      <header className="agent-workbench-header">
        <div className="agent-title-icon"><Bot size={18} /></div><div><b>AI Agent 工作台</b><small>INDUSTRIAL OPERATIONS COPILOT</small></div>
        <button type="button" onClick={onClose} aria-label="关闭 AI Agent 工作台"><X size={17} /></button>
      </header>
      <div className="agent-context-bar">
        <span className="agent-online"><i />在线</span><span>领域：储能系统</span><span>站点：示范电站</span>{container && <span>设备：{container.id}</span>}
      </div>
      <div className="agent-message-list" ref={messageListRef} aria-live="polite">
        {messages.map((message) => (
          <article key={message.id} className={`agent-message ${message.role}`}>
            <time>{new Date(message.createdAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time>
            <div className="agent-message-bubble">
              {message.role === "assistant" && message.status && message.id !== "welcome" && message.showProcess !== false && <AgentProcessPanel message={message} />}
              {message.content && <p>{message.content}</p>}
              {message.role === "assistant" && message.status === "completed" && <button className="agent-copy" type="button" aria-label="复制消息" onClick={() => navigator.clipboard?.writeText(message.content)}><Copy size={12} /></button>}
            </div>
          </article>
        ))}
        <SuggestionCard container={container} onLocate={onLocate} onConfirm={() => setConfirmOpen(true)} />
      </div>
      <div className="agent-quick-prompts">{quickPrompts.map((prompt) => <button type="button" key={prompt} onClick={() => setDraft(prompt)}>{prompt}</button>)}</div>
      <form className="agent-composer" onSubmit={(event) => { event.preventDefault(); runMessage(draft); }}>
        {error && <div className="agent-error"><span>{error}</span><button type="button" onClick={() => setError("")} aria-label="关闭错误提示"><X size={13} /></button></div>}
        <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="向 Agent 提问" rows={1} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); runMessage(draft); } }} />
        {generationState === "ready" ? <button className="agent-send" type="submit" disabled={!draft.trim()} aria-label="发送消息"><Send size={18} /></button> : <button className="agent-send stop" type="button" onClick={stopRun} aria-label="停止生成"><CircleStop size={18} /></button>}
      </form>
      {confirmOpen && <div className="agent-confirm-backdrop" role="presentation"><section className="agent-confirm" role="dialog" aria-modal="true" aria-label="确认生成工单"><ShieldAlert size={24} /><h3>确认生成处置工单</h3><p>对象：{container?.id}<br />影响：仅创建待审核工单，不执行设备控制。<br />权限：运维工程师 · 全程记录审计 ID</p><div><button type="button" onClick={() => setConfirmOpen(false)}>取消</button><button type="button" className="primary" onClick={async () => { const target = container; if (!target || !latestRunId) { setError("请先完成一次 Agent 分析再生成工单"); return; } setConfirmOpen(false); setError(""); try { const token = await resolveAgentToken(); const receipt = await approveAgentAction(latestRunId, target, token); setMessages((items) => [...items, { id: receipt.audit_id, role: "assistant", content: `已创建 ${target.id} 待审核工单草稿。审计 ID：${receipt.audit_id}，操作未下发设备。`, createdAt: new Date().toISOString(), status: "completed", showProcess: false }]); } catch (actionError) { setError(actionError.message); } }}><Check size={14} />确认创建</button></div></section></div>}
    </aside>
  );
}
