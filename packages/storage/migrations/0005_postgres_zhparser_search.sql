CREATE EXTENSION IF NOT EXISTS zhparser;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_ts_config
    WHERE cfgname = 'harness_zh'
      AND cfgnamespace = 'public'::regnamespace
  ) THEN
    CREATE TEXT SEARCH CONFIGURATION public.harness_zh (PARSER = zhparser);
    ALTER TEXT SEARCH CONFIGURATION public.harness_zh
      ADD MAPPING FOR n, v, a, i, e, l WITH simple;
  END IF;
END
$$;

CREATE OR REPLACE VIEW resource_search_documents AS
SELECT
  'run'::text AS resource_type,
  r.run_id AS resource_id,
  r.session_id,
  r.run_id,
  s.site_id,
  r.model_id,
  NULL::text AS tool_id,
  r.workflow_id,
  r.status,
  r.created_at AS occurred_at,
  concat_ws(
    ' ',
    r.run_id,
    r.task_type,
    r.model_id,
    r.workflow_id,
    r.status,
    r.record::text,
    r.control_projection::text
  ) AS content
FROM runs r
LEFT JOIN sessions s ON s.session_id = r.session_id
UNION ALL
SELECT
  'trace_event',
  COALESCE(t.record_id, t.event_id::text),
  t.session_id,
  t.run_id,
  s.site_id,
  COALESCE(t.record->>'model_id', r.model_id),
  COALESCE(t.record->>'tool_name', t.payload->>'tool_id'),
  r.workflow_id,
  COALESCE(t.record->>'status', t.payload->>'status', r.status),
  t.timestamp,
  concat_ws(' ', t.event_type, t.record::text, t.payload::text)
FROM trace_events t
LEFT JOIN runs r ON r.run_id = t.run_id
LEFT JOIN sessions s ON s.session_id = COALESCE(t.session_id, r.session_id)
UNION ALL
SELECT
  'observation',
  o.observation_id,
  r.session_id,
  o.run_id,
  s.site_id,
  o.model_name,
  o.tool_name,
  r.workflow_id,
  COALESCE(o.record->>'status', r.status),
  o.observed_at,
  concat_ws(' ', o.tool_name, o.plugin_id, o.record::text, o.payload::text)
FROM observation_records o
LEFT JOIN runs r ON r.run_id = o.run_id
LEFT JOIN sessions s ON s.session_id = r.session_id
UNION ALL
SELECT
  'evidence',
  e.evidence_id,
  r.session_id,
  e.run_id,
  s.site_id,
  r.model_id,
  e.record->>'tool_name',
  r.workflow_id,
  e.quality,
  e.recorded_at,
  concat_ws(' ', e.source_type, e.record::text, e.payload::text)
FROM evidence_records e
LEFT JOIN runs r ON r.run_id = e.run_id
LEFT JOIN sessions s ON s.session_id = r.session_id;
