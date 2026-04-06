"""Tests for PawControl device registry behavior."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
import pytest

from custom_components.pawcontrol import async_remove_config_entry_device
from custom_components.pawcontrol.const import CONF_DOG_OPTIONS, CONF_DOGS, DOMAIN
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD
from custom_components.pawcontrol.utils import (
    async_get_or_create_dog_device_entry,
    sanitize_dog_id,
)


@pytest.mark.asyncio
async def test_remove_config_entry_device_blocks_configured_dog(
    hass: HomeAssistant,
) -> None:
    """Ensure configured dogs are not removed from the device registry."""
    entry = ConfigEntry(
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
    device_entry = DeviceEntry(
        id="device-1",
        identifiers={(DOMAIN, sanitize_dog_id("Buddy 1"))},
    )

    result = await async_remove_config_entry_device(hass, entry, device_entry)

    assert result is False


@pytest.mark.asyncio
async def test_remove_config_entry_device_allows_orphaned_device(
    hass: HomeAssistant,
) -> None:
    """Allow removal when no configured dogs match the device identifiers."""
    entry = ConfigEntry(
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
    device_entry = DeviceEntry(
        id="device-2",
        identifiers={(DOMAIN, sanitize_dog_id("Echo"))},
    )

    result = await async_remove_config_entry_device(hass, entry, device_entry)

    assert result is True


@pytest.mark.asyncio
async def test_remove_config_entry_device_ignores_non_pawcontrol_identifiers(
    hass: HomeAssistant,
) -> None:
    """Ignore unrelated devices that are not managed by the integration."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "Luna",
                    DOG_NAME_FIELD: "Luna",
                }
            ],
        },
    )
    device_entry = DeviceEntry(
        id="device-3",
        identifiers={("other_domain", "luna")},
    )

    result = await async_remove_config_entry_device(hass, entry, device_entry)

    assert result is False


@pytest.mark.asyncio
async def test_remove_config_entry_device_considers_dog_options_mapping(
    hass: HomeAssistant,
) -> None:
    """Prevent removal when identifiers are still present in dog option payloads."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: []},
        options={
            CONF_DOG_OPTIONS: {
                "NOVA 007": {DOG_ID_FIELD: "NOVA 007"},
            }
        },
    )
    device_entry = DeviceEntry(
        id="device-4",
        identifiers={(DOMAIN, sanitize_dog_id("NOVA 007"))},
    )

    result = await async_remove_config_entry_device(hass, entry, device_entry)

    assert result is False


@pytest.mark.asyncio
async def test_remove_config_entry_device_uses_mapping_payloads(
    hass: HomeAssistant,
) -> None:
    """Keep mapped dog definitions and data-level dog options in the active set."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: {
                "Delta-9": {
                    DOG_NAME_FIELD: "Delta",
                }
            },
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "Ghost 55"},
            ],
        },
        options={
            CONF_DOGS: {
                "Echo-11": {
                    DOG_ID_FIELD: "Echo-11",
                }
            }
        },
    )

    mapped_device = DeviceEntry(
        id="device-mapped",
        identifiers={(DOMAIN, sanitize_dog_id("Delta-9"))},
    )
    options_device = DeviceEntry(
        id="device-options",
        identifiers={(DOMAIN, sanitize_dog_id("Echo-11"))},
    )
    data_options_device = DeviceEntry(
        id="device-data-options",
        identifiers={(DOMAIN, sanitize_dog_id("Ghost 55"))},
    )
    orphaned_device = DeviceEntry(
        id="device-orphaned",
        identifiers={(DOMAIN, sanitize_dog_id("Zulu-1"))},
    )

    test_cases = [
        (mapped_device, "mapped data[CONF_DOGS]", False),
        (options_device, "options[CONF_DOGS]", False),
        (data_options_device, "data[CONF_DOG_OPTIONS]", False),
        (orphaned_device, "orphaned identifier", True),
    ]

    for device, description, expected in test_cases:
        result = await async_remove_config_entry_device(hass, entry, device)
        assert result is expected, (
            f"Expected {description} to return {expected} during removal check"
        )


