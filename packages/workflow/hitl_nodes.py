def wait_for_human(run_id: str, reason: str) -> dict:
    return {"run_id": run_id, "status": "waiting", "reason": reason}


def resume_from_human(run_id: str, approved: bool) -> dict:
    return {"run_id": run_id, "status": "resumed", "approved": approved}
