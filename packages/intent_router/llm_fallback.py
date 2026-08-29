from packages.harness_common.schemas.intent import IntentDecision, RouterPath, SubIntent


class StructuredFallback:
    def classify(self, *, base: IntentDecision, text: str) -> IntentDecision:
        sub_intents: list[SubIntent] = []
        if "报告" in text:
            sub_intents.append(SubIntent(intent_id="report.generate", confidence=0.82, normalized_user_turn=text))
        if "工单" in text:
            sub_intents.append(SubIntent(intent_id="workorder.draft", confidence=0.82, normalized_user_turn=text))
        if "查" in text or "查询" in text or "状态" in text:
            sub_intents.insert(0, SubIntent(intent_id="data.query", confidence=0.86, normalized_user_turn=text))
        primary = sub_intents[0].intent_id if sub_intents else "diagnosis.alarm"
        family = primary.split(".", 1)[0]
        return base.model_copy(
            update={
                "intent_id": primary,
                "intent_label": "LLM结构化兜底",
                "intent_family": family,
                "confidence": 0.76,
                "router_path": RouterPath.LLM_FALLBACK,
                "is_composite": len(sub_intents) > 1,
                "sub_intents": sub_intents,
            }
        )
