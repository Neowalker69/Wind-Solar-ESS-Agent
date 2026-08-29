from packages.harness_common.schemas.evidence import EvidenceQuality, EvidenceRecord


class RequiredEvidenceMissing(Exception):
    pass


def supporting_evidence_ids(records: list[EvidenceRecord], *, required: bool = True) -> list[str]:
    good_ids = [record.evidence_id for record in records if record.quality == EvidenceQuality.GOOD]
    # BAD/UNCERTAIN 证据可用于排查过程，但不能支撑最终结论；required=True 的路径必须显式阻断无证据输出。
    if required and not good_ids:
        raise RequiredEvidenceMissing("required_evidence_missing")
    return good_ids


def validate_requested_evidence_ids(records: list[EvidenceRecord], requested_ids: list[str]) -> list[str]:
    by_id = {record.evidence_id: record for record in records}
    for evidence_id in requested_ids:
        record = by_id.get(evidence_id)
        if record is None:
            raise RequiredEvidenceMissing("evidence_not_found_or_wrong_run")
        if record.quality != EvidenceQuality.GOOD:
            raise RequiredEvidenceMissing("evidence_quality_not_supported")
    return requested_ids


def quality_summary(records: list[EvidenceRecord]) -> dict:
    return {
        "total": len(records),
        "good": sum(1 for record in records if record.quality == EvidenceQuality.GOOD),
        "bad": sum(1 for record in records if record.quality == EvidenceQuality.BAD),
        "uncertain": sum(1 for record in records if record.quality == EvidenceQuality.UNCERTAIN),
    }
