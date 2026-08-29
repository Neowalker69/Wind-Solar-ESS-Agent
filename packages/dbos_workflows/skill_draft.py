def submit_skill_draft(source_trace_ids: list[str], evaluation_case_ids: list[str], idempotency_key: str) -> dict:
    return {
        "workflow": "skill_draft",
        "idempotency_key": idempotency_key,
        "skill_package": {
            "SKILL.md": "# Draft Skill\n",
            "skill.yaml": {"status": "draft", "source_trace_ids": source_trace_ids},
            "tests": evaluation_case_ids,
        },
    }
