import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from unittest.mock import patch

pytestmark = pytest.mark.asyncio


async def test_async_remove_config_entry_device_allows_removal(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.helpers import device_registry as dr

    entry = MockConfigEntry(domain=comp.DOMAIN, data={}, options={}, entry_id="e1")
    entry.add_to_hass(hass)
    
    # Mock the heavy dependencies to avoid setup issues in tests
    with (
        patch("custom_components.pawcontrol.coordinator.PawControlCoordinator") as mock_coord,
        patch("custom_components.pawcontrol.helpers.notification_router.NotificationRouter"),
        patch("custom_components.pawcontrol.helpers.setup_sync.SetupSync"),
        patch("custom_components.pawcontrol.services.ServiceManager"),
    ):
        mock_coord.return_value.async_config_entry_first_refresh.return_value = None
        await comp.async_setup_entry(hass, entry)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(comp.DOMAIN, "dog-x")}
    )
    # Should allow removal for our domain device
    ok = await comp.async_remove_config_entry_device(hass, entry, device)
    assert ok
