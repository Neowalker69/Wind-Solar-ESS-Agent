from dataclasses import dataclass


@dataclass(frozen=True)
class RuleMatch:
    intent_id: str
    intent_label: str
    intent_family: str
    confidence: float
    terminal_action: bool = False
    safety_flags: tuple[str, ...] = ()
    rejection_reason: str | None = None


SYSTEM_RULES = {
    "/help": RuleMatch("system.help", "帮助", "system", 1.0, terminal_action=True),
    "/exit": RuleMatch("system.exit", "退出", "system", 1.0, terminal_action=True),
}

WRITE_KEYWORDS = ("写入", "修改参数", "下发", "启停", "停止", "启动", "确认报警", "acknowledge", "write", "set_parameter")


def match_rule(text: str) -> RuleMatch | None:
    normalized = text.strip()
    if not normalized:
        return RuleMatch("chat.noise", "空消息", "chat", 1.0, terminal_action=True)
    if normalized in SYSTEM_RULES:
        return SYSTEM_RULES[normalized]
    lowered = normalized.lower()
    if any(keyword in lowered or keyword in normalized for keyword in WRITE_KEYWORDS):
        return RuleMatch(
            "safety.violation",
            "安全违规",
            "safety",
            0.99,
            terminal_action=True,
            safety_flags=("ot_write_requested",),
            rejection_reason="P0 forbids OPC UA writes, method calls, and control actions.",
        )
    return None
