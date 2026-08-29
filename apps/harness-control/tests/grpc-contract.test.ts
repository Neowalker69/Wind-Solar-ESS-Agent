import path from "node:path"

import { loadSync } from "@grpc/proto-loader"
import protobuf from "protobufjs"
import { describe, expect, it } from "@jest/globals"

const repoRoot = path.resolve(process.cwd(), "../..")
const protoPath = path.join(repoRoot, "proto/agent_runtime/v1/runtime.proto")
const startTurnFixture = {
  runId: "run-contract-1",
  sessionId: "session-contract-1",
  text: "检查储能设备状态",
  context: {
    selectedAssetId: "PCS-01",
    environment: "test",
    attributes: { siteId: "station-demo" }
  },
  toolRefs: [{ toolId: "asset.get_status", version: "1.0.0" }],
  skillRefs: [],
  policy: { visibleToolIds: ["asset.get_status"], workflowStage: "diagnosis" },
  approval: { status: "APPROVAL_STATUS_NOT_REQUIRED" }
}

describe("Agent Runtime gRPC contract", () => {
  it("exposes the three confirmed versioned RPCs", () => {
    const definition = loadSync(protoPath)
    const service = definition["agent_harness.runtime.v1.AgentRuntime"]

    expect(service).toBeDefined()
    expect(Object.keys(service as object)).toEqual([
      "StartTurn",
      "StreamRunEvents",
      "GetRuntimeSnapshot"
    ])
  })

  it("round-trips a repository-local StartTurn fixture", () => {
    const root = protobuf.loadSync(protoPath)
    const startTurnRequest = root.lookupType("agent_harness.runtime.v1.StartTurnRequest")
    const message = startTurnRequest.fromObject(startTurnFixture)
    const wire = startTurnRequest.encode(message).finish()
    const decoded = startTurnRequest.toObject(startTurnRequest.decode(wire), {
      defaults: true,
      enums: String,
      longs: String
    })

    expect(decoded).toMatchObject(startTurnFixture)
  })
})
