from packages.harness_common.schemas.learning import LearningCandidate, ReflectionJob
from packages.storage.repositories.base import InMemoryRepository


class ReflectionJobRepository(InMemoryRepository[ReflectionJob]):
    table_name = "reflection_jobs"
    id_field = "job_id"
    model_type = ReflectionJob


class LearningCandidateRepository(InMemoryRepository[LearningCandidate]):
    table_name = "learning_candidates"
    id_field = "candidate_id"
    model_type = LearningCandidate
