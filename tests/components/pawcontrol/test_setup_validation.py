"""Tests for setup-time configuration validation helpers."""

import logging

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.const import CONF_DOGS, CONF_MODULES, DOMAIN
from custom_components.pawcontrol.exceptions import ConfigurationError
from custom_components.pawcontrol.setup.validation import (
    _async_validate_dogs_config,
    _extract_enabled_modules,
    _validate_profile,
    async_validate_entry_config,
)


@pytest.mark.asyncio
async def test_async_validate_entry_config_normalizes_profile_and_modules(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The entry validator should return normalized dogs, profile, and known modules."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    "dog_id": "dog-1",
                    "dog_name": "Buddy",
                    CONF_MODULES: {
                        "gps": True,
                        "weather": True,
                        "unknown": True,
                        "walk": False,
                    },
                },
            ],
        },
        options={"entity_profile": "unsupported-profile"},
    )

    with caplog.at_level(logging.WARNING):
        dogs, profile, modules = await async_validate_entry_config(entry)

    assert profile == "standard"
    assert modules == frozenset({"gps"})
    assert dogs[0]["dog_id"] == "dog-1"
    assert "Unknown profile 'unsupported-profile'" in caplog.text


@pytest.mark.asyncio
async def test_async_validate_dogs_config_requires_list_payload() -> None:
    """Dogs payload must be a list."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DOGS: {"dog_id": "dog-1"}})

    with pytest.raises(ConfigurationError, match="Dogs configuration must be a list"):
        await _async_validate_dogs_config(entry)


@pytest.mark.asyncio
async def test_async_validate_dogs_config_requires_mapping_entries() -> None:
    """Each dog payload must be a mapping."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DOGS: ["dog-1"]})

    with pytest.raises(
        ConfigurationError,
        match="Dog configuration entries must be mappings",
    ):
        await _async_validate_dogs_config(entry)


@pytest.mark.asyncio
async def test_async_validate_dogs_config_rejects_invalid_dog_records() -> None:
    """Dog records must include a non-empty ID and name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{"dog_id": "dog-1", "dog_name": ""}]},
    )

    with pytest.raises(ConfigurationError, match="Invalid dog configuration"):
        await _async_validate_dogs_config(entry)


@pytest.mark.asyncio
async def test_async_validate_dogs_config_accepts_none_payload_and_logs_empty_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A missing dogs payload should normalize to an empty list."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DOGS: None})

    with caplog.at_level(logging.DEBUG):
        dogs = await _async_validate_dogs_config(entry)

    assert dogs == []
    assert "No dogs configured for entry" in caplog.text


def test_validate_profile_defaults_to_standard_for_none_and_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Profile helper should handle optional and unknown values safely."""
    none_entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={"entity_profile": None}
    )
    assert _validate_profile(none_entry) == "standard"

    unknown_entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"entity_profile": 123},
    )
    with caplog.at_level(logging.WARNING):
        assert _validate_profile(unknown_entry) == "standard"

    assert "Unknown profile '123'" in caplog.text


def test_extract_enabled_modules_ignores_invalid_module_payloads(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Module extraction should ignore invalid and unknown module definitions."""
    dogs_config = [
        {"dog_id": "dog-1", "dog_name": "Buddy", CONF_MODULES: "bad-payload"},
        {
            "dog_id": "dog-2",
            "dog_name": "Luna",
            CONF_MODULES: {"gps": True, "unknown": True, "walk": False},
        },
    ]

    with caplog.at_level(logging.WARNING):
        modules = _extract_enabled_modules(dogs_config)

    assert modules == frozenset({"gps"})
    assert "configuration is not a mapping" in caplog.text


def test_extract_enabled_modules_ignores_missing_modules_key() -> None:
    """Dogs without module configuration should be ignored without warnings."""
    dogs_config = [
        {"dog_id": "dog-1", "dog_name": "Buddy"},
        {"dog_id": "dog-2", "dog_name": "Luna", CONF_MODULES: {"gps": True}},
    ]

    modules = _extract_enabled_modules(dogs_config)

    assert modules == frozenset({"gps"})