@pytest.mark.asyncio
async def test_remove_config_entry_device_uses_runtime_data_and_skips_invalid_payloads(
    hass: HomeAssistant,
) -> None:
    """Runtime dogs should block removal while malformed payloads are ignored."""
    entry = ConfigEntry(
        domain=DOMAIN,
        entry_id="runtime-entry",
        data={
            CONF_DOGS: [
                "not-a-mapping",
                {DOG_NAME_FIELD: "Missing dog id"},
            ],
            CONF_DOG_OPTIONS: [
                "invalid",
                {DOG_NAME_FIELD: "Still missing id"},
            ],
        },
        options={
            CONF_DOG_OPTIONS: {
                "": {DOG_ID_FIELD: ""},
                "Valid Key": "not-a-mapping",
            },
        },
    )
    store_runtime_data(
        hass,
        entry,
        runtime_data=type(
            "RuntimeData",
            (),
            {
                "dogs": [
                    {
                        DOG_ID_FIELD: "Runtime Dog",
                        DOG_NAME_FIELD: "Runtime Dog",
                    }
                ]
            },
        )(),
    )

    runtime_device = DeviceEntry(
        id="runtime-device",
        identifiers={
            (DOMAIN, sanitize_dog_id("Runtime Dog")),
            ("other", "ignored"),
            (DOMAIN, "invalid", "identifier"),
        },
    )
    orphan_device = DeviceEntry(
        id="orphan-device",
        identifiers={(DOMAIN, sanitize_dog_id("No Match"))},
    )

    assert await async_remove_config_entry_device(hass, entry, runtime_device) is False
    assert await async_remove_config_entry_device(hass, entry, orphan_device) is True


@pytest.mark.asyncio
async def test_remove_config_entry_device_skips_invalid_mapping_and_falls_back_to_id(
    hass: HomeAssistant,
) -> None:
    """Mapping payloads should ignore non-mappings and coerce missing dog names."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: {
                "SkipMe": "not-a-mapping",
                "Nameless-42": {DOG_NAME_FIELD: 1234},
            },
        },
        options={},
    )
    active_device = DeviceEntry(
        id="name-fallback-device",
        identifiers={(DOMAIN, sanitize_dog_id("Nameless-42"))},
    )

    assert await async_remove_config_entry_device(hass, entry, active_device) is False


@pytest.mark.asyncio
async def test_remove_config_entry_device_sequence_payload_handles_invalid_ids(
    hass: HomeAssistant,
) -> None:
    """Sequence payloads should coerce names and ignore unsanitizable dog ids."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {DOG_ID_FIELD: "!!!", DOG_NAME_FIELD: 100},
            ],
        },
        options={},
    )
    orphan_device = DeviceEntry(
        id="sequence-invalid-id",
        identifiers={(DOMAIN, sanitize_dog_id("Other Dog"))},
    )

    assert await async_remove_config_entry_device(hass, entry, orphan_device) is True


@pytest.mark.asyncio
async def test_async_get_or_create_dog_device_entry_updates_metadata(
    hass: HomeAssistant,
) -> None:
    """Verify dog devices are created and updated dynamically."""
    dr.async_get(hass)

    device = await async_get_or_create_dog_device_entry(
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

    assert device.name == "Fido"
    assert device.suggested_area == "Living Room"
    assert device.serial_number == "SN-123"
    assert device.hw_version == "HW-1"
    assert device.sw_version == "1.0.0"
    assert device.configuration_url == "https://example.com/device"
    assert (DOMAIN, sanitize_dog_id("Fido 99")) in device.identifiers
    assert ("external", "ext-42") in device.identifiers
    assert ("microchip", "ABC123") in device.identifiers

    updated = await async_get_or_create_dog_device_entry(
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

    assert updated.id == device.id
    assert updated.suggested_area == "Yard"
    assert updated.sw_version == "1.1.0"
    assert updated.name == "Fido"
    assert updated.serial_number == "SN-123"
    assert updated.hw_version == "HW-1"
    assert (DOMAIN, sanitize_dog_id("Fido 99")) in updated.identifiers
    assert ("external", "ext-42") in updated.identifiers
    assert ("microchip", "ABC123") in updated.identifiers
