from packages.workflow.guardrails import require_evidence


def reduce_final_answer(summary: str, evidence_ids: list[str], confidence: float) -> dict:
    answer = {"summary": summary, "evidence_ids": evidence_ids, "confidence": confidence}
    require_evidence(answer)
    return answer
