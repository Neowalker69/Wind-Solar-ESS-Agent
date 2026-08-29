def submit_report_generation(run_id: str, report_type: str, evidence_ids: list[str], idempotency_key: str) -> dict:
    if not evidence_ids:
        return {
            "workflow": "report_generation",
            "idempotency_key": idempotency_key,
            "run_id": run_id,
            "report_type": report_type,
            "outcome_status": "blocked",
            "missing": ["evidence"],
            "report": None,
        }
    references = "\n".join(f"- `{evidence_id}`" for evidence_id in evidence_ids)
    return {
        "workflow": "report_generation",
        "idempotency_key": idempotency_key,
        "run_id": run_id,
        "report_type": report_type,
        "outcome_status": "completed",
        "missing": [],
        "report": {
            "format": "markdown",
            "body": f"# {report_type} 报告\n\n## 证据引用\n{references}",
            "evidence_ids": evidence_ids,
        },
    }
