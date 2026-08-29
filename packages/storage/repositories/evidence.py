from packages.harness_common.schemas.evidence import EvidenceRecord
from packages.storage.repositories.base import InMemoryRepository


class EvidenceRepository(InMemoryRepository[EvidenceRecord]):
    table_name = "evidence_records"
    id_field = "evidence_id"
    model_type = EvidenceRecord
