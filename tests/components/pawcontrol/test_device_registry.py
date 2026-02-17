"""Tests for PawControl device registry behavior."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
import pytest

from custom_components.pawcontrol import async_remove_config_entry_device
from custom_components.pawcontrol.const import CONF_DOGS, DOMAIN
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD
from custom_components.pawcontrol.utils import (
    async_get_or_create_dog_device_entry,
    sanitize_dog_id,
)


@pytest.mark.asyncio
async def test_remove_config_entry_device_blocks_configured_dog(
    hass: HomeAssistant,
) -> None:
    """Ensure configured dogs are not removed from the device registry."""  # noqa: E111

    entry = ConfigEntry(  # noqa: E111
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "Buddy 1",
                    DOG_NAME_FIELD: "Buddy",
                }
            ],
        },
    )
    device_entry = DeviceEntry(  # noqa: E111
        id="device-1",
        identifiers={(DOMAIN, sanitize_dog_id("Buddy 1"))},
    )

    result = await async_remove_config_entry_device(hass, entry, device_entry)  # noqa: E111

    assert result is False  # noqa: E111


@pytest.mark.asyncio
async def test_remove_config_entry_device_allows_orphaned_device(
    hass: HomeAssistant,
) -> None:
    """Allow removal when no configured dogs match the device identifiers."""  # noqa: E111

    entry = ConfigEntry(  # noqa: E111
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "Juno",
                    DOG_NAME_FIELD: "Juno",
                }
            ],
        },
    )
    device_entry = DeviceEntry(  # noqa: E111
        id="device-2",
        identifiers={(DOMAIN, sanitize_dog_id("Echo"))},
    )

    result = await async_remove_config_entry_device(hass, entry, device_entry)  # noqa: E111

    assert result is True  # noqa: E111


@pytest.mark.asyncio
async def test_async_get_or_create_dog_device_entry_updates_metadata(
    hass: HomeAssistant,
) -> None:
    """Verify dog devices are created and updated dynamically."""  # noqa: E111

    dr.async_get(hass)  # noqa: E111

    device = await async_get_or_create_dog_device_entry(  # noqa: E111
        hass,
        config_entry_id="entry-1",
        dog_id="Fido 99",
        dog_name="Fido",
        sw_version="1.0.0",
        configuration_url="https://example.com/device",
        suggested_area="Living Room",
        serial_number="SN-123",
        hw_version="HW-1",
        microchip_id="abc-123",
        extra_identifiers=[("external", "ext-42")],
    )

    assert device.name == "Fido"  # noqa: E111
    assert device.suggested_area == "Living Room"  # noqa: E111
    assert device.serial_number == "SN-123"  # noqa: E111
    assert device.hw_version == "HW-1"  # noqa: E111
    assert device.sw_version == "1.0.0"  # noqa: E111
    assert device.configuration_url == "https://example.com/device"  # noqa: E111
    assert (DOMAIN, sanitize_dog_id("Fido 99")) in device.identifiers  # noqa: E111
    assert ("external", "ext-42") in device.identifiers  # noqa: E111
    assert ("microchip", "ABC123") in device.identifiers  # noqa: E111

    updated = await async_get_or_create_dog_device_entry(  # noqa: E111
        hass,
        config_entry_id="entry-1",
        dog_id="Fido 99",
        dog_name="Fido",
        sw_version="1.1.0",
        configuration_url="https://example.com/device",
        suggested_area="Yard",
        serial_number="SN-123",
        hw_version="HW-1",
    )

    assert updated.id == device.id  # noqa: E111
    assert updated.suggested_area == "Yard"  # noqa: E111
    assert updated.sw_version == "1.1.0"  # noqa: E111
    assert updated.name == "Fido"  # noqa: E111
    assert updated.serial_number == "SN-123"  # noqa: E111
    assert updated.hw_version == "HW-1"  # noqa: E111
    assert (DOMAIN, sanitize_dog_id("Fido 99")) in updated.identifiers  # noqa: E111
    assert ("external", "ext-42") in updated.identifiers  # noqa: E111
    assert ("microchip", "ABC123") in updated.identifiers  # noqa: E111
