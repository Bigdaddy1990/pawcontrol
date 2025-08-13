import pytest

pytestmark = pytest.mark.asyncio


async def test_async_remove_config_entry_device_allows_removal(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers import device_registry as dr

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

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(comp.DOMAIN, "dog-x")}
    )
    # Should allow removal for our domain device
    ok = await comp.async_remove_config_entry_device(hass, entry, device)
    assert ok
