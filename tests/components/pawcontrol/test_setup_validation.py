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

_DOG_TEMPLATE = {"dog_id": "dog-1", "dog_name": "Buddy"}


def _build_entry_with_dogs(dogs: object) -> MockConfigEntry:
    """Build a config entry with a dogs payload for validation tests."""
    return MockConfigEntry(domain=DOMAIN, data={CONF_DOGS: dogs})


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
@pytest.mark.parametrize(
    ("dogs_payload", "expected_error"),
    [
        ({"dog_id": "dog-1"}, "Dogs configuration must be a list"),
        (["dog-1"], "Dog configuration entries must be mappings"),
        ([{"dog_id": "dog-1", "dog_name": ""}], "Invalid dog configuration"),
    ],
)
async def test_async_validate_dogs_config_rejects_invalid_payloads(
    dogs_payload: object,
    expected_error: str,
) -> None:
    """Invalid dogs payloads should raise explicit configuration errors."""
    with pytest.raises(ConfigurationError, match=expected_error):
        await _async_validate_dogs_config(_build_entry_with_dogs(dogs_payload))


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_data", [{CONF_DOGS: None}, {}])
async def test_async_validate_dogs_config_accepts_empty_payloads_and_logs(
    entry_data: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """None or missing dogs payload should normalize to an empty validated list."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data)

    with caplog.at_level(logging.DEBUG):
        dogs = await _async_validate_dogs_config(entry)

    assert dogs == []
    assert "No dogs configured for entry" in caplog.text


@pytest.mark.parametrize(
    ("raw_profile", "expects_warning"),
    [(None, False), (123, True), ("unsupported-profile", True)],
)
def test_validate_profile_defaults_to_standard_for_invalid_values(
    raw_profile: object,
    expects_warning: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Profile helper should handle optional and unknown values safely."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={"entity_profile": raw_profile}
    )
    with caplog.at_level(logging.WARNING):
        assert _validate_profile(entry) == "standard"
    if expects_warning:
        assert "Unknown profile" in caplog.text
    else:
        assert "Unknown profile" not in caplog.text


@pytest.mark.parametrize(
    ("dogs_config", "expected_modules", "expected_log_fragment"),
    [
        (
            [
                {"dog_id": "dog-1", "dog_name": "Buddy", CONF_MODULES: "bad-payload"},
                {
                    "dog_id": "dog-2",
                    "dog_name": "Luna",
                    CONF_MODULES: {"gps": True, "unknown": True, "walk": False},
                },
            ],
            frozenset({"gps"}),
            "configuration is not a mapping",
        ),
        (
            [
                {
                    "dog_id": "dog-1",
                    "dog_name": "Buddy",
                    CONF_MODULES: {
                        "zz_unknown": True,
                        "aa_unknown": True,
                        "zz_unknown_duplicate": False,
                        "gps": True,
                    },
                },
                {
                    "dog_id": "dog-2",
                    "dog_name": "Luna",
                    CONF_MODULES: {"aa_unknown": True},
                },
            ],
            frozenset({"gps"}),
            "Ignoring unknown PawControl modules: aa_unknown, zz_unknown",
        ),
        (
            [
                _DOG_TEMPLATE,
                {
                    "dog_id": "dog-2",
                    "dog_name": "Luna",
                    CONF_MODULES: {"gps": True},
                },
            ],
            frozenset({"gps"}),
            "",
        ),
    ],
)
def test_extract_enabled_modules_validation_and_mapping(
    dogs_config: list[dict[str, object]],
    expected_modules: frozenset[str],
    expected_log_fragment: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Module extraction should normalize valid modules and validate invalid ones."""
    with caplog.at_level(logging.WARNING):
        modules = _extract_enabled_modules(dogs_config)
    assert modules == expected_modules
    if expected_log_fragment:
        assert expected_log_fragment in caplog.text
    else:
        assert caplog.text == ""
