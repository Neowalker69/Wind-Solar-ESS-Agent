import { z } from "zod"


export const toolResultStatusSchema = z.enum(["success", "no_data", "partial", "failed"])
export const dataQualitySchema = z.enum(["good", "uncertain", "bad", "missing"])

export const resourceSearchHitSchema = z.object({
  resource_type: z.string(),
  resource_id: z.string(),
  session_id: z.string().nullable(),
  run_id: z.string().nullable(),
  snippet: z.string(),
  occurred_at: z.string().datetime({ offset: true }),
  score: z.number(),
}).strict()

const auditRunSchema = z.object({
  run_id: z.string(),
  session_id: z.string(),
  status: z.string(),
  workflow_id: z.string(),
  model_id: z.string(),
}).passthrough()

const auditToolCallSchema = z.object({
  observation_id: z.string(),
  tool_id: z.string(),
  tool_version: z.string(),
  status: toolResultStatusSchema,
  quality: dataQualitySchema,
  result: z.record(z.string(), z.unknown()),
  evidence_id: z.string().nullable(),
  occurred_at: z.string().datetime({ offset: true }),
}).strict()

const auditTimelineItemSchema = z.object({
  kind: z.enum(["intent", "model", "tool", "evidence", "workflow", "final"]),
  name: z.string(),
  status: z.string(),
  occurred_at: z.string().datetime({ offset: true }).nullable(),
  ref_id: z.string(),
}).strict()

export const runAuditSchema = z.object({
  run: auditRunSchema,
  intent: z.record(z.string(), z.unknown()).nullable(),
  model_calls: z.array(z.object({
    stage: z.string().nullable(),
    provider: z.string().nullable(),
  }).passthrough()),
  tool_calls: z.array(auditToolCallSchema),
  observations: z.array(z.record(z.string(), z.unknown())),
  evidence: z.array(z.record(z.string(), z.unknown())),
  workflows: z.array(z.record(z.string(), z.unknown())),
  final: z.object({
    content: z.string(),
    reasoning_summary: z.string(),
    evidence_ids: z.array(z.string()),
    occurred_at: z.string().datetime({ offset: true }),
  }).passthrough().nullable(),
  timeline: z.array(auditTimelineItemSchema),
}).strict()

export const evidenceDetailSchema = z.object({
  evidence_id: z.string(),
  run_id: z.string(),
  trace_id: z.string(),
  source_type: z.string(),
  source_ref: z.string(),
  quality: z.string(),
  data: z.record(z.string(), z.unknown()),
  recorded_at: z.string().datetime({ offset: true }),
  snapshot: z.unknown().nullable(),
  content_hash: z.string().nullable(),
  fact_time: z.string().nullable(),
  observed_at: z.string(),
  query_window: z.unknown().nullable(),
  aggregation: z.unknown().nullable(),
  source_locator: z.object({
    source_system: z.string().nullable(),
    source_resource_type: z.string().nullable(),
    source_ref: z.string(),
    upstream_trace_id: z.string().nullable(),
  }).strict(),
}).passthrough()

export type ResourceSearchHit = z.infer<typeof resourceSearchHitSchema>
export type RunAudit = z.infer<typeof runAuditSchema>
export type EvidenceDetail = z.infer<typeof evidenceDetailSchema>
