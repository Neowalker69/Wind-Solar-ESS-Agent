from packages.workflow.langgraph_runtime import LangGraphRuntime


_runtime = LangGraphRuntime()


def invoke(state: dict) -> dict:
    return _runtime.invoke(state)
