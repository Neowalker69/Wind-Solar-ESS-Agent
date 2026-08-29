from dataclasses import dataclass
import os


@dataclass(frozen=True)
class IntentRouterConfig:
    embedding_model: str = os.getenv("INTENT_EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
    intent_lock_threshold: float = float(os.getenv("INTENT_LOCK_THRESHOLD", "0.86"))
    classifier_lock_threshold: float = float(os.getenv("CLASSIFIER_LOCK_THRESHOLD", "0.82"))
    qwen_fallback_model: str = os.getenv("QWEN_FALLBACK_MODEL", "qwen2.5-7b-instruct-q4")
