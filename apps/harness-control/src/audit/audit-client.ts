import { z } from "zod"

import { resolveStationApiToken } from "../workspace/station-api"
import {
  evidenceDetailSchema,
  resourceSearchHitSchema,
  runAuditSchema,
  type EvidenceDetail,
  type ResourceSearchHit,
  type RunAudit,
} from "./audit-contracts"


interface HarnessEnvelope {
  data?: unknown
  error?: { code?: string; message?: string } | null
}

async function fetchHarness<T>(
  path: string,
  schema: z.ZodType<T>,
): Promise<T> {
  const token = await resolveStationApiToken()
  const response = await fetch(path, {
    credentials: "include",
    headers: { Authorization: `Bearer ${token}` },
  })
  const envelope = await response.json() as HarnessEnvelope
  if (!response.ok) {
    throw new Error(
      envelope.error?.message ?? `harness_audit_http_${response.status}`,
    )
  }
  return schema.parse(envelope.data)
}

export async function searchAuditResources(
  filters: Record<string, string | undefined>,
): Promise<ResourceSearchHit[]> {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) search.set(key, value)
  }
  const data = await fetchHarness(
    `/api/v1/resources/search?${search}`,
    z.object({ hits: z.array(resourceSearchHitSchema) }).strict(),
  )
  return data.hits
}

export function fetchRunAudit(runId: string): Promise<RunAudit> {
  return fetchHarness(
    `/api/v1/runs/${encodeURIComponent(runId)}/audit`,
    runAuditSchema,
  )
}

export function fetchEvidenceDetail(
  evidenceId: string,
): Promise<EvidenceDetail> {
  return fetchHarness(
    `/api/v1/evidence/${encodeURIComponent(evidenceId)}`,
    evidenceDetailSchema,
  )
}
