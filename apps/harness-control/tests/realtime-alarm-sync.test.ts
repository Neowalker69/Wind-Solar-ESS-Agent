import { describe, expect, it } from "@jest/globals"

import { mapAlarmItems } from "../src/workspace/station-data-mappers"
import { alarmListQueryOptions, STATION_REALTIME_REFRESH_MS } from "../src/workspace/station-queries"

describe("realtime alarm synchronization", () => {
  it("refreshes the authoritative active alarm snapshot every five seconds", () => {
    expect(STATION_REALTIME_REFRESH_MS).toBe(5_000)
    expect(alarmListQueryOptions().refetchInterval).toBe(STATION_REALTIME_REFRESH_MS)
  })

  it("keeps simultaneous OPC UA alarms as independently keyed stacked cards", () => {
    const alerts = mapAlarmItems([
      {
        alarm_uuid: "alarm-a01-temperature",
        device_id: "A-01",
        severity: "critical",
        message: "BESS_A_01 high-temperature protection tripped the container",
        status: "active",
        triggered_at: "2026-08-26T12:20:07Z"
      },
      {
        alarm_uuid: "alarm-a02-soc",
        device_id: "A-02",
        severity: "warning",
        message: "BESS_A_02 SOC is below the normal operating range",
        status: "active",
        triggered_at: "2026-08-26T12:20:06Z"
      }
    ])

    expect(alerts).toHaveLength(2)
    expect(alerts.map((alert) => alert.id)).toEqual([
      "alarm-a01-temperature",
      "alarm-a02-soc"
    ])
    expect(alerts.map((alert) => alert.deviceId)).toEqual(["A-01", "A-02"])
  })
})
