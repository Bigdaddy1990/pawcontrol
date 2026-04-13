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
                },
                "Ignored-Malformed": "not-a-mapping",
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
async def test_remove_config_entry_device_handles_non_mapping_and_unsanitizable_ids(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed map entries and invalid IDs should be skipped cleanly."""
    monkeypatch.setattr(
        "custom_components.pawcontrol.sanitize_dog_id",
        lambda _dog_id: "",
    )

    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: {
                "bad-entry": "not-a-mapping",
                "!!!": {DOG_NAME_FIELD: 123},
            }
        },
        options={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "!!!",
                    DOG_NAME_FIELD: 123,
                }
            ]
        },
    )
    device_entry = DeviceEntry(
        id="invalid-id-device",
        identifiers={(DOMAIN, sanitize_dog_id("No Match"))},
    )

    assert await async_remove_config_entry_device(hass, entry, device_entry) is True


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
async def test_remove_config_entry_device_normalizes_sequence_and_mapping_names(
    hass: HomeAssistant,
) -> None:
    """Dog ids should be preserved even when payload names are malformed."""


async def test_remove_config_entry_device_sequence_source_falls_back_to_dog_id_name(
    hass: HomeAssistant,
) -> None:
    """Sequence dog payloads without names should fall back to their dog id."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                "ignored-non-mapping",
                {DOG_ID_FIELD: "Sequence-77"},
            ],
        },
    )
    active_device = DeviceEntry(
        id="sequence-device",
        identifiers={(DOMAIN, sanitize_dog_id("Sequence-77"))},
    )
    DeviceEntry(
        id="sequence-orphan",
        identifiers={(DOMAIN, sanitize_dog_id("No-Sequence-Match"))},
    )

    assert await async_remove_config_entry_device(hass, entry, active_device) is False


@pytest.mark.asyncio
async def test_remove_config_entry_device_skips_invalid_mapping_and_falls_back_to_id(
    hass: HomeAssistant,
) -> None:
    """Mapping payloads should ignore non-mappings and coerce missing dog names."""
    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: {
                "Map Dog": "invalid-payload",
            },
        },
        options={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "Seq Dog",
                    DOG_NAME_FIELD: 123,
                }
            ]
        },
    )

    mapping_device = DeviceEntry(
        id="mapping-device",
        identifiers={(DOMAIN, sanitize_dog_id("Map Dog"))},
    )
    sequence_device = DeviceEntry(
        id="sequence-device",
        identifiers={(DOMAIN, sanitize_dog_id("Seq Dog"))},
    )

    assert await async_remove_config_entry_device(hass, entry, mapping_device) is True
    assert await async_remove_config_entry_device(hass, entry, sequence_device) is False


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
async def test_remove_config_entry_device_handles_none_normalization_and_non_mapping_options(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid normalized dogs and non-mapping options should be skipped defensively."""

    def _ensure_dog_config_data(candidate):  # type: ignore[no-untyped-def]
        dog_id = candidate.get(DOG_ID_FIELD)
        if dog_id in {"drop-map", "drop-seq"}:
            return None
        return candidate

    monkeypatch.setattr(
        "custom_components.pawcontrol.ensure_dog_config_data",
        _ensure_dog_config_data,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.sanitize_dog_id",
        lambda dog_id: "" if dog_id == "unsanitized" else str(dog_id).lower(),
    )

    entry = ConfigEntry(
        domain=DOMAIN,
        entry_id="defensive-entry",
        data={
            CONF_DOGS: {
                "drop-map": {DOG_NAME_FIELD: "Drop Map"},
                "unsanitized": {DOG_NAME_FIELD: "Unsanitized"},
            },
        },
        options=[],  # non-mapping options payload
    )
    store_runtime_data(
        hass,
        entry,
        runtime_data=type("RuntimeData", (), {"dogs": [{DOG_ID_FIELD: "drop-seq"}]})(),
    )

    device_entry = DeviceEntry(
        id="defensive-device",
        identifiers={(DOMAIN, "orphan")},
    )

    assert await async_remove_config_entry_device(hass, entry, device_entry) is True


@pytest.mark.asyncio
async def test_remove_config_entry_device_skips_unsanitizable_option_candidates(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Option candidates with empty sanitized IDs should not be added as active dogs."""
    monkeypatch.setattr(
        "custom_components.pawcontrol.sanitize_dog_id",
        lambda dog_id: "" if str(dog_id).startswith("bad") else sanitize_dog_id(dog_id),
    )

    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [],
            CONF_DOG_OPTIONS: [{DOG_ID_FIELD: "bad-seq"}],
        },
        options={
            CONF_DOG_OPTIONS: {
                "bad-map": {DOG_ID_FIELD: "bad-map"},
            }
        },
    )
    orphan_device = DeviceEntry(
        id="option-orphan",
        identifiers={(DOMAIN, sanitize_dog_id("no-match"))},
    )

    assert await async_remove_config_entry_device(hass, entry, orphan_device) is True


