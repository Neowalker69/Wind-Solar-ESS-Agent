from packages.harness_common.schemas.run import RunRecord
from packages.storage.repositories.base import InMemoryRepository


class RunRepository(InMemoryRepository[RunRecord]):
    table_name = "runs"
    id_field = "run_id"
    model_type = RunRecord
