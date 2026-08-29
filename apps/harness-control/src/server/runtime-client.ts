import { randomUUID } from "node:crypto"
import path from "node:path"

import * as grpc from "@grpc/grpc-js"
import { loadSync } from "@grpc/proto-loader"

import type { ContextSnapshot, RuntimeEvent, RuntimeTurnRequest } from "../contracts/control"

export interface RuntimeRunAcceptance {
  run_id: string
  session_id: string
  status: "accepted" | "running" | "waiting" | "completed" | "failed" | "cancelled"
}

export interface RuntimeClient {
  startTurn(request: RuntimeTurnRequest): Promise<RuntimeRunAcceptance>
  streamRunEvents(runId: string, afterSequence?: number): AsyncIterable<RuntimeEvent>
  getRuntimeSnapshot(sessionId: string, runId: string): Promise<RuntimeSnapshot>
}

export interface ToolProjection {
  tool_id: string
  version: string
  display_name: string
  description: string
}

export interface SkillProjection {
  skill_id: string
  version: string
  display_name: string
  description: string
}

export interface RuntimeSnapshot {
  session_id: string
  run_id: string
  context: ContextSnapshot
  tools: ToolProjection[]
  skills: SkillProjection[]
  run_status: RuntimeRunAcceptance["status"]
}

export interface RuntimeStartErrorProjection {
  status: 400 | 502
  code: "runtime_request_invalid" | "model_provider_unavailable" | "runtime_unavailable"
  message: string
}

export function projectRuntimeStartError(error: unknown): RuntimeStartErrorProjection {
  const candidate = error as { code?: unknown; details?: unknown; message?: unknown }
  const numericCode = Number(candidate?.code)
  const details = String(candidate?.details ?? candidate?.message ?? "")
  if ([3, 9].includes(numericCode)) {
    return {
      status: 400,
      code: "runtime_request_invalid",
      message: "Agent 请求参数无效，请刷新页面后重试"
    }
  }
  if (/modelprovidererror|model provider|bailian|deepseek/i.test(details)) {
    return {
      status: 502,
      code: "model_provider_unavailable",
      message: "模型服务暂不可用，请稍后重试"
    }
  }
  return {
    status: 502,
    code: "runtime_unavailable",
    message: "Agent Runtime 当前不可用，请稍后重试"
  }
}

export interface RuntimeGrpcTransport {
  StartTurn(request: object, callback: (error: grpc.ServiceError | null, response: unknown) => void): void
  StreamRunEvents(request: object): grpc.ClientReadableStream<unknown>
  GetRuntimeSnapshot(request: object, callback: (error: grpc.ServiceError | null, response: unknown) => void): void
}

interface GrpcStartTurnResponse {
  runId: string
  sessionId: string
  status: string | number
}

interface GrpcRuntimeSnapshot {
  sessionId: string
  runId: string
  context?: { selectedAssetId?: string; environment?: string; attributes?: Record<string, string> }
  tools?: Array<{
    toolId: string
    version: string
    displayName: string
    description: string
    inputSchema?: object
    outputSchema?: object
  }>
  skills?: Array<{ skillId: string; version: string; displayName: string; description: string }>
  runStatus: string | number
}

interface GrpcRuntimeEvent {
  eventId: string
  eventType: string | number
  sessionId: string
  runId: string
  sequence?: number | string
  occurredAt?: { seconds?: number | string; nanos?: number }
  payload?: unknown
}

const approvalStatusByControlStatus = {
  not_required: "APPROVAL_STATUS_NOT_REQUIRED",
  required: "APPROVAL_STATUS_REQUIRED",
  approved: "APPROVAL_STATUS_APPROVED",
  rejected: "APPROVAL_STATUS_REJECTED"
} as const

const controlRunStatusByGrpcStatus = {
  RUN_STATUS_ACCEPTED: "accepted",
  RUN_STATUS_RUNNING: "running",
  RUN_STATUS_WAITING: "waiting",
  RUN_STATUS_COMPLETED: "completed",
  RUN_STATUS_FAILED: "failed",
  RUN_STATUS_CANCELLED: "cancelled"
} as const

const controlRunStatusByGrpcNumber: Record<number, RuntimeRunAcceptance["status"]> = {
  1: "accepted",
  2: "running",
  3: "waiting",
  4: "completed",
  5: "failed",
  6: "cancelled"
}

export function toGrpcStartTurnRequest(request: RuntimeTurnRequest): object {
  return {
    sessionId: request.session_id,
    text: request.text,
    context: {
      selectedAssetId: request.context.selected_asset_id ?? "",
      environment: request.context.environment ?? "",
      attributes: request.context.attributes ?? {}
    },
    toolRefs: request.tool_refs.map((reference) => ({ toolId: reference.tool_id, version: reference.version })),
    skillRefs: request.skill_refs.map((reference) => ({ skillId: reference.skill_id, version: reference.version })),
    policy: {
      visibleToolIds: request.policy.visible_tool_ids,
      workflowStage: request.policy.workflow_stage ?? ""
    },
    approval: {
      status: approvalStatusByControlStatus[request.approval.status],
      approvalId: request.approval.approval_id ?? "",
      comment: request.approval.comment ?? ""
    }
  }
}

