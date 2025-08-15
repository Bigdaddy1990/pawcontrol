import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "pawcontrol"


@pytest.mark.asyncio
async def test_services_registered(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for svc in [
        "notify_test",
        "gps_start_walk",
        "gps_end_walk",
        "gps_post_location",
        "gps_pause_tracking",
        "gps_resume_tracking",
        "gps_export_last_route",
        "gps_generate_diagnostics",
        "gps_reset_stats",
        "route_history_list",
        "route_history_purge",
        "route_history_export_range",
        "toggle_geofence_alerts",
        "purge_all_storage",
    ]:
        assert hass.services.has_service(DOMAIN, svc), f"missing service {svc}"
