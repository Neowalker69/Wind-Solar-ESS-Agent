from packages.harness_common.schemas.observation import ObservationRecord
from packages.storage.repositories.base import InMemoryRepository


class ObservationRepository(InMemoryRepository[ObservationRecord]):
    table_name = "observation_records"
    id_field = "observation_id"
    model_type = ObservationRecord
