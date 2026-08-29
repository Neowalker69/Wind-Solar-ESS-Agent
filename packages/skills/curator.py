from datetime import datetime, timedelta, timezone

from packages.harness_common.schemas.skill import SkillStatus
from packages.skills.registry import SkillRegistry


class SkillCurator:
    """离线精确去重和陈旧标记；不执行语义合并，也不进入在线链路。"""

    def __init__(self, registry: SkillRegistry, *, stale_days: int = 90) -> None:
        self.registry = registry
        self.stale_days = stale_days

    def run(self, *, now: datetime | None = None) -> dict[str, list]:
        current = now or datetime.now(timezone.utc)
        by_hash: dict[str, list[str]] = {}
        for skill in self.registry.repo.list_all():
            by_hash.setdefault(skill.package_hash, []).append(
                f"{skill.skill_id}:{skill.version}"
            )
        duplicate_groups = [
            sorted(versions) for versions in by_hash.values() if len(versions) > 1
        ]
        stale_versions: list[str] = []
        threshold = current - timedelta(days=self.stale_days)
        for skill in self.registry.repo.list_all():
            reference_time = skill.last_used_at or skill.activated_at or skill.created_at
            if (
                skill.status is SkillStatus.ACTIVE
                and skill.usage_count == 0
                and reference_time <= threshold
            ):
                stale = skill.model_copy(
                    update={
                        "status": SkillStatus.STALE,
                        "lifecycle_history": [
                            *skill.lifecycle_history,
                            {
                                "action": "marked_stale",
                                "actor": "skill_curator",
                                "reason": f"unused_for_{self.stale_days}_days",
                                "timestamp": current.isoformat(),
                            },
                        ],
                    }
                )
                self.registry.save(stale)
                stale_versions.append(f"{skill.skill_id}:{skill.version}")
        return {
            "duplicate_groups": duplicate_groups,
            "stale_versions": sorted(stale_versions),
        }
