from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.pawcontrol import system_health as system_health_module
from custom_components.pawcontrol.config_flow import config_flow_monitor
from custom_components.pawcontrol.const import DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_system_health_no_api(hass: HomeAssistant) -> None:
    """Return defaults when API is unavailable."""
    config_flow_monitor.operation_times.clear()
    config_flow_monitor.validation_counts.clear()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": [], "entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pawcontrol.system_health.system_health.async_check_can_reach_url"
    ) as mock_check:
        info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is False
    assert info["remaining_quota"] == "unknown"
    assert info["configured_dogs"] == 0
    assert info["entity_profile"] == "standard"
    assert info["config_flow_operations"] == {"validations": {}}
    assert "dog_names" not in info
    mock_check.assert_not_called()


async def test_system_health_with_runtime_data(hass: HomeAssistant) -> None:
    """Return expanded data when runtime information is available."""

    config_flow_monitor.operation_times.clear()
    config_flow_monitor.validation_counts.clear()
    config_flow_monitor.record_operation("user_step", 0.42)
    config_flow_monitor.record_validation("dog_validation")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "name": "Paw Control",
            "dogs": [{"dog_id": "rex", "dog_name": "Rex", "modules": {}}],
            "entity_profile": "standard",
        },
        options={"entity_profile": "advanced"},
        unique_id=DOMAIN,
    )
    entry.runtime_data = SimpleNamespace(
        api=SimpleNamespace(base_url="https://api.example.com"),
        remaining_quota="75%",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pawcontrol.system_health.system_health.async_check_can_reach_url",
        return_value=True,
    ) as mock_check:
        info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is True
    assert info["remaining_quota"] == "75%"
    assert info["configured_dogs"] == 1
    assert info["entity_profile"] == "advanced"
    assert info["dog_names"] == ["Rex"]
    assert info["config_flow_operations"]["user_step"]["count"] == 1
    assert info["config_flow_operations"]["validations"]["dog_validation"] == 1
    mock_check.assert_called_once_with(hass, "https://api.example.com")
