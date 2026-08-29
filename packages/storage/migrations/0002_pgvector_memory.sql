CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_records (
  memory_id TEXT PRIMARY KEY,
  memory_type TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  source_trace_ids JSONB NOT NULL DEFAULT '[]',
  evidence_ids JSONB NOT NULL DEFAULT '[]',
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  embedding vector(1024),
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ
);
