def workflow_id(name: str, idempotency_key: str) -> str:
    return f"dbos_{name}_{idempotency_key}"
