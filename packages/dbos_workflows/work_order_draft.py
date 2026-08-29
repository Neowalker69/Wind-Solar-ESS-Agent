def submit_work_order_draft(run_id: str, evidence_ids: list[str], idempotency_key: str, *, asset_id: str = "unknown") -> dict:
    missing = []
    if not evidence_ids:
        missing.append("evidence")
    if asset_id == "unknown":
        missing.append("asset")
    tasks = (
        [
            {
                "title": f"核查 {asset_id} 的已引用诊断事实",
                "evidence_ids": evidence_ids,
                "execution": "manual",
            }
        ]
        if not missing
        else []
    )
    return {
        "workflow": "work_order_draft",
        "idempotency_key": idempotency_key,
        "run_id": run_id,
        "outcome_status": "blocked" if missing else "completed",
        "missing": missing,
        "draft": {
            "asset": asset_id,
            "priority": "normal",
            "tasks": tasks,
            "safety_notes": ["执行前由现场人员复核证据与设备状态"],
            "evidence_ids": evidence_ids,
        },
    }
