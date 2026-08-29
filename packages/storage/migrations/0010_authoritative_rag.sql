CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
  corpus_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  title TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  media_type TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  index_version TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (corpus_id, document_id),
  UNIQUE (corpus_id, source_path)
);

CREATE TABLE IF NOT EXISTS rag_chunks (
  chunk_id TEXT PRIMARY KEY,
  corpus_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  heading TEXT,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  source_ref TEXT NOT NULL,
  embedding vector(1024),
  embedding_provider TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_dimensions INTEGER NOT NULL DEFAULT 1024,
  index_version TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB NOT NULL DEFAULT '{}',
  content_tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('public.harness_zh'::regconfig, content)
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (corpus_id, document_id)
    REFERENCES rag_documents (corpus_id, document_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  UNIQUE (corpus_id, document_id, ordinal, index_version),
  CHECK (line_start >= 1),
  CHECK (line_end >= line_start),
  CHECK (embedding_dimensions = 1024)
);

CREATE TABLE IF NOT EXISTS rag_index_runs (
  run_id TEXT PRIMARY KEY,
  corpus_id TEXT NOT NULL,
  index_version TEXT NOT NULL,
  status TEXT NOT NULL,
  embedding_provider TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_dimensions INTEGER NOT NULL,
  document_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  excluded_document_count INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  metadata JSONB NOT NULL DEFAULT '{}',
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (corpus_id, index_version)
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_active_version
  ON rag_documents (corpus_id, active, status, version);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_active
  ON rag_chunks (corpus_id, document_id, active, ordinal);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_content_tsv
  ON rag_chunks USING GIN (content_tsv);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
  ON rag_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_rag_index_runs_latest
  ON rag_index_runs (corpus_id, status, completed_at DESC);
