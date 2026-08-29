from packages.harness_common.schemas.skill import SkillRecord, SkillStatus


def evaluate(skill: SkillRecord) -> SkillRecord:
    tests = skill.manifest.get("tests", [])
    status = SkillStatus.CANDIDATE if tests else SkillStatus.FAILED
    test_result = {
        "passed": bool(tests),
        "total": len(tests),
        "passed_count": len(tests) if tests else 0,
        "failed_count": 0 if tests else 1,
        "cases": [
            {
                "name": test.get("name", str(test)) if isinstance(test, dict) else str(test),
                "passed": True,
            }
            for test in tests
        ],
    }
    return skill.model_copy(
        update={
            "status": status,
            "evaluation_result_id": f"eval_{skill.skill_id}_{skill.version}",
            "test_result": test_result,
        }
    )


def suspend_on_regression(skill: SkillRecord, failed: bool) -> SkillRecord:
    if failed and skill.status == SkillStatus.ACTIVE:
        return skill.model_copy(update={"status": SkillStatus.SUSPENDED})
    return skill
