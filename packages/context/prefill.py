from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentContextPrefill:
    soul: str
    rules: str
    source_paths: dict[str, str]

    def system_prompt(self, task_instruction: str) -> str:
        sections = [
            "# Agent Identity",
            self.soul.strip(),
            "# Agent Work Rules",
            self.rules.strip(),
            "# Task Instruction",
            task_instruction.strip(),
        ]
        return "\n\n".join(section for section in sections if section)


def load_agent_context_prefill(root: Path | None = None) -> AgentContextPrefill:
    base = root or Path.cwd()
    soul_path = base / "SOUL.md"
    agents_path = base / "AGENTS.md"
    return AgentContextPrefill(
        soul=_read_optional(soul_path),
        rules=_read_optional(agents_path),
        source_paths={"soul": str(soul_path), "agents": str(agents_path)},
    )


def _read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
