import { randomUUID } from "node:crypto"
import { NextResponse } from "next/server"

import { createControlAccessToken } from "../../../../../src/server/control-auth"
import { authenticateLocalControlCredentials } from "../../../../../src/server/local-control-auth"

export async function POST(request: Request): Promise<NextResponse> {
  let payload: unknown
  try {
    payload = await request.json()
  } catch {
    return stationResponse(400, 1000, "invalid request")
  }

  if (!isLoginPayload(payload)) return stationResponse(400, 1000, "username and password are required")

  const identity = authenticateLocalControlCredentials(payload.username, payload.password)
  if (!identity) return stationResponse(401, 1001, "invalid username or password")

  return stationResponse(200, 0, "ok", {
    access_token: createControlAccessToken(identity),
    token_type: "Bearer",
    expires_in: 8 * 60 * 60
  })
}

function isLoginPayload(value: unknown): value is { username: string; password: string } {
  if (!value || typeof value !== "object") return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.username === "string" && typeof candidate.password === "string"
}

function stationResponse(status: number, code: number, message: string, data: unknown = null): NextResponse {
  return NextResponse.json({ code, message, data, trace_id: randomUUID() }, { status })
}
