import { NextResponse } from "next/server"

import { toRuntimeTurnRequest, turnInputSchema } from "../../../../../../src/contracts/control"
import { invalidJsonResponse, validationErrorResponse } from "../../../../../../src/server/http-response"
import { createRuntimeClient, projectRuntimeStartError } from "../../../../../../src/server/runtime-client"
import {
  authenticateControlRequest,
  authorizeControlSession,
  controlAuthErrorResponse
} from "../../../../../../src/server/control-auth"

interface RouteContext {
  params: Promise<{ sessionId: string }>
}

export async function POST(request: Request, context: RouteContext): Promise<NextResponse> {
  const { sessionId } = await context.params
  try {
    const identity = authenticateControlRequest(request)
    authorizeControlSession(identity, sessionId)
  } catch (error) {
    return controlAuthErrorResponse(error) as NextResponse
  }
  let payload: unknown
  try {
    payload = await request.json()
  } catch {
    return invalidJsonResponse()
  }

  const parsed = turnInputSchema.safeParse(payload)
  if (!parsed.success) {
    return validationErrorResponse(parsed.error)
  }

  const runtimeClient = createRuntimeClient()
  let run
  try {
    run = await runtimeClient.startTurn(toRuntimeTurnRequest(sessionId, parsed.data))
  } catch (error) {
    const projected = projectRuntimeStartError(error)
    return NextResponse.json(
      { data: null, meta: {}, error: { code: projected.code, message: projected.message } },
      { status: projected.status }
    )
  }

  return NextResponse.json({ data: { run }, meta: {} }, { status: 202 })
}
