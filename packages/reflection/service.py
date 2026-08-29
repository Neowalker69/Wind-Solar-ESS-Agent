from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Protocol

from packages.events.bus import EventBus
from packages.harness_common.schemas.learning import (
    LearningCandidate,
    LearningCandidateStatus,
    LearningCategory,
    ReflectionJob,
    ReflectionJobStatus,
    ReflectionTrigger,
)
from packages.harness_common.schemas.memory import MemoryRecord, MemoryType
from packages.harness_common.schemas.evidence import EvidenceQuality
from packages.reflection.repositories import (
    LearningCandidateRepository,
    ReflectionJobRepository,
)
from packages.observability.metrics import GLOBAL_METRICS


class ReflectionClassifier(Protocol):
    def classify(self, **kwargs: Any) -> tuple[LearningCategory, dict[str, Any]]: ...


class RulesReflectionClassifier:
    """P0/P2 的确定性 L0 分类器，不向外部模型发送 Trace。"""

    def classify(
        self,
        *,
        job: ReflectionJob,
        trace_events: list[Any],
        evidence_ids: list[str],
    ) -> tuple[LearningCategory, dict[str, Any]]:
        payload = job.payload
        if job.trigger in {
            ReflectionTrigger.USER_CORRECTION,
            ReflectionTrigger.EXPLICIT_FEEDBACK,
        } and payload.get("correction"):
            return LearningCategory.FACT, {
                "content": str(payload["correction"]),
                "fact_key": str(
                    payload.get("fact_key")
                    or f"{job.project_id or job.run_id}.explicit_fact"
                ),
            }
        if job.trigger in {
            ReflectionTrigger.SKILL_USAGE_ANOMALY,
            ReflectionTrigger.REPEATED_FAILURE_THRESHOLD,
        } or int(payload.get("repeated_failure_count") or 0) >= 3:
            return LearningCategory.PROCEDURE, {
                "request": str(
                    payload.get("failed_step")
                    or payload.get("user_turn")
                    or "修正重复失败步骤"
                ),
                "skill_id": str(payload.get("skill_id") or "learned_procedure"),
                "base_version": payload.get("skill_version"),
            }
        if job.trigger is ReflectionTrigger.RUN_FAILED and payload.get("error"):
            return LearningCategory.EXPERIENCE, {
                "user_turn": str(payload.get("user_turn") or ""),
                "outcome": "failed",
                "error": str(payload["error"]),
                "workflow_stage": payload.get("workflow_stage"),
            }
        if evidence_ids and job.trigger in {
            ReflectionTrigger.RUN_COMPLETED,
            ReflectionTrigger.SESSION_END,
            ReflectionTrigger.SCHEDULED_BACKGROUND_REVIEW,
        }:
            finals = [
                event
                for event in trace_events
                if event.event_type == "assistant.completed"
            ]
            final = finals[-1] if finals else None
            return LearningCategory.EXPERIENCE, {
                "user_turn": str(payload.get("user_turn") or ""),
                "summary": str((final.payload if final else {}).get("content") or ""),
                "reasoning_summary": str(
                    (final.payload if final else {}).get("reasoning_summary") or ""
                ),
                "source_episode_count": len(finals),
                "episode_summaries": [
                    str(event.payload.get("content") or "") for event in finals
                ],
            }
        return LearningCategory.NO_LEARNING, {
            "reason": "insufficient_reusable_evidence"
        }


