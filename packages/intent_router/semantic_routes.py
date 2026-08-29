from dataclasses import dataclass
from math import sqrt
from typing import Callable, Protocol, Sequence, Any


@dataclass(frozen=True)
class SemanticRouteResult:
    intent_id: str
    intent_label: str
    intent_family: str
    similarity_score: float
    matched_examples: list[dict[str, str | float]]


@dataclass(frozen=True)
class SemanticRouteExample:
    text: str
    intent_id: str
    intent_label: str
    intent_family: str


SEMANTIC_KEYWORDS = {
    "sop.search": (
        "SOP 查询",
        "sop",
        (
            "怎么处置",
            "处置流程",
            "应急步骤",
            "应急处置",
            "操作规程",
            "故障码说明",
        ),
    ),
    "data.query": ("数据查询", "data", ("查询", "状态", "遥测", "读取", "温度", "电压", "pcs")),
    "diagnosis.alarm": ("告警诊断", "diagnosis", ("诊断", "告警", "异常", "原因", "报警")),
    "report.generate": ("生成报告", "report", ("生成", "报告", "总结")),
    "workorder.draft": ("工单草稿", "workorder", ("工单", "维修任务", "草稿")),
    "skill.create": ("创建技能", "skill", ("技能", "skill", "经验")),
    "sop.ingest": ("SOP 导入", "sop", ("sop", "规程", "导入")),
    "memory.search": ("会话记忆", "memory", ("历史会话", "会话", "记忆")),
    "messaging.draft": ("消息草稿", "messaging", ("消息", "通知", "草稿", "澄清")),
    "task.status": ("任务状态", "task", ("任务", "待办", "状态")),
    "replay.eval": ("回放评测", "replay", ("回放", "replay", "评测")),
}


class EmbeddingEncoder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]:
        ...


class SentenceTransformerEmbeddingEncoder:
    def __init__(
        self,
        model_path_or_name: str,
        *,
        loader: Callable[[], Any] | None = None,
        normalize_embeddings: bool = True,
    ) -> None:
        self.model_path_or_name = model_path_or_name
        self.loader = loader
        self.normalize_embeddings = normalize_embeddings
        self._model: Any | None = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=False,
        )
        return [_vector_to_floats(vector) for vector in vectors]

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            self._model = self.loader() if self.loader else self._load_sentence_transformer()
        except ImportError as exc:
            raise RuntimeError(
                "sentence_transformers_not_installed: install sentence-transformers "
                "before enabling LocalEmbeddingSemanticRouter"
            ) from exc
        return self._model

    def _load_sentence_transformer(self) -> Any:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_path_or_name)


class LocalEmbeddingSemanticRouter:
    def __init__(
        self,
        *,
        encoder: EmbeddingEncoder,
        examples: Sequence[SemanticRouteExample] | None = None,
        min_similarity: float = 0.0,
    ) -> None:
        self.encoder = encoder
        self.examples = list(examples or default_semantic_route_examples())
        self.min_similarity = min_similarity
        self._example_vectors = self.encoder.encode([example.text for example in self.examples])
        if len(self._example_vectors) != len(self.examples):
            raise ValueError("embedding_example_count_mismatch")

    def route(self, text: str) -> SemanticRouteResult | None:
        normalized = text.strip()
        if not normalized or not self.examples:
            return None
        query_vectors = self.encoder.encode([normalized])
        if len(query_vectors) != 1:
            raise ValueError("embedding_query_count_mismatch")
        query_vector = query_vectors[0]
        best_index = -1
        best_score = 0.0
        for index, example_vector in enumerate(self._example_vectors):
            score = _cosine_similarity(query_vector, example_vector)
            if score > best_score:
                best_index = index
                best_score = score
        if best_index < 0 or best_score <= 0.0 or best_score < self.min_similarity:
            return None
        example = self.examples[best_index]
        rounded_score = round(best_score, 6)
        return SemanticRouteResult(
            intent_id=example.intent_id,
            intent_label=example.intent_label,
            intent_family=example.intent_family,
            similarity_score=rounded_score,
            matched_examples=[{"text": example.text, "score": rounded_score}],
        )


def default_semantic_route_examples() -> list[SemanticRouteExample]:
    examples: list[SemanticRouteExample] = []
    for intent_id, (label, family, keywords) in SEMANTIC_KEYWORDS.items():
        for keyword in keywords:
            examples.append(
                SemanticRouteExample(
                    text=str(keyword),
                    intent_id=intent_id,
                    intent_label=label,
                    intent_family=family,
                )
            )
    return examples


class SemanticRouter:
    """Deterministic semantic-router facade.

    P0 tests use keyword scoring so the contract is stable without model downloads.
    Use LocalEmbeddingSemanticRouter when a local embedding model is configured.
    """

    def route(self, text: str) -> SemanticRouteResult | None:
        lowered = text.lower()
        best: tuple[str, str, str, float, str] | None = None
        for intent_id, (label, family, keywords) in SEMANTIC_KEYWORDS.items():
            hits = [keyword for keyword in keywords if keyword in lowered or keyword in text]
            if not hits:
                continue
            # 单个明确领域词应达到默认锁定阈值，避免回退到无关的默认诊断意图。
            score = min(0.96, 0.80 + 0.06 * len(hits))
            if best is None or score > best[3]:
                best = (intent_id, label, family, score, hits[0])
        if best is None:
            return None
        intent_id, label, family, score, example = best
        return SemanticRouteResult(
            intent_id=intent_id,
            intent_label=label,
            intent_family=family,
            similarity_score=score,
            matched_examples=[{"text": example, "score": score}],
        )


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _vector_to_floats(vector: Any) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(value) for value in vector]
