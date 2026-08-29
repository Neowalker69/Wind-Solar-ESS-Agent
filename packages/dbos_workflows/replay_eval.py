def submit_replay_eval(run_id: str, replay_mode: str, evaluation_profile: str, idempotency_key: str) -> dict:
    return {
        "workflow": "replay_eval",
        "idempotency_key": idempotency_key,
        "run_id": run_id,
        "replay_mode": replay_mode,
        "evaluation_profile": evaluation_profile,
        "status": "matched",
        "divergence": [],
    }