class ReflectionService:
    def __init__(
        self,
        *,
        jobs: ReflectionJobRepository,
        candidates: LearningCandidateRepository,
        traces: Any,
        memory_service: Any,
        skill_meta_tools: Any,
        event_bus: EventBus,
        classifier: ReflectionClassifier | None = None,
        evidence_repo: Any | None = None,
    ) -> None:
        self.jobs = jobs
        self.candidates = candidates
        self.traces = traces
        self.memory_service = memory_service
        self.skill_meta_tools = skill_meta_tools
        self.event_bus = event_bus
        self.classifier = classifier or RulesReflectionClassifier()
        self.evidence_repo = evidence_repo

    def enqueue(
        self,
        *,
        trigger: ReflectionTrigger,
        run_id: str,
        session_id: str | None,
        trace_ids: list[str],
        tenant_id: str,
        site_id: str | None,
        user_id: str | None,
        project_id: str | None,
        payload: dict[str, Any],
        idempotency_key: str,
        now: datetime | None = None,
    ) -> ReflectionJob:
        existing = self.jobs.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing
        created_at = now or datetime.now(timezone.utc)
        job = ReflectionJob(
            job_id="reflection_" + sha256(idempotency_key.encode()).hexdigest()[:24],
            trigger=trigger,
            trace_ids=trace_ids,
            run_id=run_id,
            session_id=session_id,
            tenant_id=tenant_id,
            site_id=site_id,
            user_id=user_id,
            project_id=project_id,
            payload=payload,
            idempotency_key=idempotency_key,
            created_at=created_at,
            updated_at=created_at,
        )
        created = self.jobs.upsert_by_idempotency_key(job)
        self.event_bus.publish(
            "reflection.jobs",
            {
                "event_type": "reflection.requested",
                "job_id": created.job_id,
                "run_id": run_id,
                "trace_id": trace_ids[0] if trace_ids else None,
                "tenant_id": tenant_id,
                "timestamp": created_at.isoformat(),
            },
        )
        GLOBAL_METRICS.inc(
            "reflection_jobs_enqueued_total",
            (created.trigger.value,),
        )
        return created

    def run_pending(
        self,
        *,
        now: datetime | None = None,
        limit: int = 20,
    ) -> list[str]:
        current = now or datetime.now(timezone.utc)
        pending = [
            job
            for job in self.jobs.list_all()
            if (
                job.status is ReflectionJobStatus.PENDING
                or (
                    job.status is ReflectionJobStatus.RETRY_SCHEDULED
                    and (job.next_attempt_at is None or job.next_attempt_at <= current)
                )
            )
        ]
        completed: list[str] = []
        for job in sorted(pending, key=lambda value: (value.created_at, value.job_id))[
            :limit
        ]:
            if self._process(job, current):
                completed.append(job.job_id)
        return completed

    def _process(self, job: ReflectionJob, now: datetime) -> bool:
        running = job.model_copy(
            update={
                "status": ReflectionJobStatus.RUNNING,
                "started_at": now,
                "updated_at": now,
                "error": None,
            }
        )
        self.jobs.create(running)
        try:
            selected_trace_ids = set(job.trace_ids)
            trace_events = [
                event
                for event in self.traces.list_all()
                if event.trace_id in selected_trace_ids
            ]
            evidence_ids = sorted(
                {
                    evidence_id
                    for event in trace_events
                    for evidence_id in event.evidence_ids
                }
            )
            category, proposal = self.classifier.classify(
                job=running,
                trace_events=trace_events,
                evidence_ids=evidence_ids,
            )
            candidate = self._candidate(
                running,
                category=category,
                proposal=proposal,
                evidence_ids=evidence_ids,
                now=now,
            )
            existing = next(
                (
                    value
                    for value in self.candidates.list_all()
                    if value.idempotency_key == candidate.idempotency_key
                    or (
                        value.proposal_hash == candidate.proposal_hash
                        and value.category == candidate.category
                        and value.tenant_id == candidate.tenant_id
                        and value.site_id == candidate.site_id
                        and value.user_id == candidate.user_id
                        and value.project_id == candidate.project_id
                        and value.asset_id == candidate.asset_id
                    )
                ),
                None,
            )
            candidate = existing or self.candidates.upsert_by_idempotency_key(candidate)
            if candidate.status is LearningCandidateStatus.CANDIDATE:
                candidate = self._materialize(candidate, running, evidence_ids, now)
            self.candidates.create(candidate)
            completed = running.model_copy(
                update={
                    "status": ReflectionJobStatus.COMPLETED,
                    "candidate_ids": [candidate.candidate_id],
                    "finished_at": now,
                    "updated_at": now,
                }
            )
            self.jobs.create(completed)
            self.event_bus.publish(
                "reflection.jobs",
                {
                    "event_type": "reflection.completed",
                    "job_id": job.job_id,
                    "candidate_id": candidate.candidate_id,
                    "category": candidate.category.value,
                    "run_id": job.run_id,
                    "timestamp": now.isoformat(),
                },
            )
            GLOBAL_METRICS.inc(
                "reflection_jobs_completed_total",
                (candidate.category.value,),
            )
            return True
        except Exception as exc:
            attempts = job.attempt_count + 1
            retryable = attempts < job.max_attempts
            failed = running.model_copy(
                update={
                    "status": (
                        ReflectionJobStatus.RETRY_SCHEDULED
                        if retryable
                        else ReflectionJobStatus.FAILED
                    ),
                    "attempt_count": attempts,
                    "next_attempt_at": (
                        now + timedelta(seconds=2**attempts) if retryable else None
                    ),
                    "finished_at": None if retryable else now,
                    "updated_at": now,
                    "error": {
                        "code": "reflection_processing_failed",
                        "message": str(exc)[:300],
                        "retryable": retryable,
                    },
                }
            )
            self.jobs.create(failed)
            self.event_bus.publish(
                "reflection.jobs",
                {
                    "event_type": "reflection.retry_scheduled"
                    if retryable
                    else "reflection.failed",
                    "job_id": job.job_id,
                    "run_id": job.run_id,
                    "attempt_count": attempts,
                    "retryable": retryable,
                    "timestamp": now.isoformat(),
                },
            )
            GLOBAL_METRICS.inc(
                "reflection_jobs_retry_total" if retryable else "reflection_jobs_failed_total"
            )
            return False

    def review_candidate(
        self,
        candidate_id: str,
        *,
        approved: bool,
        reviewed_by: str,
        reason: str,
        now: datetime | None = None,
    ) -> LearningCandidate:
        candidate = self.candidates.get(candidate_id)
        if candidate is None:
            raise KeyError("learning_candidate_not_found")
        reviewed_at = now or datetime.now(timezone.utc)
        reviewed = candidate.model_copy(
            update={
                "status": (
                    LearningCandidateStatus.APPROVED
                    if approved
                    else LearningCandidateStatus.REJECTED
                ),
                "review": {
                    "approved": approved,
                    "reviewed_by": reviewed_by,
                    "reason": reason,
                    "reviewed_at": reviewed_at.isoformat(),
                },
                "updated_at": reviewed_at,
            }
        )
        self.candidates.create(reviewed)
        self.event_bus.publish(
            "reflection.jobs",
            {
                "event_type": (
                    "reflection.candidate_approved"
                    if approved
                    else "reflection.candidate_rejected"
                ),
                "candidate_id": candidate_id,
                "job_id": candidate.job_id,
                "reviewed_by": reviewed_by,
                "timestamp": reviewed_at.isoformat(),
            },
        )
        GLOBAL_METRICS.inc(
            "reflection_candidate_reviews_total",
            ("approved" if approved else "rejected",),
        )
        return reviewed

    def _candidate(
        self,
        job: ReflectionJob,
        *,
        category: LearningCategory,
        proposal: dict[str, Any],
        evidence_ids: list[str],
        now: datetime,
    ) -> LearningCandidate:
        proposal_hash = sha256(
            json.dumps(proposal, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        candidate_key = f"{job.idempotency_key}:{category.value}:{proposal_hash}"
        risk_level = "L2" if category is LearningCategory.PROCEDURE else "L0"
        evidence_score = self._evidence_score(evidence_ids)
        confidence = (
            evidence_score
            if evidence_score is not None
            else (0.9 if category is LearningCategory.FACT else 0.75)
        )
        conflicts_with = self._memory_conflicts(job, category, proposal)
        return LearningCandidate(
            candidate_id="learning_" + sha256(candidate_key.encode()).hexdigest()[:24],
            job_id=job.job_id,
            trace_id=job.trace_ids[0] if job.trace_ids else f"run:{job.run_id}",
            run_id=job.run_id,
            category=category,
            proposal=proposal,
            proposal_hash=proposal_hash,
            confidence=confidence,
            importance=0.8 if category is not LearningCategory.NO_LEARNING else 0.0,
            repeat_count=int(job.payload.get("repeated_failure_count") or 1),
            evidence_count=len(evidence_ids),
            impact_scope="project" if job.project_id else "user",
            risk_level=risk_level,
            contradiction_score=1.0 if conflicts_with else 0.0,
            conflicts_with=conflicts_with,
            tenant_id=job.tenant_id,
            site_id=job.site_id,
            user_id=job.user_id,
            project_id=job.project_id,
            asset_id=job.payload.get("asset_id"),
            source_refs=[f"trace:{value}" for value in job.trace_ids],
            idempotency_key=candidate_key,
            created_at=now,
            updated_at=now,
        )

    def _evidence_score(self, evidence_ids: list[str]) -> float | None:
        if self.evidence_repo is None or not evidence_ids:
            return None
        weights = {
            EvidenceQuality.GOOD: 1.0,
            EvidenceQuality.UNCERTAIN: 0.5,
            EvidenceQuality.BAD: 0.0,
        }
        records = [self.evidence_repo.get(value) for value in evidence_ids]
        scores = [weights[record.quality] for record in records if record is not None]
        return round(sum(scores) / len(scores), 4) if scores else None

    def _memory_conflicts(
        self,
        job: ReflectionJob,
        category: LearningCategory,
        proposal: dict[str, Any],
    ) -> list[str]:
        if category is not LearningCategory.FACT or not proposal.get("fact_key"):
            return []
        conflicts: list[str] = []
        for memory in self.memory_service.repo.list_all():
            if (
                memory.status.value == "active"
                and memory.memory_type is MemoryType.SEMANTIC
                and memory.tenant_id == job.tenant_id
                and memory.site_id == job.site_id
                and memory.user_id == job.user_id
                and memory.project_id == job.project_id
                and memory.asset_id == job.payload.get("asset_id")
                and memory.metadata.get("fact_key") == proposal.get("fact_key")
                and memory.content.get("summary") != proposal.get("content")
            ):
                conflicts.append(f"memory:{memory.memory_id}")
        return sorted(conflicts)

    def _materialize(
        self,
        candidate: LearningCandidate,
        job: ReflectionJob,
        evidence_ids: list[str],
        now: datetime,
    ) -> LearningCandidate:
        if candidate.category is LearningCategory.NO_LEARNING:
            return candidate.model_copy(
                update={
                    "status": LearningCandidateStatus.REJECTED,
                    "updated_at": now,
                }
            )
        if candidate.category in {
            LearningCategory.FACT,
            LearningCategory.EXPERIENCE,
        }:
            memory_type = (
                MemoryType.SEMANTIC
                if candidate.category is LearningCategory.FACT
                else (
                    MemoryType.LESSON
                    if job.trigger is ReflectionTrigger.SCHEDULED_BACKGROUND_REVIEW
                    and len(job.trace_ids) > 1
                    else MemoryType.EPISODIC
                )
            )
            content = (
                {"summary": candidate.proposal.get("content")}
                if candidate.category is LearningCategory.FACT
                else candidate.proposal
            )
            memory = self.memory_service.create_candidate(
                MemoryRecord(
                    memory_id=f"memory_{candidate.candidate_id}",
                    memory_type=memory_type,
                    version="1",
                    content=content,
                    source_trace_ids=job.trace_ids,
                    # 显式用户纠正本身就是可审计的一手来源；使用稳定引用保留其来源，
                    # 不伪造工业事实 Evidence。
                    evidence_ids=(
                        evidence_ids
                        or (
                            [f"feedback:{candidate.trace_id}"]
                            if job.trigger
                            in {
                                ReflectionTrigger.USER_CORRECTION,
                                ReflectionTrigger.EXPLICIT_FEEDBACK,
                            }
                            else []
                        )
                    ),
                    tenant_id=job.tenant_id,
                    site_id=job.site_id,
                    user_id=job.user_id,
                    project_id=job.project_id,
                    asset_id=job.payload.get("asset_id"),
                    source_ref=f"learning:{candidate.candidate_id}",
                    confidence=candidate.confidence,
                    importance=candidate.importance,
                    risk_level=candidate.risk_level,
                    idempotency_key=f"memory:{candidate.idempotency_key}",
                    metadata={
                        "learning_candidate_id": candidate.candidate_id,
                        "fact_key": candidate.proposal.get("fact_key"),
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            return candidate.model_copy(
                update={
                    "status": LearningCandidateStatus.MATERIALIZED,
                    "materialized_ref": f"memory:{memory.memory_id}",
                    "updated_at": now,
                }
            )
        skill_id = str(candidate.proposal.get("skill_id") or "learned_procedure")
        next_version = self._next_skill_version(skill_id)
        draft = self.skill_meta_tools.skill_create_from_request(
            str(candidate.proposal.get("request") or job.payload.get("user_turn") or ""),
            skill_id=skill_id,
            version=next_version,
            source_trace_id=candidate.trace_id,
            source_candidate_id=candidate.candidate_id,
            base_version=candidate.proposal.get("base_version"),
            risk_level=candidate.risk_level,
            tenant_id=job.tenant_id,
            project_id=job.project_id,
        )
        evaluated = self.skill_meta_tools.skill_evaluate(draft.skill_id, draft.version)
        return candidate.model_copy(
            update={
                "status": LearningCandidateStatus.MATERIALIZED,
                "materialized_ref": f"skill:{evaluated.skill_id}:{evaluated.version}",
                "updated_at": now,
            }
        )

    def _next_skill_version(self, skill_id: str) -> str:
        versions = [
            skill.version
            for skill in self.skill_meta_tools.service.registry.repo.list_all()
            if skill.skill_id == skill_id
        ]
        if not versions:
            return "0.1.0"
        major, minor, patch = max(
            (tuple(int(part) for part in value.split(".")) for value in versions)
        )
        return f"{major}.{minor}.{patch + 1}"
