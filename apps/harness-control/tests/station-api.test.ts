import { afterEach, beforeEach, describe, expect, it, jest as vi } from "@jest/globals"

import {
  buildStationApiUrl,
  fetchStationApi,
  resetStationApiTokenForTests,
  unwrapStationEnvelope,
} from "../src/workspace/station-api"
import { restoreGlobalStubs, stubGlobal } from "./test-global-stubs"

describe("Station API client", () => {
  beforeEach(() => {
    const values = new Map<string, string>()
    stubGlobal("sessionStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    })
    resetStationApiTokenForTests()
  })

  afterEach(() => restoreGlobalStubs())

  it("builds Go API URLs without coupling view components to endpoint strings", () => {
    expect(buildStationApiUrl("/devices/tree", { station_id: "station-demo", depth: 3 })).toBe(
      "/api/v1/devices/tree?station_id=station-demo&depth=3"
    )
  })

  it("unwraps the existing Go response envelope and preserves its stable error", () => {
    expect(unwrapStationEnvelope({ code: 0, message: "ok", data: { device_id: "A-03" }, trace_id: "trace-1" })).toEqual({ device_id: "A-03" })
    expect(() => unwrapStationEnvelope({ code: 2002, message: "not found", trace_id: "trace-2" })).toThrow("station_api_2002:not found")
  })

  it("uses the authenticated station token without calling the deprecated Agent bootstrap", async () => {
    sessionStorage.setItem("station.accessToken", "shared-local-jwt")
    const fetchMock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0,
        message: "ok",
        data: [{ device_id: "A-03" }],
        trace_id: "trace-1",
      }), { status: 200 }))
    stubGlobal("fetch", fetchMock)

    await expect(fetchStationApi<Array<{ device_id: string }>>("/devices/tree")).resolves.toEqual([
      { device_id: "A-03" },
    ])
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/devices/tree", {
      credentials: "include",
      headers: { Authorization: "Bearer shared-local-jwt" },
    })
    expect(sessionStorage.getItem("station.accessToken")).toBe("shared-local-jwt")
  })
})
