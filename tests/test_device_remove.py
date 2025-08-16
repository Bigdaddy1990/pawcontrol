from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.asyncio


async def test_async_remove_config_entry_device_allows_removal(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.helpers import device_registry as dr

    entry = MockConfigEntry(domain=comp.DOMAIN, data={}, options={}, entry_id="e1")
    entry.add_to_hass(hass)
    
    # Mock all heavy dependencies to avoid setup issues in tests
    with (
        patch("custom_components.pawcontrol.coordinator.PawControlCoordinator") as mock_coord,
        patch("custom_components.pawcontrol.helpers.notification_router.NotificationRouter"),
        patch("custom_components.pawcontrol.helpers.setup_sync.SetupSync"),
        patch("custom_components.pawcontrol.services.ServiceManager") as mock_service_manager,
        patch("custom_components.pawcontrol.gps_handler.PawControlGPSHandler") as mock_gps_handler,
        patch("custom_components.pawcontrol.report_generator.ReportGenerator"),
        patch("custom_components.pawcontrol.helpers.scheduler.setup_schedulers"),
    ):
        # Setup all async mocks properly
        mock_coord.return_value.async_config_entry_first_refresh.return_value = None
        mock_service_manager.return_value.async_register_services.return_value = None
        mock_gps_handler.return_value.async_setup.return_value = None
        
        await comp.async_setup_entry(hass, entry)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(comp.DOMAIN, "dog-x")}
    )
    # Should allow removal for our domain device
    ok = await comp.async_remove_config_entry_device(hass, entry, device)
    assert ok
