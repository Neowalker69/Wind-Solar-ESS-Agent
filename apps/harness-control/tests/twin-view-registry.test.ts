import { describe, expect, it } from "@jest/globals"

import {
  buildTwinViewHref,
  resolveTwinView,
  TWIN_VIEW_DEFINITIONS,
  viewDefinitionForIndex
} from "../src/workspace/twin-view-registry"

describe("Twin View registry", () => {
  it("uses one complete definition for every Topbar view", () => {
    expect(TWIN_VIEW_DEFINITIONS.map((definition) => definition.id)).toEqual([
      "data",
      "thermal",
      "power-flow",
      "alarms",
      "video"
    ])

    for (const definition of TWIN_VIEW_DEFINITIONS) {
      expect(definition).toMatchObject({
        routeSegment: expect.any(String),
        dashboard: expect.any(String),
        sceneProfile: expect.any(String),
        legendProfile: expect.any(String),
        telemetryProfile: expect.any(String)
      })
    }
  })

  it("resolves routes and keeps a stable default for an unknown view", () => {
    expect(resolveTwinView("alarms").id).toBe("alarms")
    expect(resolveTwinView("missing").id).toBe("data")
  })

  it("builds the station, view and selected asset URL from the registry", () => {
    expect(buildTwinViewHref("station-demo", "thermal", "A-03")).toBe(
      "/stations/station-demo/thermal?assetId=A-03"
    )
  })

  it("maps legacy workspace indices through the same registry with a stable fallback", () => {
    expect(viewDefinitionForIndex(3)).toMatchObject({
      id: "alarms",
      dashboard: "alarms",
      sceneProfile: "alarm",
      legendProfile: "alarm",
      telemetryProfile: "alarms"
    })
    expect(viewDefinitionForIndex(99)).toBe(resolveTwinView(undefined))
  })
})
