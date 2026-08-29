class AgentIterationLimit(Exception):
    pass


class LocalAgentLoop:
    def __init__(self, max_iterations: int = 8) -> None:
        self.max_iterations = max_iterations

    def run(self, steps: list[str]) -> list[str]:
        if len(steps) > self.max_iterations:
            raise AgentIterationLimit("agent_iteration_limit")
        return [f"observed:{step}" for step in steps]
