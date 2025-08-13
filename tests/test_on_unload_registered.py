import pytest

pytestmark = pytest.mark.asyncio


async def test_entry_has_on_unload_callbacks(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        domain=comp.DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="e1",
        options={},
    )
    # Before setup, no callbacks
    assert not getattr(entry, "_on_unload", [])
    await comp.async_setup_entry(hass, entry)
    # After setup, we expect at least one on_unload callback registered
    assert len(getattr(entry, "_on_unload", [])) > 0
