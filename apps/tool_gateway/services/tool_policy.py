from packages.harness_common.schemas.plugin import ToolDefinition


FORBIDDEN_TOOL_TOKENS = ("write", "call_method", "acknowledge_alarm", "start", "stop", "set_parameter")


def is_tool_allowed(tool: ToolDefinition) -> bool:
    lowered = tool.name.lower()
    # 工具网关是 OT/OPC UA 的最后一道只读边界：即使 manifest 误标 read_only，也要按名称拦截常见写入/启停/确认告警动作。
    if any(token in lowered for token in FORBIDDEN_TOOL_TOKENS):
        return False
    return tool.read_only and tool.risk_level in {"L0", "L1"}


def assert_tool_allowed(tool: ToolDefinition) -> None:
    if not is_tool_allowed(tool):
        raise ValueError("tool_policy_rejected")
