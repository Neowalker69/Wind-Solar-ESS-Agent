from hashlib import sha256
from uuid import uuid4

from packages.harness_common.schemas.intent import IntentDecision, RouterPath
from packages.intent_router.cache import IntentCache
from packages.intent_router.classifier import DeterministicClassifier
from packages.intent_router.config import IntentRouterConfig
from packages.intent_router.llm_fallback import StructuredFallback
from packages.intent_router.rules import match_rule
from packages.intent_router.semantic_routes import SemanticRouter


def user_turn_hash(text: str) -> str:
    return sha256(text.strip().encode("utf-8")).hexdigest()


def cache_key(text: str) -> str:
    return f"intent:{user_turn_hash(text)}"


class IntentRouter:
    def __init__(
        self,
        *,
        config: IntentRouterConfig | None = None,
        cache: IntentCache | None = None,
        semantic_router: SemanticRouter | None = None,
        classifier: DeterministicClassifier | None = None,
        fallback: StructuredFallback | None = None,
    ) -> None:
        self.config = config or IntentRouterConfig()
        self.cache = cache or IntentCache()
        self.semantic_router = semantic_router or SemanticRouter()
        self.classifier = classifier or DeterministicClassifier()
        self.fallback = fallback or StructuredFallback()

    def classify(self, text: str, *, session_id: str, trace_id: str) -> IntentDecision:
        normalized = text.strip()
        key = cache_key(normalized)
        cached = self.cache.get(key)
        if cached is not None:
            # 缓存命中后改写 router_path，便于观测层区分“复用旧判断”和“重新分类”的成本与风险。
            return cached.model_copy(update={"router_path": RouterPath.CACHE})

        base = IntentDecision(
            intent_decision_id=f"intent_{uuid4().hex}",
            session_id=session_id,
            trace_id=trace_id,
            user_turn_hash=user_turn_hash(normalized),
            intent_id="unknown",
            intent_label="未知",
            intent_family="unknown",
            confidence=0.0,
            router_path=RouterPath.LLM_FALLBACK,
            normalized_user_turn=normalized,
            cache_key=key,
        )

        rule = match_rule(normalized)
        if rule is not None:
            # 安全/拒绝类规则优先于语义召回和分类器，确保高风险意图不会被后续模型路径稀释。
            decision = base.model_copy(
                update={
                    "intent_id": rule.intent_id,
                    "intent_label": rule.intent_label,
                    "intent_family": rule.intent_family,
                    "confidence": rule.confidence,
                    "router_path": RouterPath.RULE,
                    "safety_flags": list(rule.safety_flags),
                    "rejection_reason": rule.rejection_reason,
                }
            )
            self.cache.set(key, decision)
            return decision

        if self._looks_composite(normalized):
            # 复合意图需要结构化拆解，直接走 fallback，避免单标签路由误锁定到其中一个子任务。
            decision = self.fallback.classify(base=base, text=normalized)
            self.cache.set(key, decision)
            return decision

        semantic = self.semantic_router.route(normalized)
        if semantic is not None and semantic.similarity_score >= self.config.intent_lock_threshold:
            decision = base.model_copy(
                update={
                    "intent_id": semantic.intent_id,
                    "intent_label": semantic.intent_label,
                    "intent_family": semantic.intent_family,
                    "confidence": semantic.similarity_score,
                    "router_path": RouterPath.SEMANTIC_ROUTER,
                    "matched_examples": semantic.matched_examples,
                }
            )
            self.cache.set(key, decision)
            return decision

        classified = self.classifier.classify(normalized)
        if classified.confidence >= self.config.classifier_lock_threshold:
            family = classified.label.split(".", 1)[0]
            decision = base.model_copy(
                update={
                    "intent_id": classified.label,
                    "intent_label": classified.label,
                    "intent_family": family,
                    "confidence": classified.confidence,
                    "router_path": RouterPath.CLASSIFIER,
                    "safety_flags": classified.safety_flags,
                }
            )
            self.cache.set(key, decision)
            return decision

        decision = self.fallback.classify(base=base, text=normalized)
        self.cache.set(key, decision)
        return decision

    @staticmethod
    def _looks_composite(text: str) -> bool:
        has_joiner = "并" in text or "然后" in text or "同时" in text
        intents = sum(1 for keyword in ("查询", "查", "状态", "报告", "工单", "技能", "回放") if keyword in text)
        return has_joiner and intents >= 2