export function fromGrpcRuntimeSnapshot(response: GrpcRuntimeSnapshot): RuntimeSnapshot {
  return {
    session_id: response.sessionId,
    run_id: response.runId,
    context: {
      selected_asset_id: response.context?.selectedAssetId || undefined,
      environment: response.context?.environment as ContextSnapshot["environment"],
      attributes: response.context?.attributes ?? {}
    },
    tools: (response.tools ?? []).map((tool) => ({
      tool_id: tool.toolId,
      version: tool.version,
      display_name: tool.displayName,
      description: tool.description
    })),
    skills: (response.skills ?? []).map((skill) => ({
      skill_id: skill.skillId,
      version: skill.version,
      display_name: skill.displayName,
      description: skill.description
    })),
    run_status: fromGrpcRunStatus(response.runStatus)
  }
}

export function fromGrpcRuntimeEvent(response: GrpcRuntimeEvent): RuntimeEvent {
  return {
    event_id: response.eventId,
    event_type: fromGrpcEventType(response.eventType),
    session_id: response.sessionId,
    run_id: response.runId,
    sequence: Number(response.sequence ?? eventSequence(response.eventId)),
    occurred_at: timestampToIso(response.occurredAt),
    payload: structToObject(response.payload)
  }
}

class TestRuntimeClient implements RuntimeClient {
  async startTurn(request: RuntimeTurnRequest): Promise<RuntimeRunAcceptance> {
    return {
      run_id: `run_${randomUUID()}`,
      session_id: request.session_id,
      status: "running"
    }
  }

  async *streamRunEvents(runId: string, afterSequence = 0): AsyncIterable<RuntimeEvent> {
    const now = new Date().toISOString()
    const events: RuntimeEvent[] = [{
      event_id: `${runId}:1`,
      event_type: "run.accepted",
      session_id: "test-session",
      run_id: runId,
      sequence: 1,
      occurred_at: now,
      payload: { event_type: "RunStart" }
    }, {
      event_id: `${runId}:2`,
      event_type: "run.completed",
      session_id: "test-session",
      run_id: runId,
      sequence: 2,
      occurred_at: now,
      payload: { event_type: "RunStop", status: "completed" }
    }]
    for (const event of events) {
      if (event.sequence > afterSequence) yield event
    }
  }

  async getRuntimeSnapshot(sessionId: string, runId: string): Promise<RuntimeSnapshot> {
    return { session_id: sessionId, run_id: runId, context: {}, tools: [], skills: [], run_status: "running" }
  }
}

export class GrpcRuntimeClient implements RuntimeClient {
  private readonly client: RuntimeGrpcTransport
  private readonly sharedSecret: string

  constructor(
    target = process.env.AGENT_RUNTIME_GRPC_TARGET ?? "127.0.0.1:50051",
    transport?: RuntimeGrpcTransport,
  ) {
    this.sharedSecret = process.env.CONTROL_RUNTIME_SHARED_SECRET ?? ""
    if (transport) {
      this.client = transport
      return
    }
    const protoPath = process.env.AGENT_RUNTIME_PROTO_PATH
      ?? path.resolve(process.cwd(), "../../proto/agent_runtime/v1/runtime.proto")
    const definition = loadSync(protoPath, {
      keepCase: false,
      defaults: true,
      oneofs: true,
      enums: String
    })
    const loaded = grpc.loadPackageDefinition(definition)
    const service = (((loaded.agent_harness as grpc.GrpcObject).runtime as grpc.GrpcObject).v1 as grpc.GrpcObject).AgentRuntime
    const RuntimeClientConstructor = service as grpc.ServiceClientConstructor
    this.client = new RuntimeClientConstructor(target, grpc.credentials.createInsecure()) as unknown as RuntimeGrpcTransport
  }

  async startTurn(request: RuntimeTurnRequest): Promise<RuntimeRunAcceptance> {
    const response = await this.unaryCall<GrpcStartTurnResponse>("StartTurn", toGrpcStartTurnRequest(request))
    return {
      run_id: response.runId,
      session_id: response.sessionId,
      status: fromGrpcRunStatus(response.status)
    }
  }

  async getRuntimeSnapshot(sessionId: string, runId: string): Promise<RuntimeSnapshot> {
    const response = await this.unaryCall<GrpcRuntimeSnapshot>("GetRuntimeSnapshot", { sessionId, runId })
    return fromGrpcRuntimeSnapshot(response)
  }

