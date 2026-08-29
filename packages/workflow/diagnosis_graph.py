from packages.harness_common.schemas.evidence import EvidenceRecord
from packages.workflow.grounding import evaluate_diagnosis_evidence, render_grounded_summary
from packages.workflow.output_reducer import reduce_final_answer

NODES = ["INTAKE", "CONTEXT_RESOLVE", "CAPABILITY_RESOLVE", "PLAN", "COLLECT_EVIDENCE", "ANALYZE", "FINALIZE"]


def run_diagnosis_graph(run_id: str, evidence: list[EvidenceRecord]) -> dict:
    trace = [{"run_id": run_id, "node_name": node, "status": "ok"} for node in NODES]
    if not evidence:
        return {
            "run_id": run_id,
            "status": "insufficient_evidence",
            "trace": trace,
            "final": {
                "conclusion": None,
                "evidence_ids": [],
                "missing": ["evidence"],
            },
        }
    evaluation = evaluate_diagnosis_evidence(run_id, evidence)
    if not evaluation["evidence_ids"]:
        return {"run_id": run_id, "status": "insufficient_evidence", "trace": trace, "final": {"conclusion": None, "evidence_ids": [], "missing": ["valid_evidence", "diagnostic_facts"], "grounding": evaluation}}
    if evaluation["conflicts"]:
        return {"run_id": run_id, "status": "conflicting_evidence", "trace": trace, "final": {"conclusion": None, "evidence_ids": evaluation["evidence_ids"], "missing": ["conflict_resolution"], "grounding": evaluation}}
    final = reduce_final_answer(render_grounded_summary(evaluation["facts"]), evaluation["evidence_ids"], 1.0)
    final["grounding"] = evaluation
    return {"run_id": run_id, "status": "completed", "trace": trace, "final": final}
