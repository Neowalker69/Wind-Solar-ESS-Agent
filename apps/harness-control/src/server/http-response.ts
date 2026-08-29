import { NextResponse } from "next/server"
import { z } from "zod"

export function validationErrorResponse(error: z.ZodError): NextResponse {
  return NextResponse.json({
    error: {
      code: "validation_error",
      message: "请求数据不符合 Harness Control 契约",
      details: error.issues.map((issue) => ({
        field: issue.path.join("."),
        code: issue.code,
        message: issue.message
      }))
    }
  }, { status: 422 })
}

export function invalidJsonResponse(): NextResponse {
  return NextResponse.json({
    error: {
      code: "invalid_json",
      message: "请求体必须是有效 JSON"
    }
  }, { status: 400 })
}
