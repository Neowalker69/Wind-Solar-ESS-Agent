from packages.harness_common.schemas.plugin import PluginInstallation
from packages.storage.repositories.base import InMemoryRepository


class PluginRepository(InMemoryRepository[PluginInstallation]):
    table_name = "plugin_installations"
    id_field = "compound_id"
    model_type = PluginInstallation

    def create(self, record: PluginInstallation) -> PluginInstallation:
        row_id = f"{record.plugin_id}:{record.version}"
        row = record.model_dump(mode="json")
        row["compound_id"] = row_id
        self.db.table(self.table_name)[row_id] = row
        return record

    def get_version(self, plugin_id: str, version: str) -> PluginInstallation | None:
        return self.get(f"{plugin_id}:{version}")
