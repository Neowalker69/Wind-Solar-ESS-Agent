from datetime import datetime, timezone

from packages.harness_common.schemas.approval import ApprovalRecord, ApprovalStatus
from packages.storage.repositories.approvals import ApprovalRepository


class ApprovalService:
    def __init__(self, repo: ApprovalRepository | None = None) -> None:
        self.repo = repo or ApprovalRepository()

    def request(self, approval: ApprovalRecord) -> ApprovalRecord:
        return self.repo.create(approval)

    def decide(self, approval_id: str, *, approved: bool, approver: str) -> ApprovalRecord:
        approval = self.repo.get(approval_id)
        if approval is None:
            raise KeyError("approval_not_found")
        decided = approval.model_copy(
            update={
                "status": ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
                "approver": approver,
                "decided_at": datetime.now(timezone.utc),
            }
        )
        return self.repo.create(decided)
