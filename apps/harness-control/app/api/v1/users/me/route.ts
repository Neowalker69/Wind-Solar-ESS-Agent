import { randomUUID } from "node:crypto"
import { NextResponse } from "next/server"

import {
  authenticateControlRequest,
  controlAuthErrorResponse
} from "../../../../../src/server/control-auth"

export async function GET(request: Request): Promise<NextResponse> {
  try {
    const identity = authenticateControlRequest(request)
    return NextResponse.json({
      code: 0,
      message: "ok",
      data: { id: identity.userId, username: identity.userId, role: identity.role },
      trace_id: randomUUID()
    })
  } catch (error) {
    const response = controlAuthErrorResponse(error)
    return NextResponse.json({
      code: 1002,
      message: "invalid or expired token",
      data: null,
      trace_id: randomUUID()
    }, { status: response.status })
  }
}
