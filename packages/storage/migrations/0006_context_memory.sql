ALTER TABLE memory_records
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'tenant_lab',
  ADD COLUMN IF NOT EXISTS site_id TEXT,
  ADD COLUMN IF NOT EXISTS user_id TEXT,
  ADD COLUMN IF NOT EXISTS asset_id TEXT,
  ADD COLUMN IF NOT EXISTS source_ref TEXT,
  ADD COLUMN IF NOT EXISTS summary TEXT,
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS content_hash TEXT,
  ADD COLUMN IF NOT EXISTS importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  ADD COLUMN IF NOT EXISTS model_visible BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS tool_visible BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS content_text TEXT NOT NULL DEFAULT '';

ALTER TABLE memory_records
  ADD COLUMN IF NOT EXISTS content_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('public.harness_zh'::regconfig, content_text)
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_memory_records_scope_status
  ON memory_records (tenant_id, site_id, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_memory_records_content_tsv
  ON memory_records USING GIN (content_tsv);
CREATE INDEX IF NOT EXISTS idx_memory_records_content_hash
  ON memory_records (tenant_id, site_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_memory_records_embedding
  ON memory_records USING hnsw (embedding vector_cosine_ops);
