from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class PolyHavenStatusParams(StrictModel):
    pass

class PolyHavenCategoriesParams(StrictModel):
    type: Literal["hdris", "textures", "models"] = Field(
        description="The type of assets to get categories for."
    )

class PolyHavenSearchParams(StrictModel):
    type: Optional[Literal["hdris", "textures", "models"]] = Field(
        None, description="Filter by asset type."
    )
    category: Optional[str] = Field(
        None, description="Filter by a specific category (e.g., 'wood')."
    )
    search: Optional[str] = Field(
        None, description="Search query string."
    )

class PolyHavenDownloadParams(StrictModel):
    asset_id: str = Field(description="The ID of the asset to download.")
    type: Literal["hdris", "textures", "models"] = Field(
        description="The type of the asset."
    )
    resolution: Literal["1k", "2k", "4k", "8k"] = Field(
        "4k", description="The resolution to download."
    )

class PolyHavenApplyTextureParams(StrictModel):
    object_name: str = Field(
        description="The name of the Blender object to apply the texture to."
    )
    asset_id: str = Field(
        description="The ID of the downloaded texture asset."
    )
    resolution: Literal["1k", "2k", "4k", "8k"] = Field(
        "4k", description="The resolution of the downloaded texture."
    )
