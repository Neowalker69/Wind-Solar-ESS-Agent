from packages.harness_common.schemas.skill import SkillRecord, SkillStatus
from packages.storage.repositories.skills import SkillRepository


class SkillRegistry:
    def __init__(self, repo: SkillRepository | None = None) -> None:
        self.repo = repo or SkillRepository()

    def save(self, skill: SkillRecord) -> SkillRecord:
        return self.repo.create(skill)

    def active(self) -> list[SkillRecord]:
        return [skill for skill in self.repo.list_all() if skill.status == SkillStatus.ACTIVE]

    def get(self, skill_id: str, version: str) -> SkillRecord | None:
        return self.repo.get_version(skill_id, version)
