CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  parent_run_id TEXT,
  task_type TEXT NOT NULL,
  status TEXT NOT NULL,
  workflow_id TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  graph_runtime TEXT NOT NULL,
  graph_checkpoint_ref TEXT,
  workflow_run_ids JSONB NOT NULL DEFAULT '[]',
  workflow_runtime TEXT,
  workflow_adapter_type TEXT,
  model_id TEXT NOT NULL,
  model_version TEXT NOT NULL,
  plugin_version_snapshot JSONB NOT NULL DEFAULT '{}',
  skill_version_snapshot JSONB NOT NULL DEFAULT '{}',
  data_model_version TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error JSONB
);

CREATE TABLE IF NOT EXISTS intent_decisions (
  intent_decision_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS routing_decisions (
  route_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trace_events (
  event_id BIGSERIAL PRIMARY KEY,
  trace_id TEXT NOT NULL,
  run_id TEXT,
  session_id TEXT,
  event_type TEXT NOT NULL,
  idempotency_key TEXT,
  wal_record_id TEXT,
  observation_id TEXT,
  payload JSONB NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_records (
  evidence_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  quality TEXT NOT NULL,
  payload JSONB NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observation_records (
  observation_id TEXT PRIMARY KEY,
  run_id TEXT,
  trace_id TEXT,
  task_id TEXT,
  model_name TEXT,
  tool_name TEXT NOT NULL,
  plugin_id TEXT NOT NULL,
  plugin_version TEXT NOT NULL,
  raw_snapshot_ref TEXT NOT NULL,
  payload JSONB NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wal_records (
  wal_record_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  source TEXT NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  parent_request_id TEXT,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_records (
  approval_id TEXT PRIMARY KEY,
  run_id TEXT,
  trace_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS skill_records (
  skill_id TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (skill_id, version)
);

CREATE TABLE IF NOT EXISTS plugin_installations (
  plugin_id TEXT NOT NULL,
  version TEXT NOT NULL,
  runtime_status TEXT NOT NULL,
  idempotency_key TEXT UNIQUE,
  payload JSONB NOT NULL,
  installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (plugin_id, version)
);
