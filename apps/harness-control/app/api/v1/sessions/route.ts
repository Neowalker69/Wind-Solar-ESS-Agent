import { NextResponse } from "next/server"

import { createSessionInputSchema } from "../../../../src/contracts/control"
import { invalidJsonResponse, validationErrorResponse } from "../../../../src/server/http-response"
import {
  authenticateControlRequest,
  controlAuthErrorResponse,
  createControlSessionId
} from "../../../../src/server/control-auth"

export async function POST(request: Request): Promise<NextResponse> {
  let identity
  try {
    identity = authenticateControlRequest(request)
  } catch (error) {
    return controlAuthErrorResponse(error) as NextResponse
  }
  let payload: unknown
  try {
    payload = await request.json()
  } catch {
    return invalidJsonResponse()
  }

  const parsed = createSessionInputSchema.safeParse(payload)
  if (!parsed.success) {
    return validationErrorResponse(parsed.error)
  }
  if (parsed.data.user.user_id !== identity.userId) {
    return NextResponse.json(
      { data: null, meta: {}, error: { code: "user_identity_mismatch" } },
      { status: 403 }
    )
  }

  return NextResponse.json({
    data: {
      session: {
        session_id: createControlSessionId(identity),
        user: parsed.data.user,
        selected_asset_id: parsed.data.context.selected_asset_id ?? null,
        context: parsed.data.context
      }
    },
    meta: {}
  }, { status: 201 })
}
