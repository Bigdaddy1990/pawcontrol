from types import MappingProxyType

import pytest

from custom_components.pawcontrol.config_flow_dashboard_extension import (
    DashboardFlowMixin,
    _build_dashboard_configure_placeholders,
    _translated_dashboard_info_line,
)


class _DashboardFlowHarness(DashboardFlowMixin):
    def __init__(self, dog_count: int) -> None:
        self._dogs = [{} for _ in range(dog_count)]
        self._enabled_modules = {}

    async def async_step_configure_external_entities(self) -> dict[str, str]:
        return {"step_id": "configure_external_entities"}

    async def async_step_final_setup(self) -> dict[str, str]:
        return {"step_id": "final_setup"}


@pytest.mark.unit
def test_build_dashboard_configure_placeholders_returns_mapping_proxy() -> None:
    """Dashboard placeholders should remain immutable and typed."""
    placeholders = _build_dashboard_configure_placeholders(
        dog_count=2,
        dashboard_info="info",
        features="features",
    )

    assert isinstance(placeholders, MappingProxyType)
    assert placeholders["dog_count"] == 2
    assert placeholders["dashboard_info"] == "info"
    assert placeholders["features"] == "features"


@pytest.mark.unit
def test_translated_dashboard_info_line_formats_count_and_falls_back_to_key() -> None:
    """Unknown keys should pass through while count templates are rendered."""
    assert _translated_dashboard_info_line("de", "multi_dog", count=3).endswith(
        "3 Hunde empfohlen"
    )
    assert _translated_dashboard_info_line("de", "unknown_key") == "unknown_key"


@pytest.mark.unit
def test_dashboard_info_includes_multi_dog_line_when_multiple_dogs() -> None:
    """Info text includes the multi-dog recommendation for multiple profiles."""
    flow = _DashboardFlowHarness(dog_count=2)

    info = flow._get_dashboard_info("en")

    assert "for 2 dogs recommended" in info


@pytest.mark.unit
def test_build_dashboard_features_string_adds_optional_features() -> None:
    """Feature summary includes map and multi-dog labels when enabled."""
    flow = _DashboardFlowHarness(dog_count=2)

    features = flow._build_dashboard_features_string("en", has_gps_enabled=True)

    assert "location maps" in features
    assert "multi-dog overview" in features


@pytest.mark.asyncio
@pytest.mark.unit
async def test_dashboard_step_routes_to_external_entities_with_gps() -> None:
    """The dashboard step should continue to external entities when GPS is on."""
    flow = _DashboardFlowHarness(dog_count=1)
    flow._enabled_modules = {"gps": True}

    result = await flow.async_step_configure_dashboard({"show_maps": False})

    assert result == {"step_id": "configure_external_entities"}
    assert flow._dashboard_config["show_maps"] is False
    assert flow._dashboard_config["dashboard_enabled"] is True
