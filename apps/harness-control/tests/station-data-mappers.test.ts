import { describe, expect, it } from "@jest/globals"

import { mapAlarmItems, mapDeviceTreeToContainers, type WorkspaceContainer } from "../src/workspace/station-data-mappers"

describe("station data mappers", () => {
  it("uses the Go device tree summaries to update matching storage containers without inventing new devices", () => {
    const fallback: WorkspaceContainer[] = [
      { id: "A-01", severity: "normal", soc: 80, temp: 28.5, power: 320 },
      { id: "A-03", severity: "critical", soc: 13, temp: 56.5, power: 0 }
    ]

    expect(mapDeviceTreeToContainers([{ device_id: "site", name: "site", station_id: "station-demo", device_type: "station", status: "normal", children: [{
      device_id: "A-01",
      name: "A-01",
      station_id: "station-demo",
      device_type: "storage",
      status: "warning",
      summary: { status: "warning", latest: { soc: 62, temperature: 41.2, power_kw: 178 } },
      children: []
    }] }], fallback)).toEqual([
      { id: "A-01", severity: "warning", soc: 62, temp: 41.2, power: 178 },
      fallback[1]
    ])
  })

  it("maps the UI short code to the canonical Station device id", () => {
    const fallback: WorkspaceContainer[] = [
      { id: "A-01", severity: "normal", soc: 80, temp: 28.5, power: 320 }
    ]

    expect(mapDeviceTreeToContainers([{ device_id: "ess-station-01", name: "场站", station_id: "ess-station-01", device_type: "station", status: "normal", children: [{
      device_id: "ess-station-01.container-a-01",
      code: "A-01",
      name: "A-01",
      station_id: "ess-station-01",
      device_type: "storage",
      status: "normal",
      children: []
    }] }], fallback)).toMatchObject([{
      id: "A-01",
      stationDeviceId: "ess-station-01.container-a-01"
    }])
  })

  it("maps Go alarms to the existing workbench alarm presentation contract", () => {
    expect(mapAlarmItems([{
      alarm_uuid: "alarm-1",
      device_id: "A-03",
      severity: "critical",
      message: "温度高于阈值",
      status: "active",
      triggered_at: "2026-07-17T11:23:18Z"
    }])).toEqual([{
      id: "alarm-1",
      deviceId: "A-03",
      severity: "critical",
      title: "温度高于阈值",
      detail: "A-03 · active",
      time: "11:23:18"
    }])
  })

  it("keeps alarm display ids short while retaining canonical device identity", () => {
    expect(mapAlarmItems([{
      alarm_uuid: "alarm-1",
      device_id: "ess-station-01.container-a-01",
      severity: "critical",
      message: "温度高于阈值",
      status: "active",
      triggered_at: "2026-07-17T11:23:18Z"
    }], [{
      device_id: "ess-station-01.container-a-01",
      code: "A-01",
      name: "A-01",
      station_id: "ess-station-01",
      device_type: "storage",
      status: "critical",
      children: []
    }])).toMatchObject([{
      deviceId: "A-01",
      stationDeviceId: "ess-station-01.container-a-01"
    }])
  })
})
