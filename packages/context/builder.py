from dataclasses import dataclass
from typing import Any


CONTEXT_PRIORITY = [
    "safety",
    "run",
    "data_model",
    "evidence",
    "skills",
    "memory",
    "recent_session",
    "tools",
]


@dataclass(frozen=True)
class ContextSection:
    name: str
    payload: dict[str, Any]
    tokens: int


class ContextBuilder:
    def build(self, sections: list[ContextSection], *, token_budget: int) -> dict[str, Any]:
        selected: dict[str, Any] = {}
        used = 0
        by_name = {section.name: section for section in sections}
        for name in CONTEXT_PRIORITY:
            section = by_name.get(name)
            if section is None:
                continue
            if used + section.tokens > token_budget and name not in {"safety", "evidence", "tools"}:
                continue
            # safety/evidence/tools 是诊断闭环的硬约束，即使超出预算也保留；其他上下文按优先级裁剪。
            selected[name] = section.payload
            used += section.tokens
        return {"sections": selected, "tokens_used": used, "token_budget": token_budget}
