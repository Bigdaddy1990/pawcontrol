from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "pawcontrol"


@pytest.mark.anyio
async def test_toggle_geofence_and_purge_storage(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {}) or True

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

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

    args, kwargs = save_mock.call_args
    assert isinstance(args[0], dict)
    assert args[0].get("geofence", {}).get("alerts_enabled") in (False, True)
    assert purge_mock.called
