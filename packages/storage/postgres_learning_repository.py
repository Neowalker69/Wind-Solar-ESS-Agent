from typing import Any

from psycopg.types.json import Jsonb

from packages.harness_common.schemas.learning import LearningCandidate, ReflectionJob
from packages.storage.postgres_connection import ConnectionFactory
from packages.storage.postgres_repository import PostgresRepository


class PostgresReflectionJobRepository(PostgresRepository[ReflectionJob]):
    table_name = "reflection_jobs"
    id_field = "job_id"
    id_columns = ("job_id",)
    idempotency_column = "idempotency_key"
    model_type = ReflectionJob
    order_column = "created_at"

    def _persistence_values(self, record: ReflectionJob, row_id: str) -> dict[str, Any]:
        return {
            "job_id": row_id,
            "run_id": record.run_id,
            "status": str(record.status),
            "trigger": str(record.trigger),
            "idempotency_key": record.idempotency_key,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "record": Jsonb(record.model_dump(mode="json")),
        }


class PostgresLearningCandidateRepository(PostgresRepository[LearningCandidate]):
    table_name = "learning_candidates"
    id_field = "candidate_id"
    id_columns = ("candidate_id",)
    idempotency_column = "idempotency_key"
    model_type = LearningCandidate
    order_column = "created_at"

    def _persistence_values(
        self,
        record: LearningCandidate,
        row_id: str,
    ) -> dict[str, Any]:
        return {
            "candidate_id": row_id,
            "job_id": record.job_id,
            "run_id": record.run_id,
            "category": str(record.category),
            "status": str(record.status),
            "idempotency_key": record.idempotency_key,
            "proposal_hash": record.proposal_hash,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "record": Jsonb(record.model_dump(mode="json")),
        }
