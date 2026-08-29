from packages.harness_common.schemas.skill import SkillRecord
from packages.storage.repositories.base import InMemoryRepository


class SkillRepository(InMemoryRepository[SkillRecord]):
    table_name = "skill_records"
    id_field = "compound_id"
    model_type = SkillRecord

    def create(self, record: SkillRecord) -> SkillRecord:
        row_id = f"{record.skill_id}:{record.version}"
        row = record.model_dump(mode="json")
        row["compound_id"] = row_id
        self.db.table(self.table_name)[row_id] = row
        return record

    def get_version(self, skill_id: str, version: str) -> SkillRecord | None:
        return self.get(f"{skill_id}:{version}")
