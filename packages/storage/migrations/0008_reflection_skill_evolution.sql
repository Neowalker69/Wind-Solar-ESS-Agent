CREATE TABLE IF NOT EXISTS reflection_jobs (
  job_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  record JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS reflection_jobs_pending_idx
  ON reflection_jobs (status, updated_at);

CREATE TABLE IF NOT EXISTS learning_candidates (
  candidate_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  category TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  proposal_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  record JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS learning_candidates_job_idx
  ON learning_candidates (job_id, created_at);

CREATE INDEX IF NOT EXISTS learning_candidates_dedup_idx
  ON learning_candidates (proposal_hash, category);

ALTER TABLE skill_records
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS skill_records_idempotency_idx
  ON skill_records (idempotency_key)
  WHERE idempotency_key IS NOT NULL;
