"""Additional regression coverage for setup validation helpers."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import ConfigurationError
from custom_components.pawcontrol.setup import validation


@pytest.mark.asyncio
async def test_validate_dogs_config_rejects_non_list_payload() -> None:
    """Dogs configuration must be a list payload."""
    entry = SimpleNamespace(data={"dogs": {"dog_id": "buddy"}}, entry_id="entry-1")

    with pytest.raises(ConfigurationError, match="must be a list"):
        await validation._async_validate_dogs_config(entry)


@pytest.mark.asyncio
async def test_validate_dogs_config_rejects_non_mapping_entries() -> None:
    """Each dog payload must be a mapping."""
    entry = SimpleNamespace(data={"dogs": ["buddy"]}, entry_id="entry-2")

    with pytest.raises(ConfigurationError, match="must be mappings"):
        await validation._async_validate_dogs_config(entry)


@pytest.mark.asyncio
async def test_validate_dogs_config_rejects_missing_required_keys() -> None:
    """Dog payloads missing identifiers should raise a validation error."""
    entry = SimpleNamespace(data={"dogs": [{"dog_id": ""}]}, entry_id="entry-3")

    with pytest.raises(ConfigurationError, match="must include non-empty dog_id"):
        await validation._async_validate_dogs_config(entry)


@pytest.mark.asyncio
async def test_validate_dogs_config_logs_when_no_dogs_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A debug message should be emitted when no dogs are configured."""
    entry = SimpleNamespace(data={"dogs": None}, entry_id="entry-empty")

    with caplog.at_level("DEBUG"):
        dogs = await validation._async_validate_dogs_config(entry)

    assert dogs == []
    assert "No dogs configured for entry entry-empty" in caplog.text


def test_validate_profile_normalizes_unknown_and_none_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown or null profile values should fall back to standard."""
    entry_none = SimpleNamespace(options={"entity_profile": None})
    entry_unknown = SimpleNamespace(options={"entity_profile": 12345})

    assert validation._validate_profile(entry_none) == "standard"

    with caplog.at_level("WARNING"):
        resolved = validation._validate_profile(entry_unknown)

    assert resolved == "standard"
    assert "Unknown profile '12345'" in caplog.text


def test_extract_enabled_modules_ignores_invalid_and_unknown_modules(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Enabled modules extraction should skip malformed and unknown values."""
    dogs_config = [
        {"dog_id": "buddy", "modules": ["gps"]},
        {"dog_id": "luna", "modules": {"gps": True, "unknown_mod": True}},
        {"dog_id": "milo", "modules": {"feeding": False}},
    ]

    with caplog.at_level("WARNING"):
        enabled = validation._extract_enabled_modules(dogs_config)

    assert enabled == frozenset({"gps"})
    assert "because configuration is not a mapping" in caplog.text
    assert "Ignoring unknown PawControl modules: unknown_mod" in caplog.text


@pytest.mark.asyncio
async def test_async_validate_entry_config_returns_normalized_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The top-level setup validation helper should normalize each section."""
    entry = SimpleNamespace(
        entry_id="entry-validated",
        data={
            "dogs": [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    "modules": {"gps": True, "feeding": False},
                }
            ]
        },
        options={"entity_profile": "standard"},
    )

    with caplog.at_level("DEBUG"):
        dogs, profile, enabled_modules = await validation.async_validate_entry_config(
            entry
        )

    assert dogs == entry.data["dogs"]
    assert profile == "standard"
    assert enabled_modules == frozenset({"gps"})
    assert (
        "Config validation complete: 1 dogs, profile='standard', 1 modules enabled"
        in caplog.text
    )


def test_extract_enabled_modules_skips_missing_modules_key() -> None:
    """Dogs without module config should not contribute enabled modules."""
    dogs_config = [{"dog_id": "buddy", "dog_name": "Buddy"}]

    assert validation._extract_enabled_modules(dogs_config) == frozenset()
