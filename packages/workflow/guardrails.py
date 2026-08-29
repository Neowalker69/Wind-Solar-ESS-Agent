FORBIDDEN_ACTION_WORDS = ("write", "call_method", "start", "stop", "set_parameter", "写入", "启动", "停止")


def reject_ot_write_action(action: str) -> None:
    lowered = action.lower()
    # 防护词同时覆盖英文工具名和中文用户意图，避免自然语言计划绕过只读 OT 集成约束。
    if any(word in lowered or word in action for word in FORBIDDEN_ACTION_WORDS):
        raise ValueError("ot_write_forbidden")


def require_evidence(final_answer: dict) -> None:
    # 诊断结论必须可追溯到证据；没有 evidence_ids 时宁可失败，也不能产出不可审计的最终答案。
    if not final_answer.get("evidence_ids"):
        raise ValueError("required_evidence_missing")
