import { describe, expect, it } from "@jest/globals"

import { POST as createSession } from "../app/api/v1/sessions/route"
import { POST as createTurn } from "../app/api/v1/sessions/[sessionId]/turns/route"
import { createControlSessionId } from "../src/server/control-auth"
import { controlAuthHeaders } from "./control-auth-helper"

function sessionId(userId = "operator-1") {
  controlAuthHeaders(userId)
  return createControlSessionId({ userId, role: "operator", tenantId: "tenant_lab" })
}

describe("Harness Control session routes", () => {
  it("creates a session from schema-validated browser input", async () => {
    const response = await createSession(new Request("http://localhost/api/v1/sessions", {
      method: "POST",
      headers: controlAuthHeaders(),
      body: JSON.stringify({
        user: { user_id: "operator-1", role: "operator", site_id: "site-a" },
        context: { selected_asset_id: "pump-101", environment: "dev" }
      })
    }))

    expect(response.status).toBe(201)
    await expect(response.json()).resolves.toMatchObject({
      data: {
        session: {
          session_id: expect.any(String),
          selected_asset_id: "pump-101"
        }
      }
    })
  })

  it("returns field-level validation errors for an invalid session", async () => {
    const response = await createSession(new Request("http://localhost/api/v1/sessions", {
      method: "POST",
      headers: controlAuthHeaders(),
      body: JSON.stringify({ context: {} })
    }))

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: "validation_error", details: expect.any(Array) }
    })
  })

  it("rejects malformed session JSON", async () => {
    const response = await createSession(new Request("http://localhost/api/v1/sessions", {
      method: "POST",
      headers: controlAuthHeaders(),
      body: "{"
    }))

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: "invalid_json" }
    })
  })

  it("submits a validated turn through the Runtime Client boundary", async () => {
    const currentSessionId = sessionId()
    const response = await createTurn(new Request(`http://localhost/api/v1/sessions/${currentSessionId}/turns`, {
      method: "POST",
      headers: controlAuthHeaders(),
      body: JSON.stringify({
        text: "检查泵的当前状态",
        context: { selected_asset_id: "pump-101", environment: "dev" },
        tool_refs: [{ tool_id: "asset.get_status", version: "1.0.0" }],
        skill_refs: [],
        policy: { visible_tool_ids: ["asset.get_status"], workflow_stage: "diagnosis" },
        approval: { status: "not_required" }
      })
    }), { params: Promise.resolve({ sessionId: currentSessionId }) })

    expect(response.status).toBe(202)
    await expect(response.json()).resolves.toMatchObject({
      data: {
        run: {
          session_id: currentSessionId,
          run_id: expect.any(String),
          status: "running"
        }
      }
    })
  })

  it("does not forward browser-supplied handler addresses to the runtime", async () => {
    const currentSessionId = sessionId()
    const response = await createTurn(new Request(`http://localhost/api/v1/sessions/${currentSessionId}/turns`, {
      method: "POST",
      headers: controlAuthHeaders(),
      body: JSON.stringify({
        text: "检查泵的当前状态",
        context: {},
        tool_refs: [],
        skill_refs: [],
        policy: { visible_tool_ids: [] },
        approval: { status: "not_required" },
        handler: "untrusted.module:handle"
      })
    }), { params: Promise.resolve({ sessionId: currentSessionId }) })

    expect(response.status).toBe(422)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: "validation_error" }
    })
  })

  it("rejects malformed turn JSON", async () => {
    const currentSessionId = sessionId()
    const response = await createTurn(new Request(`http://localhost/api/v1/sessions/${currentSessionId}/turns`, {
      method: "POST",
      headers: controlAuthHeaders(),
      body: "{"
    }), { params: Promise.resolve({ sessionId: currentSessionId }) })

    expect(response.status).toBe(400)
    await expect(response.json()).resolves.toMatchObject({
      error: { code: "invalid_json" }
    })
  })
})
