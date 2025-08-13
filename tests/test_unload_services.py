import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.asyncio


async def test_unload_removes_services_when_last_entry(hass):
    import custom_components.pawcontrol as comp

    # Setup one entry → services registered
    entry = MockConfigEntry(domain=comp.DOMAIN, data={}, options={}, entry_id="e1")
    entry.add_to_hass(hass)
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