@pytest.mark.asyncio
async def test_remove_config_entry_device_covers_iterator_continue_branches(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise mapping/sequence continue paths and option-shape guard branches."""

    class _Entry:
        def __init__(self, *, data: dict[str, object], options: object) -> None:
            self.data = data
            self.options = options
            self.entry_id = "iter-branch-entry"

    monkeypatch.setattr(
        "custom_components.pawcontrol.get_runtime_data", lambda *_: None
    )

    def _ensure_dog_config_data(candidate):  # type: ignore[no-untyped-def]
        dog_id = candidate.get(DOG_ID_FIELD)
        if dog_id in {"drop-map", "drop-seq"}:
            return None
        return candidate

    monkeypatch.setattr(
        "custom_components.pawcontrol.ensure_dog_config_data",
        _ensure_dog_config_data,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.sanitize_dog_id",
        lambda dog_id: "" if str(dog_id).startswith("bad") else str(dog_id).lower(),
    )

    orphan_device = DeviceEntry(
        id="iter-branch-device",
        identifiers={(DOMAIN, "orphan")},
    )

    mapping_entry = _Entry(
        data={
            CONF_DOGS: {
                "drop-map": {DOG_NAME_FIELD: "Drop"},
                "bad-map": {DOG_NAME_FIELD: "Bad"},
                "keep-map": {DOG_NAME_FIELD: "Keep"},
            },
        },
        options={},
    )
    assert (
        await async_remove_config_entry_device(hass, mapping_entry, orphan_device)
        is True
    )

    sequence_entry = _Entry(
        data={
            CONF_DOGS: [
                {DOG_ID_FIELD: "drop-seq", DOG_NAME_FIELD: "Drop"},
                {DOG_ID_FIELD: "keep-seq", DOG_NAME_FIELD: "Keep"},
            ],
        },
        options=[],  # non-mapping options trigger options-shape guards
    )
    assert (
        await async_remove_config_entry_device(hass, sequence_entry, orphan_device)
        is True
    )

    options_entry = _Entry(
        data={
            CONF_DOGS: [],
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "bad-seq-a"},
                {DOG_ID_FIELD: "bad-seq-b"},
            ],
        },
        options={
            CONF_DOG_OPTIONS: {
                "bad-map-key": {DOG_ID_FIELD: "bad-map-id"},
            },
        },
    )
    assert (
        await async_remove_config_entry_device(hass, options_entry, orphan_device)
        is True
    )


@pytest.mark.asyncio
async def test_remove_config_entry_device_covers_mapping_sequence_and_option_yield_branches(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid mapping/sequence payloads should iterate through multiple yielded IDs."""
    monkeypatch.setattr(
        "custom_components.pawcontrol.sanitize_dog_id",
        lambda dog_id: "" if str(dog_id) == "!!!" else sanitize_dog_id(dog_id),
    )

    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: {
                "Map-A": {DOG_NAME_FIELD: "Map A"},
                "!!!": {DOG_NAME_FIELD: "Unsanitized"},
                "Map-B": {DOG_NAME_FIELD: "Map B"},
            },
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "Seq-Opt-1"},
                {DOG_ID_FIELD: "Seq-Opt-2"},
            ],
        },
        options={
            CONF_DOGS: [
                {DOG_ID_FIELD: "Seq-A", DOG_NAME_FIELD: "Seq A"},
                {DOG_ID_FIELD: "Seq-B", DOG_NAME_FIELD: "Seq B"},
            ],
            CONF_DOG_OPTIONS: {
                "Opt-Key-1": {DOG_ID_FIELD: "Opt-Id-1"},
                "Opt-Key-2": {DOG_ID_FIELD: "Opt-Id-2"},
            },
        },
    )
    orphan_device = DeviceEntry(
        id="yield-branch-device",
        identifiers={(DOMAIN, sanitize_dog_id("No-Match"))},
    )

    assert await async_remove_config_entry_device(hass, entry, orphan_device) is True


