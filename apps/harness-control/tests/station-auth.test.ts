import { describe, expect, it, jest as vi } from "@jest/globals"

import {
  STATION_TOKEN_KEY,
  authenticateStation,
  clearStationToken,
  readStationToken,
  validateStationToken
} from "../src/auth/station-auth"

class MemoryStorage implements Pick<Storage, "getItem" | "setItem" | "removeItem"> {
  private readonly values = new Map<string, string>()

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }

  removeItem(key: string): void {
    this.values.delete(key)
  }
}

describe("Station authentication", () => {
  it("exchanges username and password for an access token kept in session storage", async () => {
    const storage = new MemoryStorage()
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      code: 0,
      message: "ok",
      data: { access_token: "station-jwt", token_type: "Bearer", expires_in: 3600 },
      trace_id: "trace-auth"
    }), { status: 200, headers: { "Content-Type": "application/json" } }))

    await expect(authenticateStation("admin", "generated-password", {
      fetchImpl: fetchMock as typeof fetch,
      storage
    })).resolves.toBe("station-jwt")

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/login", expect.objectContaining({
      method: "POST",
      credentials: "include"
    }))
    expect(storage.getItem(STATION_TOKEN_KEY)).toBe("station-jwt")
    expect(readStationToken(storage)).toBe("station-jwt")
  })

  it("rejects invalid credentials without persisting a token", async () => {
    const storage = new MemoryStorage()
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      code: 1001,
      message: "invalid username or password",
      trace_id: "trace-denied"
    }), { status: 401, headers: { "Content-Type": "application/json" } }))

    await expect(authenticateStation("admin", "wrong", {
      fetchImpl: fetchMock as typeof fetch,
      storage
    })).rejects.toThrow("用户名或密码无效")
    expect(storage.getItem(STATION_TOKEN_KEY)).toBeNull()
  })

  it("validates and clears an existing station token", async () => {
    const storage = new MemoryStorage()
    storage.setItem(STATION_TOKEN_KEY, "station-jwt")
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      code: 0,
      message: "ok",
      data: { id: 1, username: "admin", role: "admin" },
      trace_id: "trace-me"
    }), { status: 200, headers: { "Content-Type": "application/json" } }))

    await expect(validateStationToken("station-jwt", fetchMock as typeof fetch)).resolves.toBe(true)
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/users/me", expect.objectContaining({
      headers: { Authorization: "Bearer station-jwt" }
    }))

    clearStationToken(storage)
    expect(storage.getItem(STATION_TOKEN_KEY)).toBeNull()
  })
})
