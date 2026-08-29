def structured_log(component: str, message: str, trace_id: str, run_id: str | None = None) -> dict:
    return {"component": component, "message": message, "trace_id": trace_id, "run_id": run_id}
