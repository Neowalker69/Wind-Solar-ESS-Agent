ALTER TABLE observation_records
  ADD COLUMN IF NOT EXISTS record JSONB NOT NULL DEFAULT '{}';

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS control_projection JSONB NOT NULL DEFAULT '{}';

ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS control_projection JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS user_id TEXT,
  ADD COLUMN IF NOT EXISTS client_message_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS runs_session_client_message_idx
  ON runs (session_id, client_message_id)
  WHERE client_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS observation_records_run_id_observed_at_idx
  ON observation_records (run_id, observed_at);

CREATE INDEX IF NOT EXISTS trace_events_run_id_timestamp_idx
  ON trace_events (run_id, timestamp);
