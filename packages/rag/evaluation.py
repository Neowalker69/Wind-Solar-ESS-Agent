from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from packages.rag.models import RagSearchHit


class RagEvalCase(BaseModel):
    query_id: str
    query: str
    relevant_document_ids: list[str] = Field(default_factory=list)
    expected_exact_terms: list[str] = Field(default_factory=list)


class RagEvaluationReport(BaseModel):
    k: int
    case_count: int
    recall_at_k: float
    mrr: float
    superseded_false_recall_rate: float
    numeric_unit_fault_accuracy: float
    chunk_citation_coverage: float


def load_eval_cases(path: Path) -> list[RagEvalCase]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return [RagEvalCase.model_validate(item) for item in value.get("cases", [])]


def evaluate_retrieval(
    cases: list[RagEvalCase],
    results: dict[str, list[RagSearchHit]],
    *,
    k: int,
) -> RagEvaluationReport:
    if not cases:
        return RagEvaluationReport(
            k=k,
            case_count=0,
            recall_at_k=0.0,
            mrr=0.0,
            superseded_false_recall_rate=0.0,
            numeric_unit_fault_accuracy=0.0,
            chunk_citation_coverage=0.0,
        )
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    exact_matches = 0
    exact_total = 0
    all_hits: list[RagSearchHit] = []
    for case in cases:
        hits = list(results.get(case.query_id, []))[: max(1, k)]
        all_hits.extend(hits)
        relevant = set(case.relevant_document_ids)
        retrieved = [hit.document_id for hit in hits]
        recalls.append(
            len(relevant.intersection(retrieved)) / len(relevant) if relevant else 0.0
        )
        first_rank = next(
            (index for index, document_id in enumerate(retrieved, start=1) if document_id in relevant),
            None,
        )
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        combined = "\n".join(hit.text for hit in hits).casefold()
        for term in case.expected_exact_terms:
            exact_total += 1
            exact_matches += int(term.casefold() in combined)
    total_hits = len(all_hits)
    superseded_hits = sum(hit.status == "superseded" for hit in all_hits)
    cited_hits = sum(
        bool(hit.citation.get("chunk_id") and hit.citation.get("source_ref"))
        for hit in all_hits
    )
    return RagEvaluationReport(
        k=k,
        case_count=len(cases),
        recall_at_k=sum(recalls) / len(recalls),
        mrr=sum(reciprocal_ranks) / len(reciprocal_ranks),
        superseded_false_recall_rate=(superseded_hits / total_hits if total_hits else 0.0),
        numeric_unit_fault_accuracy=(exact_matches / exact_total if exact_total else 0.0),
        chunk_citation_coverage=(cited_hits / total_hits if total_hits else 0.0),
    )
