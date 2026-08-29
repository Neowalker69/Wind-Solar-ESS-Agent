from datetime import datetime, timezone

from packages.harness_common.schemas.skill import SkillRecord, SkillStatus
from packages.skills.evaluator import evaluate, suspend_on_regression
from packages.skills.registry import SkillRegistry


class SkillLifecycleService:
    def __init__(
        self,
        registry: SkillRegistry | None = None,
        *,
        auto_promote_low_risk: bool = False,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.auto_promote_low_risk = auto_promote_low_risk

    def create_draft(self, skill: SkillRecord) -> SkillRecord:
        if skill.idempotency_key:
            existing = next(
                (
                    item
                    for item in self.registry.repo.list_all()
                    if item.idempotency_key == skill.idempotency_key
                ),
                None,
            )
            if existing is not None:
                return existing
        draft = skill.model_copy(update={"status": SkillStatus.DRAFT})
        return self.registry.save(draft)

    def evaluate(self, skill_id: str, version: str) -> SkillRecord:
        skill = self._require(skill_id, version)
        evaluated = evaluate(skill)
        saved = self.registry.save(evaluated)
        if (
            self.auto_promote_low_risk
            and saved.status is SkillStatus.CANDIDATE
            and saved.risk_level in {"L0", "L1"}
            and saved.test_result.get("passed") is True
        ):
            return self.activate_admin(skill_id, version)
        return saved

    def activate_admin(self, skill_id: str, version: str) -> SkillRecord:
        skill = self._require(skill_id, version)
        if skill.status != SkillStatus.CANDIDATE:
            raise ValueError("skill_not_candidate")
        if not skill.evaluation_result_id:
            raise ValueError("skill_evaluation_required")
        if skill.test_result.get("passed") is not True:
            raise ValueError("skill_tests_not_passed")
        if (
            skill.risk_level not in {"L0", "L1"}
            and skill.approval_status != "approved"
        ):
            raise ValueError("skill_approval_required")
        active_versions = [
            existing
            for existing in self.registry.active()
            if existing.skill_id == skill_id and existing.version != version
        ]
        for existing in active_versions:
            self.registry.save(
                existing.model_copy(update={"status": SkillStatus.SUPERSEDED})
            )
        previous = active_versions[-1] if active_versions else None
        return self.registry.save(
            skill.model_copy(
                update={
                    "status": SkillStatus.ACTIVE,
                    "base_version": skill.base_version
                    or (previous.version if previous else None),
                    "activated_at": datetime.now(timezone.utc),
                    "lifecycle_history": [
                        *skill.lifecycle_history,
                        self._audit("promoted", "admin", "tests_and_policy_passed"),
                    ],
                }
            )
        )

    def rollback(
        self,
        skill_id: str,
        *,
        from_version: str,
        target_version: str,
    ) -> SkillRecord:
        current = self._require(skill_id, from_version)
        target = self._require(skill_id, target_version)
        if current.status is not SkillStatus.ACTIVE:
            raise ValueError("skill_rollback_source_not_active")
        if not target.evaluation_result_id:
            raise ValueError("skill_evaluation_required")
        self.registry.save(
            current.model_copy(update={"status": SkillStatus.SUPERSEDED})
        )
        return self.registry.save(
            target.model_copy(
                update={
                    "status": SkillStatus.ACTIVE,
                    "activated_at": datetime.now(timezone.utc),
                    "lifecycle_history": [
                        *target.lifecycle_history,
                        self._audit(
                            "rollback",
                            "admin",
                            f"rollback_from:{from_version}",
                        ),
                    ],
                }
            )
        )

    def request_approval(self, skill_id: str, version: str) -> SkillRecord:
        skill = self._require(skill_id, version)
        approval_id = f"approval_{skill_id}_{version}"
        return self.registry.save(
            skill.model_copy(
                update={
                    "approval_request_id": approval_id,
                    "approval_status": "pending",
                    "lifecycle_history": [
                        *skill.lifecycle_history,
                        self._audit("approval_requested", "admin", approval_id),
                    ],
                }
            )
        )

    def decide_approval(
        self,
        skill_id: str,
        version: str,
        *,
        approved: bool,
        approver: str,
    ) -> SkillRecord:
        skill = self._require(skill_id, version)
        if not skill.approval_request_id or skill.approval_status != "pending":
            raise ValueError("skill_approval_not_pending")
        decision = "approved" if approved else "rejected"
        return self.registry.save(
            skill.model_copy(
                update={
                    "approval_status": decision,
                    "lifecycle_history": [
                        *skill.lifecycle_history,
                        self._audit(
                            f"approval_{decision}",
                            approver,
                            skill.approval_request_id,
                        ),
                    ],
                }
            )
        )

    def suspend_regression(self, skill_id: str, version: str) -> SkillRecord:
        skill = self._require(skill_id, version)
        return self.registry.save(suspend_on_regression(skill, True))

    def _require(self, skill_id: str, version: str) -> SkillRecord:
        skill = self.registry.get(skill_id, version)
        if skill is None:
            raise KeyError("skill_not_found")
        return skill

    @staticmethod
    def _audit(action: str, actor: str, reason: str) -> dict:
        return {
            "action": action,
            "actor": actor,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
