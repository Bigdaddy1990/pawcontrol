from types import MappingProxyType

import pytest

from custom_components.pawcontrol.config_flow_dashboard_extension import (
  _build_dashboard_configure_placeholders,
)


@pytest.mark.unit
def test_build_dashboard_configure_placeholders_returns_mapping_proxy() -> None:
  """Dashboard placeholders should remain immutable and typed."""  # noqa: E111

  placeholders = _build_dashboard_configure_placeholders(  # noqa: E111
    dog_count=2,
    dashboard_info="info",
    features="features",
  )

  assert isinstance(placeholders, MappingProxyType)  # noqa: E111
  assert placeholders["dog_count"] == 2  # noqa: E111
  assert placeholders["dashboard_info"] == "info"  # noqa: E111
  assert placeholders["features"] == "features"  # noqa: E111
