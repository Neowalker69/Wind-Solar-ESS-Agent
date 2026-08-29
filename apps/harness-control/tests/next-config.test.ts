import path from "node:path"
import fs from "node:fs"

import { describe, expect, it } from "@jest/globals"

import nextConfig from "../next.config.mjs"

describe("Next workspace module resolution", () => {
  it("resolves external frontend imports from the React 19 application first", () => {
    const webpackConfig = {
      module: { rules: [] as object[] },
      plugins: [] as object[],
      resolve: { modules: ["node_modules"] }
    }
    class DefinePlugin {}
    const applyWebpack = nextConfig.webpack as unknown as (
      config: typeof webpackConfig,
      context: { webpack: { DefinePlugin: typeof DefinePlugin } }
    ) => typeof webpackConfig

    applyWebpack(webpackConfig, { webpack: { DefinePlugin } })

    expect(webpackConfig.resolve.modules[0]).toBe(path.resolve(process.cwd(), "node_modules"))
  })

  it("keeps browser clients on Next Control instead of the legacy Agent API", () => {
    const browserClient = fs.readFileSync(
      path.resolve(process.cwd(), "src/agent-workbench/agent-stream-client.ts"),
      "utf8"
    )
    const stationClient = fs.readFileSync(
      path.resolve(process.cwd(), "src/workspace/station-api.ts"),
      "utf8"
    )
    expect(browserClient).not.toContain("/api/v1/agent/")
    expect(stationClient).not.toContain("/api/v1/agent/")
  })
})
