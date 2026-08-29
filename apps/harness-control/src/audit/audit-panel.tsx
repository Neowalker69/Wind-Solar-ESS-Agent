"use client"

import { useState, type CSSProperties, type FormEvent } from "react"

import {
  fetchEvidenceDetail,
  fetchRunAudit,
  searchAuditResources,
} from "./audit-client"
import type {
  EvidenceDetail,
  ResourceSearchHit,
  RunAudit,
} from "./audit-contracts"


const statusColors: Record<string, string> = {
  success: "#39d98a",
  completed: "#39d98a",
  no_data: "#f4c95d",
  partial: "#f59e5b",
  failed: "#ff6b6b",
  missing: "#f4c95d",
  good: "#39d98a",
  uncertain: "#f59e5b",
  bad: "#ff6b6b",
}

export function AuditPanel({ stationId }: { stationId: string }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [runId, setRunId] = useState("")
  const [toolId, setToolId] = useState("")
  const [status, setStatus] = useState("")
  const [hits, setHits] = useState<ResourceSearchHit[]>([])
  const [audit, setAudit] = useState<RunAudit | null>(null)
  const [evidence, setEvidence] = useState<EvidenceDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function search(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError("")
    try {
      const results = await searchAuditResources({
        query: query || undefined,
        run_id: runId || undefined,
        tool_id: toolId || undefined,
        status: status || undefined,
      })
      setHits(results)
      if (runId) {
        await loadAudit(runId)
      } else if (results.length === 1 && results[0].run_id) {
        await loadAudit(results[0].run_id)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "审计检索失败")
    } finally {
      setLoading(false)
    }
  }

  async function loadAudit(selectedRunId: string) {
    setLoading(true)
    setError("")
    setEvidence(null)
    try {
      setRunId(selectedRunId)
      setAudit(await fetchRunAudit(selectedRunId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Run 审计加载失败")
    } finally {
      setLoading(false)
    }
  }

  async function loadEvidence(evidenceId: string) {
    setLoading(true)
    setError("")
    try {
      setEvidence(await fetchEvidenceDetail(evidenceId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Evidence 加载失败")
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button type="button" data-testid="audit-launcher" onClick={() => setOpen(true)} style={launcherStyle}>
        运行审计
      </button>
    )
  }

  return (
    <aside data-testid="audit-panel" style={panelStyle} aria-label="Agent Run 历史与审计">
      <header style={headerStyle}>
        <div>
          <strong>运行历史与事实审计</strong>
          <div style={mutedStyle}>场站 {stationId}</div>
        </div>
        <button type="button" onClick={() => setOpen(false)} style={plainButtonStyle}>
          关闭
        </button>
      </header>

      <form onSubmit={search} style={searchStyle}>
        <input aria-label="关键字" placeholder="问题、设备或业务关键字" value={query} onChange={(event) => setQuery(event.target.value)} style={inputStyle} />
        <input aria-label="Run ID" placeholder="Run ID（可选）" value={runId} onChange={(event) => setRunId(event.target.value)} style={inputStyle} />
        <div style={{ display: "flex", gap: 8 }}>
          <input aria-label="工具 ID" placeholder="工具 ID" value={toolId} onChange={(event) => setToolId(event.target.value)} style={{ ...inputStyle, flex: 1 }} />
          <select aria-label="状态" value={status} onChange={(event) => setStatus(event.target.value)} style={{ ...inputStyle, width: 120 }}>
            <option value="">全部状态</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
            <option value="running">running</option>
          </select>
        </div>
        <button data-testid="audit-search" type="submit" disabled={loading || (!query && !runId && !toolId && !status)} style={primaryButtonStyle}>
          {loading ? "查询中…" : "检索 PostgreSQL 历史"}
        </button>
      </form>

      {error && <div role="alert" style={{ color: "#ff8f8f", padding: "0 16px 12px" }}>{error}</div>}

      <div style={scrollStyle}>
        {hits.length > 0 && (
          <section>
            <h3 style={sectionTitleStyle}>检索结果</h3>
            {hits.map((hit) => (
              <button
                type="button"
                key={`${hit.resource_type}:${hit.resource_id}`}
                disabled={!hit.run_id}
                onClick={() => hit.run_id && loadAudit(hit.run_id)}
                style={resultButtonStyle}
              >
                <span>{hit.snippet}</span>
                <small style={mutedStyle}>{hit.resource_type} · {hit.run_id ?? "无 Run"} · {new Date(hit.occurred_at).toLocaleString()}</small>
              </button>
            ))}
          </section>
        )}

        {audit && (
          <>
            <section>
              <h3 style={sectionTitleStyle}>Run</h3>
              <div style={cardStyle}>
                <code>{audit.run.run_id}</code>
                <div>{audit.run.workflow_id} · {audit.run.model_id}</div>
                <Status value={audit.run.status} />
              </div>
            </section>
            <section>
              <h3 style={sectionTitleStyle}>时间线</h3>
              {audit.timeline.map((item, index) => (
                <div key={`${item.kind}:${item.ref_id}:${index}`} style={timelineStyle}>
                  <span style={timelineDotStyle} />
                  <div>
                    <strong>{item.kind} · {item.name}</strong>
                    <div><Status value={item.status} /></div>
                    <small style={mutedStyle}>{item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "持久工作流"}</small>
                  </div>
                </div>
              ))}
            </section>
            <section>
              <h3 style={sectionTitleStyle}>工具结果</h3>
              {audit.tool_calls.map((tool) => (
                <div key={tool.observation_id} style={cardStyle}>
                  <strong>{tool.tool_id}</strong>
                  <div><Status value={tool.status} /> <Status value={tool.quality} /></div>
                  <pre style={preStyle}>{JSON.stringify(tool.result.data ?? tool.result, null, 2)}</pre>
                  {tool.evidence_id && (
                    <button data-testid="audit-evidence-link" type="button" onClick={() => loadEvidence(tool.evidence_id!)} style={linkButtonStyle}>
                      展开 Evidence {tool.evidence_id}
                    </button>
                  )}
                </div>
              ))}
            </section>
            {audit.final && (
              <section>
                <h3 style={sectionTitleStyle}>最终回答</h3>
                <div style={cardStyle}>
                  <div>{audit.final.content}</div>
                  <small style={mutedStyle}>{audit.final.reasoning_summary}</small>
                  <div>
                    {audit.final.evidence_ids.map((evidenceId) => (
                      <button type="button" key={evidenceId} onClick={() => loadEvidence(evidenceId)} style={linkButtonStyle}>
                        {evidenceId}
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            )}
          </>
        )}

        {evidence && (
          <section>
            <h3 style={sectionTitleStyle}>Evidence 详情</h3>
            <div style={cardStyle}>
              <code>{evidence.evidence_id}</code>
              <div><Status value={evidence.quality} /> {evidence.source_locator.source_system} · {evidence.source_locator.source_resource_type}</div>
              <div style={mutedStyle}>{evidence.source_locator.source_ref}</div>
              <div style={mutedStyle}>fact: {evidence.fact_time ?? "未提供"} · trace: {evidence.source_locator.upstream_trace_id ?? "未提供"}</div>
              <div style={mutedStyle}>hash: {evidence.content_hash ?? "未提供"}</div>
              <pre style={preStyle}>{JSON.stringify(evidence.snapshot, null, 2)}</pre>
            </div>
          </section>
        )}
      </div>
    </aside>
  )
}

function Status({ value }: { value: string }) {
  return <span style={{ ...statusStyle, color: statusColors[value] ?? "#b7c0cc" }}>{value}</span>
}

const launcherStyle: CSSProperties = { position: "fixed", zIndex: 80, top: 72, right: 16, border: "1px solid #3b82f6", borderRadius: 6, background: "#0b1729", color: "#dbeafe", padding: "8px 12px", cursor: "pointer" }
const panelStyle: CSSProperties = { position: "fixed", zIndex: 90, top: 56, right: 0, bottom: 0, width: "min(460px, 94vw)", background: "rgba(7, 16, 30, 0.98)", color: "#e5edf7", borderLeft: "1px solid #233650", boxShadow: "-12px 0 30px rgba(0,0,0,.35)", fontFamily: "ui-sans-serif, system-ui" }
const headerStyle: CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottom: "1px solid #233650" }
const searchStyle: CSSProperties = { display: "grid", gap: 8, padding: 16 }
const inputStyle: CSSProperties = { minWidth: 0, border: "1px solid #334962", borderRadius: 5, background: "#0d1c30", color: "#e5edf7", padding: "8px 10px" }
const primaryButtonStyle: CSSProperties = { border: 0, borderRadius: 5, background: "#2563eb", color: "white", padding: "9px 12px", cursor: "pointer" }
const plainButtonStyle: CSSProperties = { border: 0, background: "transparent", color: "#9fb0c4", cursor: "pointer" }
const linkButtonStyle: CSSProperties = { border: 0, background: "transparent", color: "#6ea8ff", padding: "6px 8px 0 0", cursor: "pointer", textAlign: "left" }
const scrollStyle: CSSProperties = { overflowY: "auto", height: "calc(100% - 238px)", padding: "0 16px 24px" }
const sectionTitleStyle: CSSProperties = { margin: "16px 0 8px", fontSize: 13, color: "#8fa9c6", textTransform: "uppercase", letterSpacing: ".08em" }
const cardStyle: CSSProperties = { display: "grid", gap: 7, border: "1px solid #263b54", borderRadius: 6, background: "#0b1729", padding: 12, marginBottom: 8 }
const resultButtonStyle: CSSProperties = { ...cardStyle, width: "100%", color: "#e5edf7", cursor: "pointer", textAlign: "left" }
const timelineStyle: CSSProperties = { display: "grid", gridTemplateColumns: "14px 1fr", gap: 8, padding: "5px 0 10px" }
const timelineDotStyle: CSSProperties = { width: 8, height: 8, borderRadius: "50%", background: "#4f8cff", marginTop: 5 }
const statusStyle: CSSProperties = { display: "inline-block", fontFamily: "ui-monospace, monospace", fontSize: 12, marginRight: 6 }
const mutedStyle: CSSProperties = { color: "#8799ad", fontSize: 12 }
const preStyle: CSSProperties = { overflowX: "auto", margin: 0, maxHeight: 180, background: "#07101e", padding: 8, borderRadius: 4, fontSize: 11, whiteSpace: "pre-wrap" }
