from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AssetIdentity(BaseModel):
    asset_uid: str
    asset_id: str
    asset_type: str
    site_id: str
    opcua_server_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeMapping(BaseModel):
    mapping_id: str
    asset_uid: str
    signal_name: str
    node_id: str
    data_type: str
    unit: str | None = None
    required_for_status: bool = False


class DataModelVersion(BaseModel):
    data_model_id: str
    version: str
    assets: list[AssetIdentity] = Field(default_factory=list)
    node_mappings: list[NodeMapping] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
