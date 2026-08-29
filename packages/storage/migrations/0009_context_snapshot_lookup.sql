CREATE INDEX IF NOT EXISTS trace_events_context_snapshot_idx
  ON trace_events ((payload->>'snapshot_id'), timestamp DESC)
  WHERE event_type = 'context.compiled';
