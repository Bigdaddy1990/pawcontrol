import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.asyncio


async def test_entry_has_on_unload_callbacks(hass):
    import custom_components.pawcontrol as comp

    entry = MockConfigEntry(domain=comp.DOMAIN, data={}, options={}, entry_id="e1")
    entry.add_to_hass(hass)
    # Before setup, no callbacks
    assert not getattr(entry, "_on_unload", [])
    await comp.async_setup_entry(hass, entry)
    # After setup, we expect at least one on_unload callback registered
    assert len(getattr(entry, "_on_unload", [])) > 0
