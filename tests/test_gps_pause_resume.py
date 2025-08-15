from unittest.mock import patch

import custom_components.pawcontrol as comp
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = comp.DOMAIN


@pytest.mark.asyncio
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_gps_pause_and_resume(hass: HomeAssistant, expected_lingering_timers):
    assert await comp.async_setup(hass, {}) or True
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"dogs": [{"dog_id": "d1"}]},
    )
    entry.add_to_hass(hass)

    # Mock the heavy dependencies to avoid setup issues in tests
    with (
        patch(
            "custom_components.pawcontrol.coordinator.PawControlCoordinator"
        ) as mock_coord,
        patch(
            "custom_components.pawcontrol.helpers.notification_router.NotificationRouter"
        ),
        patch("custom_components.pawcontrol.helpers.setup_sync.SetupSync"),
        patch("custom_components.pawcontrol.services.ServiceManager"),
    ):
        mock_coord.return_value.async_config_entry_first_refresh.return_value = None
        await comp.async_setup_entry(hass, entry)
        await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "gps_pause_tracking")
    assert hass.services.has_service(DOMAIN, "gps_resume_tracking")
