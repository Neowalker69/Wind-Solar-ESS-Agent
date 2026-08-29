import { timingSafeEqual } from "node:crypto"

import type { ControlIdentity } from "./control-auth"

export function authenticateLocalControlCredentials(
  username: string,
  password: string
): ControlIdentity | null {
  const expectedUsername = process.env.CONTROL_PANEL_USERNAME ?? "admin"
  const expectedPassword = process.env.CONTROL_PANEL_PASSWORD
  if (!expectedPassword) throw new Error("CONTROL_PANEL_PASSWORD is required")

  if (!safeEqual(username.trim(), expectedUsername) || !safeEqual(password, expectedPassword)) {
    return null
  }
  return { userId: expectedUsername, role: "admin", tenantId: "tenant_lab" }
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left)
  const rightBuffer = Buffer.from(right)
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer)
}
