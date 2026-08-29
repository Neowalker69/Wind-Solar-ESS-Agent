def submit_sop_ingest(source_uri: str, source_hash: str, idempotency_key: str) -> dict:
    return {
        "workflow": "sop_ingest",
        "idempotency_key": idempotency_key,
        "source_uri": source_uri,
        "source_hash": source_hash,
        "chunks": [{"chunk_id": "chunk_1", "text": "normalized SOP"}],
    }