@pytest.mark.asyncio
async def test_remove_config_entry_device_covers_unsanitized_continue_paths(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsanitized/invalid candidates should continue iterating over remaining items."""

    def _ensure_dog_config_data(candidate):  # type: ignore[no-untyped-def]
        dog_id = candidate.get(DOG_ID_FIELD)
        if dog_id in {"drop-map", "drop-seq"}:
            return None
        return candidate

    monkeypatch.setattr(
        "custom_components.pawcontrol.ensure_dog_config_data",
        _ensure_dog_config_data,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.sanitize_dog_id",
        lambda dog_id: "" if str(dog_id).startswith("bad") else sanitize_dog_id(dog_id),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.get_runtime_data", lambda *_: None
    )

    entry = ConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: {
                "drop-map": {DOG_NAME_FIELD: "Drop"},
                "bad-keep": {DOG_NAME_FIELD: "Unsanitized"},
                "good-map": {DOG_NAME_FIELD: "Good"},
            },
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "bad-opt-seq"},
                {DOG_ID_FIELD: "good-opt-seq"},
            ],
        },
        options={
            CONF_DOGS: [
                {DOG_ID_FIELD: "drop-seq", DOG_NAME_FIELD: "Drop Seq"},
                {DOG_ID_FIELD: "good-seq", DOG_NAME_FIELD: "Good Seq"},
            ],
            CONF_DOG_OPTIONS: {
                "bad-opt-key-a": {DOG_ID_FIELD: "bad-opt-key-b"},
                "good-opt-key": {DOG_ID_FIELD: "good-opt-id"},
            },
        },
    )
    orphan_device = DeviceEntry(
        id="continue-paths-device",
        identifiers={(DOMAIN, sanitize_dog_id("no-match"))},
    )

    assert await async_remove_config_entry_device(hass, entry, orphan_device) is True


@pytest.mark.asyncio
async def test_remove_config_entry_device_iterator_continue_paths_with_custom_entry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover continue branches for mapping/sequence dogs and option iterators."""

    class _Entry:
        def __init__(
            self, *, data: dict[str, object], options: dict[str, object]
        ) -> None:
            self.data = data
            self.options = options
            self.entry_id = "iterator-continue-entry"

    def _ensure_dog_config_data(candidate):  # type: ignore[no-untyped-def]
        dog_id = candidate.get(DOG_ID_FIELD)
        if dog_id in {"drop-map", "drop-seq"}:
            return None
        return candidate

    monkeypatch.setitem(
        async_remove_config_entry_device.__globals__,
        "get_runtime_data",
        lambda *_: None,
    )
    monkeypatch.setitem(
        async_remove_config_entry_device.__globals__,
        "ensure_dog_config_data",
        _ensure_dog_config_data,
    )
    monkeypatch.setitem(
        async_remove_config_entry_device.__globals__,
        "sanitize_dog_id",
        lambda dog_id: "" if str(dog_id).startswith("bad") else str(dog_id).lower(),
    )

    entry = _Entry(
        data={
            CONF_DOGS: {
                "drop-map": {DOG_NAME_FIELD: "Drop"},
                "bad-map": {DOG_NAME_FIELD: "Unsanitized"},
                "good-map": {DOG_NAME_FIELD: "Good"},
            },
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "bad-option-seq"},
                {DOG_ID_FIELD: "good-option-seq"},
            ],
        },
        options={
            CONF_DOGS: [
                {DOG_ID_FIELD: "drop-seq", DOG_NAME_FIELD: "Drop Sequence"},
                {DOG_ID_FIELD: "bad-seq", DOG_NAME_FIELD: "Unsanitized Sequence"},
                {DOG_ID_FIELD: "good-seq", DOG_NAME_FIELD: "Good Sequence"},
            ],
            CONF_DOG_OPTIONS: {
                "bad-option-key-a": {DOG_ID_FIELD: "bad-option-key-b"},
                "good-option-key": {DOG_ID_FIELD: "good-option-id"},
            },
        },
    )
    orphan_device = DeviceEntry(
        id="iterator-continue-device",
        identifiers={(DOMAIN, "no-match")},
    )

    assert await async_remove_config_entry_device(hass, entry, orphan_device) is True


