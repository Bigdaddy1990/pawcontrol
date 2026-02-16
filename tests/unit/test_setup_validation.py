"""Tests for setup.validation module.

Tests configuration validation logic extracted from __init__.py
"""
from __future__ import annotations


from collections.abc import Mapping
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.const import CONF_DOGS, CONF_MODULES
from custom_components.pawcontrol.exceptions import ConfigurationError
from custom_components.pawcontrol.setup.validation import (
    _extract_enabled_modules,
    _validate_profile,
    async_validate_entry_config,
)
from custom_components.pawcontrol.types import DogConfigData


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_DOGS: [
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
    }
    entry.options = {"entity_profile": "standard"}
    return entry


@pytest.mark.asyncio
async def test_async_validate_entry_config_success(mock_config_entry):
    """Test successful config validation."""
    dogs, profile, modules = await async_validate_entry_config(mock_config_entry)

    assert len(dogs) == 1
    assert dogs[0]["dog_id"] == "buddy"
    assert dogs[0]["dog_name"] == "Buddy"
    assert profile == "standard"
    assert "gps" in modules
    assert "feeding" in modules
    assert "health" not in modules


@pytest.mark.asyncio
async def test_async_validate_entry_config_empty_dogs(mock_config_entry):
    """Test validation with no dogs configured."""
    mock_config_entry.data = {CONF_DOGS: []}

    dogs, profile, modules = await async_validate_entry_config(mock_config_entry)

    assert len(dogs) == 0
    assert profile == "standard"
    assert len(modules) == 0


@pytest.mark.asyncio
async def test_async_validate_entry_config_invalid_dogs_type(mock_config_entry):
    """Test validation fails with invalid dogs type."""
    mock_config_entry.data = {CONF_DOGS: "invalid"}

    with pytest.raises(ConfigurationError, match="must be a list"):
        await async_validate_entry_config(mock_config_entry)


@pytest.mark.asyncio
async def test_async_validate_entry_config_invalid_dog_entry(mock_config_entry):
    """Test validation fails with invalid dog entry."""
    mock_config_entry.data = {CONF_DOGS: ["not_a_dict"]}

    with pytest.raises(ConfigurationError, match="must be mappings"):
        await async_validate_entry_config(mock_config_entry)


@pytest.mark.asyncio
async def test_async_validate_entry_config_missing_dog_id(mock_config_entry):
    """Test validation fails with missing dog_id."""
    mock_config_entry.data = {CONF_DOGS: [{"dog_name": "Buddy"}]}

    with pytest.raises(ConfigurationError, match="must include"):
        await async_validate_entry_config(mock_config_entry)


def test_validate_profile_standard(mock_config_entry):
    """Test profile validation with standard profile."""
    profile = _validate_profile(mock_config_entry)
    assert profile == "standard"


def test_validate_profile_unknown_fallback(mock_config_entry):
    """Test profile validation falls back to standard for unknown profile."""
    mock_config_entry.options = {"entity_profile": "unknown_profile"}

    profile = _validate_profile(mock_config_entry)
    assert profile == "standard"


def test_validate_profile_none_fallback(mock_config_entry):
    """Test profile validation falls back to standard for None."""
    mock_config_entry.options = {"entity_profile": None}

    profile = _validate_profile(mock_config_entry)
    assert profile == "standard"


def test_extract_enabled_modules_success():
    """Test extracting enabled modules."""
    dogs_config: list[DogConfigData] = [
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
    ]

    modules = _extract_enabled_modules(dogs_config)

    assert "gps" in modules
    assert "feeding" in modules
    assert "walk" in modules
    assert "notifications" in modules
    assert "health" not in modules


def test_extract_enabled_modules_empty():
    """Test extracting modules from empty dogs list."""
    modules = _extract_enabled_modules([])
    assert len(modules) == 0


def test_extract_enabled_modules_no_modules_config():
    """Test extracting modules when no modules configured."""
    dogs_config: list[DogConfigData] = [
        {
            "dog_id": "buddy",
            "dog_name": "Buddy",
        },
    ]

    modules = _extract_enabled_modules(dogs_config)
    assert len(modules) == 0


def test_extract_enabled_modules_invalid_modules_type():
    """Test extracting modules with invalid modules type."""
    dogs_config: list[Mapping] = [
        {
            "dog_id": "buddy",
            "dog_name": "Buddy",
            CONF_MODULES: "invalid",  # Should be dict
        },
    ]

    modules = _extract_enabled_modules(dogs_config)  # type: ignore
    assert len(modules) == 0


def test_extract_enabled_modules_unknown_module():
    """Test extracting modules filters unknown modules."""
    dogs_config: list[DogConfigData] = [
        {
            "dog_id": "buddy",
            "dog_name": "Buddy",
            CONF_MODULES: {
                "gps": True,
                "unknown_module": True,  # Should be filtered
            },
        },
    ]

    modules = _extract_enabled_modules(dogs_config)

    assert "gps" in modules
    assert "unknown_module" not in modules
