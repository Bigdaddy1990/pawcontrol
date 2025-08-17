from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "pawcontrol"


@pytest.mark.asyncio
async def test_toggle_geofence_and_purge_storage(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:

    entry = init_integration

    with (
        patch(
            "custom_components.pawcontrol.gps_settings.GPSSettingsStore.async_load",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "custom_components.pawcontrol.gps_settings.GPSSettingsStore.async_save",
            new=AsyncMock(),
        ) as save_mock,
        patch(
            "custom_components.pawcontrol.route_store.RouteHistoryStore.async_purge",
            new=AsyncMock(),
        ) as purge_mock,
    ):
        await hass.services.async_call(
            DOMAIN,
            "toggle_geofence_alerts",
            {"enabled": False, "config_entry_id": entry.entry_id},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "purge_all_storage",
            {"config_entry_id": entry.entry_id},
            blocking=True,
        )

    assert save_mock.called
    assert purge_mock.called
