from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from custom_components.pawcontrol import system_health as system_health_module
from custom_components.pawcontrol.const import DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_system_health_no_api(hass: HomeAssistant) -> None:
    """Return defaults when API is unavailable."""
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
    mock_check.assert_not_called()


async def test_system_health_reports_coordinator_status(
    hass: HomeAssistant,
) -> None:
    """Use coordinator statistics when runtime data is available."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = False
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 3}
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        unique_id="coordinator-entry",
    )
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    entry.add_to_hass(hass)

    info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is True
    assert info["remaining_quota"] == "unlimited"
    coordinator.get_update_statistics.assert_called_once()


async def test_system_health_reports_external_quota(
    hass: HomeAssistant,
) -> None:
    """Report remaining quota when external API tracking is enabled."""

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.use_external_api = True
    coordinator.get_update_statistics.return_value = {
        "performance_metrics": {"api_calls": 7}
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": []},
        options={"external_api_quota": 10},
        unique_id="quota-entry",
    )
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    entry.add_to_hass(hass)

    info = await system_health_module.system_health_info(hass)

    assert info["can_reach_backend"] is True
    assert info["remaining_quota"] == 3
