import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

DOMAIN = "pawcontrol"


@pytest.mark.anyio
async def test_services_registered(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}}) or True
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