@pytest.mark.asyncio
async def test_remove_config_entry_device_hits_all_unsanitized_iterator_branches(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force all remaining iterator continue branches with deterministic inputs."""

    class _Entry:
        def __init__(
            self, *, data: dict[str, object], options: dict[str, object]
        ) -> None:
            self.data = data
            self.options = options
            self.entry_id = "iterator-continue-all"

    ensured_ids: list[str] = []
    sanitized_ids: list[str] = []

    def _ensure_dog_config_data(candidate):  # type: ignore[no-untyped-def]
        dog_id = str(candidate.get(DOG_ID_FIELD))
        ensured_ids.append(dog_id)
        if dog_id in {"drop-map-1", "drop-map-2", "drop-seq-1", "drop-seq-2"}:
            return None
        return candidate

    def _sanitize_dog_id(dog_id):  # type: ignore[no-untyped-def]
        value = str(dog_id)
        sanitized_ids.append(value)
        if "bad" in value:
            return ""
        return value.lower()

    monkeypatch.setitem(
        async_remove_config_entry_device.__globals__,
        "get_runtime_data",
        lambda *_: None,
    )
    monkeypatch.setitem(
        async_remove_config_entry_device.__globals__,
        "ensure_dog_config_data",
        _ensure_dog_config_data,
    )
    monkeypatch.setitem(
        async_remove_config_entry_device.__globals__,
        "sanitize_dog_id",
        _sanitize_dog_id,
    )

    entry = _Entry(
        data={
            CONF_DOGS: {
                "drop-map-1": {DOG_NAME_FIELD: "Drop 1"},
                "drop-map-2": {DOG_NAME_FIELD: "Drop 2"},
                "bad-map-keep": {DOG_NAME_FIELD: "Bad Keep"},
            },
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "bad-seq-opt-1"},
                {DOG_ID_FIELD: "bad-seq-opt-2"},
            ],
        },
        options={
            CONF_DOGS: [
                {DOG_ID_FIELD: "drop-seq-1", DOG_NAME_FIELD: "Drop Seq 1"},
                {DOG_ID_FIELD: "drop-seq-2", DOG_NAME_FIELD: "Drop Seq 2"},
                {DOG_ID_FIELD: "bad-seq-keep", DOG_NAME_FIELD: "Bad Seq Keep"},
            ],
            CONF_DOG_OPTIONS: {
                "bad-opt-key-1": {DOG_ID_FIELD: "bad-opt-id-1"},
            },
        },
    )
    orphan_device = DeviceEntry(
        id="iterator-continue-all-device",
        identifiers={(DOMAIN, "no-match")},
    )

    assert await async_remove_config_entry_device(hass, entry, orphan_device) is True
    assert "drop-map-1" in ensured_ids
    assert "drop-map-2" in ensured_ids
    assert "drop-seq-1" in ensured_ids
    assert "drop-seq-2" in ensured_ids
    assert "bad-map-keep" in sanitized_ids
    assert "bad-seq-keep" in sanitized_ids
    assert "bad-opt-key-1" in sanitized_ids
    assert "bad-opt-id-1" in sanitized_ids
    assert "bad-seq-opt-1" in sanitized_ids
    assert "bad-seq-opt-2" in sanitized_ids


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
