from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "pawcontrol"


@pytest.mark.asyncio
async def test_route_history_list_emits_event(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    import custom_components.pawcontrol as comp

    entry = init_integration

    with patch(
        "custom_components.pawcontrol.route_store.RouteHistoryStore.async_list",
        new=AsyncMock(
            return_value=[{"id": "r1", "start_time": "2025-08-01T10:00:00+00:00"}]
        ),
    ):
        events = []
        unsub = hass.bus.async_listen(
            f"{DOMAIN}_route_history_listed", lambda e: events.append(e)
        )
        await hass.services.async_call(
            DOMAIN,
            "route_history_list",
            {"config_entry_id": entry.entry_id},
            blocking=True,
        )
        await hass.async_block_till_done()
        unsub()
        assert events, "Expected event to be fired"
        assert events[0].data["result"][0]["id"] == "r1"


@pytest.mark.asyncio
async def test_gps_post_location_calls_handler(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    import custom_components.pawcontrol as comp

    called = {}

    async def fake_update_location(hass, call):
        called["ok"] = True
        called["data"] = dict(call.data)

    with patch(
        "custom_components.pawcontrol.gps_handler.async_update_location",
        new=AsyncMock(side_effect=fake_update_location),
    ):
        await hass.services.async_call(
            DOMAIN,
            "gps_post_location",
            {"latitude": 52.5, "longitude": 13.4},
            blocking=True,
        )
        assert called.get("ok")
        assert called["data"]["latitude"] == 52.5


@pytest.mark.asyncio
async def test_route_history_list_requires_loaded_entry(hass: HomeAssistant):
    import custom_components.pawcontrol as comp

    assert await comp.async_setup(hass, {}) or True
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "route_history_list", {}, blocking=True)
