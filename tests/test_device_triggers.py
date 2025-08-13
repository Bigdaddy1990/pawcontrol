import pytest

pytestmark = pytest.mark.asyncio


async def test_device_trigger_gps_location_posted(hass):
    """Device trigger fires when event with matching device_id is fired."""
    import custom_components.pawcontrol as comp
    from custom_components.pawcontrol.device_trigger import (
        async_attach_trigger,
        async_get_triggers,
    )
    from homeassistant.helpers import device_registry as dr

    # Create a device with identifiers (DOMAIN, dog_id)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id="e1", identifiers={(comp.DOMAIN, "dog-1")}
    )
    device_id = device.id

    # Build trigger config
    trigger = {
        "domain": comp.DOMAIN,
        "type": "gps_location_posted",
        "device_id": device_id,
    }

    triggers = await async_get_triggers(hass, device_id)
    assert any(t["type"] == "gps_location_posted" for t in triggers)

    fired = {"count": 0}

    async def action(**kwargs):
        fired["count"] += 1

    unsub = await async_attach_trigger(hass, trigger, action, {"platform": "device"})
    try:
        # Fire event with matching device_id
        hass.bus.async_fire(
            f"{comp.DOMAIN}_gps_location_posted", {"device_id": device_id}
        )
        await hass.async_block_till_done()
        assert fired["count"] == 1
    finally:
        unsub()


async def test_device_trigger_geofence_alert(hass):
    import custom_components.pawcontrol as comp
    from custom_components.pawcontrol.device_trigger import async_attach_trigger
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id="e1", identifiers={(comp.DOMAIN, "dog-2")}
    )
    device_id = device.id

    trigger = {"domain": comp.DOMAIN, "type": "geofence_alert", "device_id": device_id}
    called = {"ok": False}

    async def action(**kwargs):
        called["ok"] = True

    unsub = await async_attach_trigger(hass, trigger, action, {"platform": "device"})
    try:
        hass.bus.async_fire(
            f"{comp.DOMAIN}_geofence_alert",
            {"device_id": device_id, "action": "entered", "zone": "home"},
        )
        await hass.async_block_till_done()
        assert called["ok"]
    finally:
        unsub()
