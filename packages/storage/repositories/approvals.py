from packages.harness_common.schemas.approval import ApprovalRecord
from packages.storage.repositories.base import InMemoryRepository


class ApprovalRepository(InMemoryRepository[ApprovalRecord]):
    table_name = "approval_records"
    id_field = "approval_id"
    model_type = ApprovalRecord
