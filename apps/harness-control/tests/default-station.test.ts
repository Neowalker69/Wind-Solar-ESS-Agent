import { describe, expect, it } from "@jest/globals"

import {
  defaultStationHref,
  DEFAULT_STATION_VIEW,
  P2_AUTHORITATIVE_STATION_ID
} from "../src/workspace/default-station"

describe("default station route", () => {
  it("opens the P2 authoritative station by default", () => {
    expect(P2_AUTHORITATIVE_STATION_ID).toBe("ess-station-01")
    expect(DEFAULT_STATION_VIEW).toBe("data")
    expect(defaultStationHref()).toBe("/stations/ess-station-01/data")
  })
})
