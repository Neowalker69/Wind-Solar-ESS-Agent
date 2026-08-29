ALTER TABLE memory_records
  ADD COLUMN IF NOT EXISTS project_id TEXT,
  ADD COLUMN IF NOT EXISTS agent_id TEXT,
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS authority DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  ADD COLUMN IF NOT EXISTS risk_level TEXT NOT NULL DEFAULT 'L0',
  ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS supersedes_memory_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_records_idempotency_key
  ON memory_records (tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_records_recall_scope
  ON memory_records (
    tenant_id, project_id, site_id, user_id, asset_id, status, valid_to
  );
