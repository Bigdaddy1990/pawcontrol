from types import MappingProxyType

import pytest
from custom_components.pawcontrol.config_flow_dashboard_extension import (
    _build_dashboard_configure_placeholders,
)


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
