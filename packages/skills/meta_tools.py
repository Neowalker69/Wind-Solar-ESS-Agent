from hashlib import sha256

from packages.harness_common.schemas.skill import SkillRecord, SkillStatus
from packages.skills.lifecycle_service import SkillLifecycleService


class SkillMetaTools:
    def __init__(self, service: SkillLifecycleService | None = None) -> None:
        self.service = service or SkillLifecycleService()

    def skill_search(self, query: str) -> list[dict]:
        return [
            {"skill_id": skill.skill_id, "version": skill.version, "status": skill.status, "score": 1.0, "reason": query, "provenance": skill.source_trace_ids}
            for skill in self.service.registry.active()
        ]

    def skill_view(self, skill_id: str, version: str) -> SkillRecord:
        return self.service._require(skill_id, version)

    def skill_create(self, payload: dict) -> SkillRecord:
        skill = SkillRecord(**payload)
        return self.service.create_draft(skill)

    def skill_create_from_request(
        self,
        request: str,
        *,
        skill_id: str,
        version: str,
        source_trace_id: str,
        source_candidate_id: str | None = None,
        base_version: str | None = None,
        risk_level: str = "L0",
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> SkillRecord:
        normalized = request.strip()
        if not normalized:
            raise ValueError("skill_request_required")
        return self.skill_create(
            {
                "skill_id": skill_id,
                "version": version,
                "manifest": {
                    "name": skill_id,
                    "description": normalized,
                    "metadata": {
                        "scope": project_id or "tenant",
                        "owner": "agent-harness",
                        "risk_level": risk_level,
                        "version": version,
                    },
                    "trigger": {
                        "intent": "procedure.learned",
                        "conditions": [normalized],
                    },
                    "inputs": ["asset_id"],
                    "instructions": normalized,
                    "steps": [
                        {
                            "type": "agent_instruction",
                            "instruction": normalized,
                        }
                    ],
                    "tools": [],
                    "references": [f"trace:{source_trace_id}"],
                    "scripts": [],
                    "templates": [],
                    "tests": [
                        {
                            "name": "request_contract",
                            "input": {"asset_id": "fixture-asset"},
                            "expected": "produces_grounded_result",
                        }
                    ],
                    "provenance": {
                        "trace_ids": [source_trace_id],
                        "learning_candidate_ids": (
                            [source_candidate_id] if source_candidate_id else []
                        ),
                    },
                },
                "package_hash": "sha256:"
                + sha256(normalized.encode("utf-8")).hexdigest(),
                "source_trace_ids": [source_trace_id],
                "source_candidate_ids": (
                    [source_candidate_id] if source_candidate_id else []
                ),
                "base_version": base_version,
                "risk_level": risk_level,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "idempotency_key": (
                    f"skill:{source_candidate_id}" if source_candidate_id else None
                ),
            }
        )

    def skill_update(self, skill_id: str, version: str, patch: dict) -> SkillRecord:
        base = self.skill_view(skill_id, version)
        changes = dict(patch)
        next_version = changes.pop("version")
        if self._semver(next_version) <= self._semver(version):
            raise ValueError("skill_version_must_increase")
        updated = base.model_copy(
            update={
                **changes,
                "version": next_version,
                "base_version": version,
                "status": SkillStatus.DRAFT,
                "evaluation_result_id": None,
                "approval_request_id": None,
                "approval_status": None,
                "test_result": {},
                "activated_at": None,
                "idempotency_key": f"skill-patch:{skill_id}:{version}:{next_version}",
            }
        )
        return self.service.create_draft(updated)

    def skill_evaluate(self, skill_id: str, version: str) -> SkillRecord:
        return self.service.evaluate(skill_id, version)

    def skill_propose_activation(self, skill_id: str, version: str) -> dict:
        skill = self.service.request_approval(skill_id, version)
        return {
            "approval_request_id": skill.approval_request_id,
            "status": skill.status,
        }

    def skill_suspend(self, skill_id: str, version: str) -> SkillRecord:
        return self.service.suspend_regression(skill_id, version)

    def skill_approve_activation(
        self,
        skill_id: str,
        version: str,
        *,
        approved: bool,
        approver: str,
    ) -> SkillRecord:
        return self.service.decide_approval(
            skill_id,
            version,
            approved=approved,
            approver=approver,
        )

    def skill_rollback(self, skill_id: str, version: str) -> SkillRecord:
        active = next(
            (
                skill
                for skill in self.service.registry.active()
                if skill.skill_id == skill_id
            ),
            None,
        )
        if active is None:
            raise ValueError("skill_rollback_source_not_active")
        return self.service.rollback(
            skill_id,
            from_version=active.version,
            target_version=version,
        )

    @staticmethod
    def _semver(version: str) -> tuple[int, int, int]:
        try:
            values = tuple(int(part) for part in version.split("."))
        except ValueError as exc:
            raise ValueError("skill_version_invalid") from exc
        if len(values) != 3:
            raise ValueError("skill_version_invalid")
        return values
