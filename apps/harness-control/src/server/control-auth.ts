import { createHmac, randomUUID, timingSafeEqual } from "node:crypto"

interface JwtPayload {
  sub?: string
  exp?: number
  role?: string
  tenant_id?: string
}

export interface ControlIdentity {
  userId: string
  role: string
  tenantId: string
}

export function createControlAccessToken(
  identity: ControlIdentity,
  expiresInSeconds = 8 * 60 * 60
): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url")
  const payload = Buffer.from(JSON.stringify({
    sub: identity.userId,
    role: identity.role,
    tenant_id: identity.tenantId,
    exp: Math.floor(Date.now() / 1000) + expiresInSeconds
  })).toString("base64url")
  return `${header}.${payload}.${sign(`${header}.${payload}`, jwtSecret())}`
}

export class ControlAuthError extends Error {
  constructor(
    readonly status: number,
    readonly code: string
  ) {
    super(code)
  }
}

export function authenticateControlRequest(request: Request): ControlIdentity {
  const authorization = request.headers.get("Authorization") ?? ""
  if (!authorization.startsWith("Bearer ")) {
    throw new ControlAuthError(401, "auth_missing")
  }
  const token = authorization.slice("Bearer ".length).trim()
  const [headerPart, payloadPart, signaturePart] = token.split(".")
  if (!headerPart || !payloadPart || !signaturePart) {
    throw new ControlAuthError(401, "auth_invalid")
  }
  let header: { alg?: string }
  let payload: JwtPayload
  try {
    header = JSON.parse(Buffer.from(headerPart, "base64url").toString("utf8"))
    payload = JSON.parse(Buffer.from(payloadPart, "base64url").toString("utf8"))
  } catch {
    throw new ControlAuthError(401, "auth_invalid")
  }
  if (header.alg !== "HS256") throw new ControlAuthError(401, "auth_invalid")
  const expected = sign(`${headerPart}.${payloadPart}`, jwtSecret())
  const received = Buffer.from(signaturePart)
  const expectedBuffer = Buffer.from(expected)
  if (
    received.length !== expectedBuffer.length
    || !timingSafeEqual(received, expectedBuffer)
  ) {
    throw new ControlAuthError(401, "auth_invalid")
  }
  if (!payload.sub || (payload.exp && payload.exp < Math.floor(Date.now() / 1000))) {
    throw new ControlAuthError(401, "auth_expired")
  }
  return {
    userId: payload.sub,
    role: payload.role ?? "operator",
    tenantId: payload.tenant_id ?? "tenant_lab"
  }
}

export function createControlSessionId(identity: ControlIdentity): string {
  const subject = Buffer.from(identity.userId).toString("base64url")
  const payload = `${subject}~${randomUUID().replaceAll("-", "")}`
  return `session_${payload}.${sign(payload, jwtSecret())}`
}

export function authorizeControlSession(
  identity: ControlIdentity,
  sessionId: string
): void {
  const unsigned = sessionId.replace(/^session_/, "")
  const [payloadPart, signaturePart] = unsigned.split(".")
  if (!payloadPart || !signaturePart) {
    throw new ControlAuthError(404, "session_not_found")
  }
  const expected = sign(payloadPart, jwtSecret())
  if (
    signaturePart.length !== expected.length
    || !timingSafeEqual(Buffer.from(signaturePart), Buffer.from(expected))
  ) {
    throw new ControlAuthError(404, "session_not_found")
  }
  let subject: string
  try {
    subject = Buffer.from(payloadPart.split("~", 1)[0], "base64url").toString("utf8")
  } catch {
    throw new ControlAuthError(404, "session_not_found")
  }
  if (subject !== identity.userId) {
    throw new ControlAuthError(403, "session_forbidden")
  }
}

export function controlAuthErrorResponse(error: unknown): Response {
  if (!(error instanceof ControlAuthError)) throw error
  return Response.json(
    { data: null, meta: {}, error: { code: error.code, message: error.code } },
    { status: error.status }
  )
}

function jwtSecret(): string {
  const secret = process.env.JWT_SECRET
  if (!secret) throw new Error("JWT_SECRET is required")
  return secret
}

function sign(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("base64url")
}
