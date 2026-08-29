from packages.harness_common.schemas.data_model import AssetIdentity, DataModelVersion, NodeMapping


class DataModelRegistry:
    def __init__(self) -> None:
        self._versions: dict[str, DataModelVersion] = {}
        self._active_version_by_site: dict[str, str] = {}

    def register(self, model: DataModelVersion) -> DataModelVersion:
        key = self._key(model.data_model_id, model.version)
        self._versions[key] = model
        for asset in model.assets:
            self._active_version_by_site.setdefault(asset.site_id, key)
        return model

    def activate(self, data_model_id: str, version: str, *, site_id: str) -> DataModelVersion:
        key = self._key(data_model_id, version)
        if key not in self._versions:
            raise KeyError("data_model_not_found")
        self._active_version_by_site[site_id] = key
        return self._versions[key]

    def active_for_site(self, site_id: str) -> DataModelVersion | None:
        key = self._active_version_by_site.get(site_id)
        return self._versions.get(key) if key else None

    def resolve_asset(self, *, site_id: str, asset_id: str) -> AssetIdentity:
        model = self.active_for_site(site_id)
        if model is None:
            raise KeyError("data_model_not_found")
        for asset in model.assets:
            if asset.site_id == site_id and asset.asset_id == asset_id:
                return asset
        raise KeyError("asset_not_found")

    def node_for_signal(self, *, site_id: str, asset_id: str, signal_name: str) -> NodeMapping:
        model = self.active_for_site(site_id)
        if model is None:
            raise KeyError("data_model_not_found")
        asset = self.resolve_asset(site_id=site_id, asset_id=asset_id)
        for mapping in model.node_mappings:
            if mapping.asset_uid == asset.asset_uid and mapping.signal_name == signal_name:
                return mapping
        raise KeyError("node_mapping_not_found")

    @staticmethod
    def _key(data_model_id: str, version: str) -> str:
        return f"{data_model_id}:{version}"


def default_lab_model() -> DataModelVersion:
    asset = AssetIdentity(
        asset_uid="asset_pcs_07",
        asset_id="PCS_07",
        asset_type="pcs",
        site_id="opcua_lab",
        opcua_server_id="lab_server",
    )
    return DataModelVersion(
        data_model_id="opcua_lab_model",
        version="0.1.0",
        assets=[asset],
        node_mappings=[
            NodeMapping(
                mapping_id="map_pcs_07_status",
                asset_uid=asset.asset_uid,
                signal_name="status",
                node_id="ns=2;s=PCS_07.Status",
                data_type="String",
                required_for_status=True,
            )
        ],
    )
