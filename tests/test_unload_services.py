import pytest

pytestmark = pytest.mark.asyncio


async def test_unload_removes_services_when_last_entry(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.config_entries import ConfigEntry

    # Setup one entry → services registered
    entry = ConfigEntry(
        version=1,
        domain=comp.DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="e1",
        options={},
    )
    await comp.async_setup_entry(hass, entry)

    for svc in (
        "gps_post_location",
        "gps_start_walk",
        "gps_end_walk",
        "toggle_geofence_alerts",
    ):
        assert hass.services.has_service(comp.DOMAIN, svc)

    # Unload the entry
    ok = await comp.async_unload_entry(hass, entry)
    assert ok

    # After unloading last entry, services should be removed
    for svc in (
        "gps_post_location",
        "gps_start_walk",
        "gps_end_walk",
        "toggle_geofence_alerts",
    ):
        assert not hass.services.has_service(comp.DOMAIN, svc)
