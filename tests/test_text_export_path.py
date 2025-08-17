from pathlib import Path

import pytest
from custom_components.pawcontrol.text import (
    STORAGE_KEY,
    STORAGE_VERSION,
    ExportPathText,
)
from homeassistant.helpers.storage import Store


@pytest.mark.asyncio
async def test_export_path_updates_config_entry(
    hass, mock_config_entry, mock_coordinator
):
    """Ensure ExportPathText persists updates to the config entry."""
    mock_config_entry.add_to_hass(hass)
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{mock_config_entry.entry_id}")
    entity = ExportPathText(hass, mock_coordinator, mock_config_entry, store)

    await entity.async_set_value("~/exports")
    expected = str(Path("~/exports").expanduser())

    assert mock_config_entry.options["export_path"] == expected
    assert entity.native_value == expected
