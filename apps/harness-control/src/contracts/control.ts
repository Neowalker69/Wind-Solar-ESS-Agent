import { z } from "zod"

const identifierSchema = z.string().min(1).max(128)
const versionSchema = z.string().regex(/^\d+\.\d+\.\d+$/, "版本必须使用语义化格式")

export const contextSnapshotSchema = z.object({
  selected_asset_id: identifierSchema.optional(),
  environment: z.enum(["dev", "sandbox", "prod"]).optional(),
  attributes: z.record(z.string(), z.string()).optional()
}).strict()

export const toolReferenceSchema = z.object({
  tool_id: identifierSchema,
  version: versionSchema
}).strict()

export const skillReferenceSchema = z.object({
  skill_id: identifierSchema,
  version: versionSchema
}).strict()

export const policySnapshotSchema = z.object({
  visible_tool_ids: z.array(identifierSchema),
  workflow_stage: identifierSchema.optional()
}).strict()

export const approvalSnapshotSchema = z.object({
  status: z.enum(["not_required", "required", "approved", "rejected"]),
  approval_id: identifierSchema.optional(),
  comment: z.string().max(1000).optional()
}).strict().superRefine((value, context) => {
  if (["approved", "rejected"].includes(value.status) && !value.approval_id) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["approval_id"],
      message: "已决审批必须提供 approval_id"
    })
  }
})

export const createSessionInputSchema = z.object({
  user: z.object({
    user_id: identifierSchema,
    role: identifierSchema,
    site_id: identifierSchema.optional()
  }).strict(),
  context: contextSnapshotSchema
}).strict()

export const turnInputSchema = z.object({
  text: z.string().trim().min(1).max(8000),
  context: contextSnapshotSchema,
  tool_refs: z.array(toolReferenceSchema),
  skill_refs: z.array(skillReferenceSchema),
  policy: policySnapshotSchema,
  approval: approvalSnapshotSchema
}).strict()

export const runtimeEventSchema = z.object({
  event_id: identifierSchema,
  event_type: z.enum([
    "run.accepted",
    "intent.resolved",
    "plan.updated",
    "tool.selected",
    "tool.completed",
    "evidence.updated",
    "approval.required",
    "run.completed",
    "run.failed"
  ]),
  session_id: identifierSchema,
  run_id: identifierSchema,
  sequence: z.number().int().nonnegative(),
  occurred_at: z.string().datetime({ offset: true }),
  payload: z.record(z.string(), z.unknown())
}).strict()

export type ContextSnapshot = z.infer<typeof contextSnapshotSchema>
export type CreateSessionInput = z.infer<typeof createSessionInputSchema>
export type TurnInput = z.infer<typeof turnInputSchema>
export type RuntimeEvent = z.infer<typeof runtimeEventSchema>

export interface RuntimeTurnRequest {
  session_id: string
  text: string
  context: ContextSnapshot
  tool_refs: z.infer<typeof toolReferenceSchema>[]
  skill_refs: z.infer<typeof skillReferenceSchema>[]
  policy: z.infer<typeof policySnapshotSchema>
  approval: z.infer<typeof approvalSnapshotSchema>
}

export function toRuntimeTurnRequest(sessionId: string, input: TurnInput): RuntimeTurnRequest {
  return {
    session_id: identifierSchema.parse(sessionId),
    text: input.text,
    context: input.context,
    tool_refs: input.tool_refs,
    skill_refs: input.skill_refs,
    policy: input.policy,
    approval: input.approval
  }
}
