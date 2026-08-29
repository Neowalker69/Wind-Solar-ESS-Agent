import { afterEach, beforeEach, describe, expect, it } from "@jest/globals"

import { POST as login } from "../app/api/v1/auth/login/route"
import { GET as currentUser } from "../app/api/v1/users/me/route"

describe("Harness Control local login routes", () => {
  beforeEach(() => {
    process.env.JWT_SECRET = "control-login-test-jwt-secret"
    process.env.CONTROL_PANEL_USERNAME = "admin"
    process.env.CONTROL_PANEL_PASSWORD = "admin123"
  })

  afterEach(() => {
    delete process.env.JWT_SECRET
    delete process.env.CONTROL_PANEL_USERNAME
    delete process.env.CONTROL_PANEL_PASSWORD
  })

  it("signs in with the configured demo credentials and validates the token", async () => {
    const response = await login(new Request("http://localhost/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "admin", password: "admin123" })
    }))
    expect(response.status).toBe(200)
    const body = await response.json()
    expect(body).toMatchObject({ code: 0, data: { token_type: "Bearer", expires_in: 28_800 } })

    const me = await currentUser(new Request("http://localhost/api/v1/users/me", {
      headers: { Authorization: `Bearer ${body.data.access_token}` }
    }))
    expect(me.status).toBe(200)
    await expect(me.json()).resolves.toMatchObject({
      code: 0,
      data: { id: "admin", username: "admin", role: "admin" }
    })
  })

  it("rejects an incorrect password", async () => {
    const response = await login(new Request("http://localhost/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "admin", password: "wrong" })
    }))
    expect(response.status).toBe(401)
    await expect(response.json()).resolves.toMatchObject({ code: 1001, data: null })
  })
})
