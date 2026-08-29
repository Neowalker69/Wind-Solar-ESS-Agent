import { afterEach, beforeEach, describe, expect, it, jest as vi } from "@jest/globals"

import {
  fetchEvidenceDetail,
  fetchRunAudit,
  searchAuditResources,
} from "../src/audit/audit-client"
import { restoreGlobalStubs, stubGlobal } from "./test-global-stubs"


describe("Harness audit client", () => {
  beforeEach(() => {
    const values = new Map<string, string>([["station.accessToken", "audit-token"]])
    stubGlobal("sessionStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    })
  })

  afterEach(() => restoreGlobalStubs())

  it("searches persistent resources with the shared bearer token", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      data: {
        hits: [{
          resource_type: "trace_event",
          resource_id: "event-1",
          session_id: "session-1",
          run_id: "run-1",
          snippet: "分析 A-01 当前告警",
          occurred_at: "2026-07-19T09:30:00Z",
          score: 0.8,
        }],
      },
      meta: {},
      error: null,
    }), { status: 200 }))
    stubGlobal("fetch", fetchMock)

    const hits = await searchAuditResources({ query: "A-01", tool_id: "alarm.get_active_alarms" })

    expect(hits[0].run_id).toBe("run-1")
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/resources/search?query=A-01&tool_id=alarm.get_active_alarms",
      {
        credentials: "include",
        headers: { Authorization: "Bearer audit-token" },
      },
    )
  })

  it("validates run audit and evidence detail envelopes", async () => {
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: {
          run: {
            run_id: "run-1",
            session_id: "session-1",
            status: "completed",
            workflow_id: "alarm_investigation_graph",
            model_id: "deepseek-v4-flash",
          },
          intent: { intent_id: "diagnosis.alarm" },
          model_calls: [],
          tool_calls: [{
            observation_id: "obs-1",
            tool_id: "alarm.get_active_alarms",
            tool_version: "0.1.0",
            status: "no_data",
            quality: "missing",
            result: { status: "no_data", data: { items: [] } },
            evidence_id: null,
            occurred_at: "2026-07-19T09:30:00Z",
          }],
          observations: [],
          evidence: [],
          workflows: [],
          final: null,
          timeline: [],
        },
        meta: {},
        error: null,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: {
          evidence_id: "ev-1",
          run_id: "run-1",
          trace_id: "trace-1",
          source_type: "alarm",
          source_ref: "alarm:1",
          quality: "good",
          data: {},
          recorded_at: "2026-07-19T09:30:00Z",
          snapshot: { alarm_uuid: "alarm-1" },
          content_hash: "sha256:1",
          fact_time: "2026-07-19T09:29:00Z",
          observed_at: "2026-07-19T09:30:00Z",
          query_window: null,
          aggregation: null,
          source_locator: {
            source_system: "station_api",
            source_resource_type: "alarm",
            source_ref: "alarm:1",
            upstream_trace_id: "station-trace-1",
          },
        },
        meta: {},
        error: null,
      }), { status: 200 }))
    stubGlobal("fetch", fetchMock)

    const audit = await fetchRunAudit("run-1")
    const evidence = await fetchEvidenceDetail("ev-1")

    expect(audit.tool_calls[0].status).toBe("no_data")
    expect(evidence.source_locator.source_system).toBe("station_api")
  })
})