  async *streamRunEvents(runId: string, afterSequence = 0): AsyncIterable<RuntimeEvent> {
    const stream = this.sharedSecret
      ? (this.client.StreamRunEvents as unknown as (
          request: object,
          metadata: grpc.Metadata
        ) => grpc.ClientReadableStream<unknown>)(
          { runId, afterSequence },
          this.metadata()
        )
      : this.client.StreamRunEvents({ runId, afterSequence })
    for await (const event of stream) {
      yield fromGrpcRuntimeEvent(event as GrpcRuntimeEvent)
    }
  }

  private unaryCall<T>(method: "StartTurn" | "GetRuntimeSnapshot", request: object): Promise<T> {
    return new Promise((resolve, reject) => {
      const callback: UnaryCallback = (error, response) => {
        if (error) {
          reject(error)
          return
        }
        resolve(response as T)
      }
      if (this.sharedSecret) {
        ;(this.client[method] as unknown as (
          request: object,
          metadata: grpc.Metadata,
          callback: UnaryCallback
        ) => void)(request, this.metadata(), callback)
      } else {
        this.client[method](request, callback)
      }
    })
  }

  private metadata(): grpc.Metadata {
    const metadata = new grpc.Metadata()
    metadata.set("authorization", `Bearer ${this.sharedSecret}`)
    return metadata
  }
}

function eventSequence(eventId: string): number {
  const candidate = Number(eventId.split(":").at(-1))
  return Number.isFinite(candidate) ? candidate : 0
}

type UnaryCallback = (
  error: grpc.ServiceError | null,
  response: unknown
) => void

export function createRuntimeClient(): RuntimeClient {
  return process.env.NODE_ENV === "test" ? new TestRuntimeClient() : new GrpcRuntimeClient()
}

const controlEventTypeByGrpcType = {
  RUNTIME_EVENT_TYPE_RUN_ACCEPTED: "run.accepted",
  RUNTIME_EVENT_TYPE_INTENT_RESOLVED: "intent.resolved",
  RUNTIME_EVENT_TYPE_PLAN_UPDATED: "plan.updated",
  RUNTIME_EVENT_TYPE_TOOL_SELECTED: "tool.selected",
  RUNTIME_EVENT_TYPE_TOOL_COMPLETED: "tool.completed",
  RUNTIME_EVENT_TYPE_EVIDENCE_UPDATED: "evidence.updated",
  RUNTIME_EVENT_TYPE_APPROVAL_REQUIRED: "approval.required",
  RUNTIME_EVENT_TYPE_RUN_COMPLETED: "run.completed",
  RUNTIME_EVENT_TYPE_RUN_FAILED: "run.failed"
} as const

const controlEventTypeByGrpcNumber: Record<number, RuntimeEvent["event_type"]> = {
  1: "run.accepted",
  2: "intent.resolved",
  3: "plan.updated",
  4: "tool.selected",
  5: "tool.completed",
  6: "evidence.updated",
  7: "approval.required",
  8: "run.completed",
  9: "run.failed"
}

function fromGrpcRunStatus(value: string | number): RuntimeRunAcceptance["status"] {
  if (typeof value === "number") return controlRunStatusByGrpcNumber[value] ?? "failed"
  return controlRunStatusByGrpcStatus[
    value as keyof typeof controlRunStatusByGrpcStatus
  ] ?? "failed"
}

function fromGrpcEventType(value: string | number): RuntimeEvent["event_type"] {
  if (typeof value === "number") return controlEventTypeByGrpcNumber[value] ?? "plan.updated"
  return controlEventTypeByGrpcType[
    value as keyof typeof controlEventTypeByGrpcType
  ] ?? "plan.updated"
}

function timestampToIso(timestamp?: { seconds?: number | string; nanos?: number }): string {
  const seconds = Number(timestamp?.seconds ?? 0)
  const nanos = Number(timestamp?.nanos ?? 0)
  const milliseconds = seconds * 1000 + Math.floor(nanos / 1_000_000)
  return new Date(milliseconds || Date.now()).toISOString()
}

function structToObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") return {}
  const candidate = value as { fields?: Record<string, unknown> }
  if (!candidate.fields) return value as Record<string, unknown>
  return Object.fromEntries(
    Object.entries(candidate.fields).map(([key, item]) => [key, protobufValue(item)])
  )
}

function protobufValue(value: unknown): unknown {
  if (!value || typeof value !== "object") return value
  const item = value as Record<string, unknown>
  if ("nullValue" in item) return null
  if ("stringValue" in item) return item.stringValue
  if ("numberValue" in item) return item.numberValue
  if ("boolValue" in item) return item.boolValue
  if ("structValue" in item) return structToObject(item.structValue)
  if ("listValue" in item) {
    const values = (item.listValue as { values?: unknown[] }).values ?? []
    return values.map(protobufValue)
  }
  return item
}
