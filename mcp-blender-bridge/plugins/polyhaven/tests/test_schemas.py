import pytest
from pydantic import ValidationError
from mcp_blender_bridge_polyhaven.schemas import (
    PolyHavenStatusParams,
    PolyHavenCategoriesParams,
    PolyHavenSearchParams,
    PolyHavenDownloadParams,
    PolyHavenApplyTextureParams,
)

def test_status_params_forbids_extra():
    with pytest.raises(ValidationError):
        PolyHavenStatusParams(extra_field="invalid")

def test_categories_params():
    # Valid
    assert PolyHavenCategoriesParams(type="textures").type == "textures"
    assert PolyHavenCategoriesParams(type="hdris").type == "hdris"
    
    # Invalid type
    with pytest.raises(ValidationError):
        PolyHavenCategoriesParams(type="invalid")
    
    with pytest.raises(ValidationError):
        PolyHavenCategoriesParams(type="invalid_type")

def test_search_params():
    params = PolyHavenSearchParams(type="textures", search="wood")
    assert params.type == "textures"
    assert params.search == "wood"
    
    # forbid extra
    with pytest.raises(ValidationError):
        PolyHavenSearchParams(type="textures", extra="invalid")

def test_download_params():
    params = PolyHavenDownloadParams(asset_id="wood_planks", type="textures")
    assert params.asset_id == "wood_planks"
    
    # Default resolution
    assert params.resolution == "4k"

def test_apply_texture_params():
    params = PolyHavenApplyTextureParams(object_name="Cube", asset_id="wood_planks")
    assert params.object_name == "Cube"
    assert params.asset_id == "wood_planks"
    assert params.resolution == "4k"
