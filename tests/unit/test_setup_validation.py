"""Tests for setup.validation module."""

from collections.abc import Callable, Mapping

from homeassistant.config_entries import ConfigEntry
import pytest

from custom_components.pawcontrol.const import CONF_DOGS, CONF_MODULES
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES
from custom_components.pawcontrol.exceptions import ConfigurationError
from custom_components.pawcontrol.setup.validation import (
    _extract_enabled_modules,
    _validate_profile,
    async_validate_entry_config,
)
from custom_components.pawcontrol.types import DogConfigData

pytestmark = pytest.mark.unit


@pytest.fixture
def base_dog_config() -> DogConfigData:
    """Return a baseline dog configuration payload for validation tests."""
    return {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        CONF_MODULES: {
            "gps": True,
            "feeding": True,
            "health": False,
        },
    }


def _build_entry(
    config_entry_factory: Callable[..., ConfigEntry],
    *,
    dogs_payload: object,
    options: Mapping[str, object] | None = None,
) -> ConfigEntry:
    """Build a config entry for setup validation tests."""
    return config_entry_factory(
        data={CONF_DOGS: dogs_payload},
        options=options or {"entity_profile": "standard"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dogs_payload", "expected_modules"),
    [
        pytest.param([], frozenset(), id="empty-list"),
        pytest.param(None, frozenset(), id="none-normalizes-empty"),
        pytest.param(
            [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    CONF_MODULES: {
                        "gps": True,
                        "feeding": True,
                        "health": False,
                    },
                },
            ],
            frozenset({"gps", "feeding"}),
            id="single-dog-modules",
        ),
    ],
)
async def test_async_validate_entry_config_matrix_success(
    config_entry_factory: Callable[..., ConfigEntry],
    dogs_payload: object,
    expected_modules: frozenset[str],
) -> None:
    """Validation should normalize common valid payload shapes."""
    dogs, profile, modules = await async_validate_entry_config(
        _build_entry(config_entry_factory, dogs_payload=dogs_payload)
    )

    assert profile == "standard"
    assert modules == expected_modules
    assert isinstance(dogs, list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dogs_payload", "expected_error"),
    [
        pytest.param("invalid", "must be a list", id="dogs-not-list"),
        pytest.param(["not_a_dict"], "must be mappings", id="dog-not-mapping"),
        pytest.param(
            [{"dog_name": "Buddy"}],
            "must include",
            id="missing-dog-id",
        ),
    ],
)
async def test_async_validate_entry_config_matrix_errors(
    config_entry_factory: Callable[..., ConfigEntry],
    dogs_payload: object,
    expected_error: str,
) -> None:
    """Validation should reject malformed dog payloads with clear errors."""
    with pytest.raises(ConfigurationError, match=expected_error):
        await async_validate_entry_config(
            _build_entry(config_entry_factory, dogs_payload=dogs_payload)
        )


@pytest.mark.parametrize(
    ("raw_profile", "expected_profile"),
    [
        pytest.param("standard", "standard", id="standard"),
        pytest.param(None, "standard", id="none-fallback"),
        pytest.param(123, "standard", id="non-string-fallback"),
        pytest.param("unknown_profile", "standard", id="unknown-fallback"),
        pytest.param(..., "standard", id="missing-option"),
    ],
)
def test_validate_profile_matrix(
    config_entry_factory: Callable[..., ConfigEntry],
    raw_profile: object,
    expected_profile: str,
) -> None:
    """Profile validation should preserve known values and fallback safely."""
    options = (
        {}
        if raw_profile is ...
        else {
            "entity_profile": raw_profile,
        }
    )
    entry = _build_entry(
        config_entry_factory,
        dogs_payload=[],
        options=options,
    )

    profile = _validate_profile(entry)
    assert profile == expected_profile


def test_validate_profile_preserves_first_non_standard_profile(
    config_entry_factory: Callable[..., ConfigEntry],
) -> None:
    """Known non-standard profile values should roundtrip unchanged."""
    known_profile = next(
        profile for profile in ENTITY_PROFILES if profile != "standard"
    )
    entry = _build_entry(
        config_entry_factory,
        dogs_payload=[],
        options={"entity_profile": known_profile},
    )

    assert _validate_profile(entry) == known_profile


@pytest.mark.parametrize(
    ("dogs_config", "expected_modules"),
    [
        pytest.param([], frozenset(), id="empty"),
        pytest.param(
            [{"dog_id": "buddy", "dog_name": "Buddy"}],
            frozenset(),
            id="without-modules",
        ),
        pytest.param(
            [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    CONF_MODULES: "invalid",
                },
            ],
            frozenset(),
            id="invalid-modules-type",
        ),
        pytest.param(
            [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    CONF_MODULES: {
                        "gps": 1,
                        "feeding": 0,
                        "health": False,
                    },
                },
            ],
            frozenset({"gps"}),
            id="truthy-filtering",
        ),
        pytest.param(
            [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    CONF_MODULES: {
                        "gps": True,
                        "unknown_module": True,
                    },
                },
            ],
            frozenset({"gps"}),
            id="unknown-module-filtered",
        ),
        pytest.param(
            [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    CONF_MODULES: {
                        "gps": True,
                        "feeding": True,
                        "health": False,
                        "walk": True,
                    },
                },
                {
                    "dog_id": "max",
                    "dog_name": "Max",
                    CONF_MODULES: {
                        "gps": False,
                        "feeding": True,
                        "notifications": True,
                    },
                },
            ],
            frozenset({"gps", "feeding", "walk", "notifications"}),
            id="multi-dog-aggregate",
        ),
    ],
)
def test_extract_enabled_modules_matrix(
    dogs_config: list[DogConfigData] | list[Mapping[str, object]],
    expected_modules: frozenset[str],
) -> None:
    """Module extraction should normalize and aggregate enabled modules."""
    modules = _extract_enabled_modules(dogs_config)  # type: ignore[arg-type]
    assert modules == expected_modules
