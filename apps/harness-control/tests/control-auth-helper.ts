import { createHmac } from "node:crypto"

export const TEST_JWT_SECRET = "harness-control-test-jwt-secret"

export function controlAuthHeaders(userId = "operator-1"): Record<string, string> {
  process.env.JWT_SECRET = TEST_JWT_SECRET
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url")
  const payload = Buffer.from(JSON.stringify({
    sub: userId,
    role: "operator",
    exp: Math.floor(Date.now() / 1000) + 3600
  })).toString("base64url")
  const signature = createHmac("sha256", TEST_JWT_SECRET)
    .update(`${header}.${payload}`)
    .digest("base64url")
  return { Authorization: `Bearer ${header}.${payload}.${signature}` }
}
