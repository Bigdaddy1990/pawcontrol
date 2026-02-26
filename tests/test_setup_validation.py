"""Tests for setup configuration validation helpers."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.const import CONF_DOGS, CONF_MODULES
from custom_components.pawcontrol.exceptions import ConfigurationError
from custom_components.pawcontrol.setup.validation import (
    _extract_enabled_modules,
    _validate_profile,
    async_validate_entry_config,
)


@pytest.mark.asyncio
async def test_async_validate_entry_config_normalizes_profile_and_modules() -> None:
    """Validation should normalize profile values and collect enabled modules."""
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            CONF_DOGS: [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    CONF_MODULES: {
                        "gps": True,
                        "feeding": False,
                    },
                }
            ]
        },
        options={"entity_profile": 123},
    )

    dogs, profile, enabled_modules = await async_validate_entry_config(entry)

    assert dogs[0]["dog_id"] == "buddy"
    assert profile == "standard"
    assert enabled_modules == frozenset({"gps"})


@pytest.mark.asyncio
async def test_async_validate_entry_config_rejects_non_list_dogs() -> None:
    """Dogs config must be a list."""
    entry = SimpleNamespace(entry_id="entry-2", data={CONF_DOGS: {}}, options={})

    with pytest.raises(ConfigurationError, match="Dogs configuration must be a list"):
        await async_validate_entry_config(entry)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_dog_payload",
    [
        {"dog_id": "", "dog_name": "Buddy"},
        {"dog_id": "buddy", "dog_name": ""},
        {"dog_id": "buddy"},
        {"dog_name": "Buddy"},
        {},
    ],
)
async def test_async_validate_entry_config_rejects_invalid_dog_payload(
    invalid_dog_payload: dict[str, str],
) -> None:
    """Each dog must include non-empty id and name."""
    entry = SimpleNamespace(
        entry_id="entry-3",
        data={CONF_DOGS: [invalid_dog_payload]},
        options={},
    )

    with pytest.raises(
        ConfigurationError,
        match="each entry must include non-empty dog_id and dog_name",
    ):
        await async_validate_entry_config(entry)


@pytest.mark.asyncio
async def test_async_validate_entry_config_rejects_non_mapping_dog_entry() -> None:
    """Each dog entry must be represented as a mapping payload."""
    entry = SimpleNamespace(
        entry_id="entry-non-mapping-dog",
        data={CONF_DOGS: ["buddy"]},
        options={},
    )

    with pytest.raises(
        ConfigurationError,
        match="Dog configuration entries must be mappings",
    ):
        await async_validate_entry_config(entry)


def test_validate_profile_none_falls_back_to_standard() -> None:
    """Explicit None profile values should be normalized to standard."""
    entry = SimpleNamespace(options={"entity_profile": None})

    assert _validate_profile(entry) == "standard"


@pytest.mark.asyncio
async def test_async_validate_entry_config_accepts_none_dogs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing dogs should be treated as empty configuration."""
    entry = SimpleNamespace(entry_id="entry-4", data={CONF_DOGS: None}, options={})
    caplog.set_level("DEBUG")

    dogs, profile, enabled_modules = await async_validate_entry_config(entry)

    assert dogs == []
    assert profile == "standard"
    assert enabled_modules == frozenset()
    assert any(
        record.levelname == "DEBUG" and "No dogs configured" in record.message
        for record in caplog.records
    )


def test_validate_profile_falls_back_for_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown profiles should fall back to standard and log a warning."""
    caplog.set_level("WARNING")
    entry = SimpleNamespace(options={"entity_profile": "mystery"})

    assert _validate_profile(entry) == "standard"
    assert "Unknown profile 'mystery', using 'standard'" in caplog.text
    assert any(
        record.levelname == "WARNING"
        and "Unknown profile 'mystery', using 'standard'" in record.message
        for record in caplog.records
    )


def test_extract_enabled_modules_ignores_invalid_and_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Module extraction should ignore malformed and unknown module declarations."""
    caplog.set_level("WARNING")
    modules = _extract_enabled_modules([
        {"dog_id": "buddy", CONF_MODULES: "invalid"},
        {
            "dog_id": "luna",
            CONF_MODULES: {"gps": True, "new_module": True, "feeding": False},
        },
        {"dog_id": "max", CONF_MODULES: None},
    ])

    assert modules == frozenset({"gps"})
    assert (
        "Ignoring modules for dog buddy because configuration is not a mapping"
        in caplog.text
    )
    assert "Ignoring unknown PawControl modules: new_module" in caplog.text
    warning_messages = {
        record.message for record in caplog.records if record.levelname == "WARNING"
    }
    assert (
        "Ignoring modules for dog buddy because configuration is not a mapping"
        in warning_messages
    )
    assert "Ignoring unknown PawControl modules: new_module" in warning_messages
