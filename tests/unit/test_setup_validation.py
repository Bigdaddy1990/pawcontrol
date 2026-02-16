"""Tests for setup.validation module.

Tests configuration validation logic extracted from __init__.py
"""

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
  """Create a mock config entry."""  # noqa: E111
  entry = MagicMock()  # noqa: E111
  entry.entry_id = "test_entry_id"  # noqa: E111
  entry.data = {  # noqa: E111
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
  entry.options = {"entity_profile": "standard"}  # noqa: E111
  return entry  # noqa: E111


@pytest.mark.asyncio
async def test_async_validate_entry_config_success(mock_config_entry):
  """Test successful config validation."""  # noqa: E111
  dogs, profile, modules = await async_validate_entry_config(mock_config_entry)  # noqa: E111

  assert len(dogs) == 1  # noqa: E111
  assert dogs[0]["dog_id"] == "buddy"  # noqa: E111
  assert dogs[0]["dog_name"] == "Buddy"  # noqa: E111
  assert profile == "standard"  # noqa: E111
  assert "gps" in modules  # noqa: E111
  assert "feeding" in modules  # noqa: E111
  assert "health" not in modules  # noqa: E111


@pytest.mark.asyncio
async def test_async_validate_entry_config_empty_dogs(mock_config_entry):
  """Test validation with no dogs configured."""  # noqa: E111
  mock_config_entry.data = {CONF_DOGS: []}  # noqa: E111

  dogs, profile, modules = await async_validate_entry_config(mock_config_entry)  # noqa: E111

  assert len(dogs) == 0  # noqa: E111
  assert profile == "standard"  # noqa: E111
  assert len(modules) == 0  # noqa: E111


@pytest.mark.asyncio
async def test_async_validate_entry_config_invalid_dogs_type(mock_config_entry):
  """Test validation fails with invalid dogs type."""  # noqa: E111
  mock_config_entry.data = {CONF_DOGS: "invalid"}  # noqa: E111

  with pytest.raises(ConfigurationError, match="must be a list"):  # noqa: E111
    await async_validate_entry_config(mock_config_entry)


@pytest.mark.asyncio
async def test_async_validate_entry_config_invalid_dog_entry(mock_config_entry):
  """Test validation fails with invalid dog entry."""  # noqa: E111
  mock_config_entry.data = {CONF_DOGS: ["not_a_dict"]}  # noqa: E111

  with pytest.raises(ConfigurationError, match="must be mappings"):  # noqa: E111
    await async_validate_entry_config(mock_config_entry)


@pytest.mark.asyncio
async def test_async_validate_entry_config_missing_dog_id(mock_config_entry):
  """Test validation fails with missing dog_id."""  # noqa: E111
  mock_config_entry.data = {CONF_DOGS: [{"dog_name": "Buddy"}]}  # noqa: E111

  with pytest.raises(ConfigurationError, match="must include"):  # noqa: E111
    await async_validate_entry_config(mock_config_entry)


def test_validate_profile_standard(mock_config_entry):
  """Test profile validation with standard profile."""  # noqa: E111
  profile = _validate_profile(mock_config_entry)  # noqa: E111
  assert profile == "standard"  # noqa: E111


def test_validate_profile_unknown_fallback(mock_config_entry):
  """Test profile validation falls back to standard for unknown profile."""  # noqa: E111
  mock_config_entry.options = {"entity_profile": "unknown_profile"}  # noqa: E111

  profile = _validate_profile(mock_config_entry)  # noqa: E111
  assert profile == "standard"  # noqa: E111


def test_validate_profile_none_fallback(mock_config_entry):
  """Test profile validation falls back to standard for None."""  # noqa: E111
  mock_config_entry.options = {"entity_profile": None}  # noqa: E111

  profile = _validate_profile(mock_config_entry)  # noqa: E111
  assert profile == "standard"  # noqa: E111


def test_extract_enabled_modules_success():
  """Test extracting enabled modules."""  # noqa: E111
  dogs_config: list[DogConfigData] = [  # noqa: E111
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

  modules = _extract_enabled_modules(dogs_config)  # noqa: E111

  assert "gps" in modules  # noqa: E111
  assert "feeding" in modules  # noqa: E111
  assert "walk" in modules  # noqa: E111
  assert "notifications" in modules  # noqa: E111
  assert "health" not in modules  # noqa: E111


def test_extract_enabled_modules_empty():
  """Test extracting modules from empty dogs list."""  # noqa: E111
  modules = _extract_enabled_modules([])  # noqa: E111
  assert len(modules) == 0  # noqa: E111


def test_extract_enabled_modules_no_modules_config():
  """Test extracting modules when no modules configured."""  # noqa: E111
  dogs_config: list[DogConfigData] = [  # noqa: E111
    {
      "dog_id": "buddy",
      "dog_name": "Buddy",
    },
  ]

  modules = _extract_enabled_modules(dogs_config)  # noqa: E111
  assert len(modules) == 0  # noqa: E111


def test_extract_enabled_modules_invalid_modules_type():
  """Test extracting modules with invalid modules type."""  # noqa: E111
  dogs_config: list[Mapping] = [  # noqa: E111
    {
      "dog_id": "buddy",
      "dog_name": "Buddy",
      CONF_MODULES: "invalid",  # Should be dict
    },
  ]

  modules = _extract_enabled_modules(dogs_config)  # type: ignore  # noqa: E111
  assert len(modules) == 0  # noqa: E111


def test_extract_enabled_modules_unknown_module():
  """Test extracting modules filters unknown modules."""  # noqa: E111
  dogs_config: list[DogConfigData] = [  # noqa: E111
    {
      "dog_id": "buddy",
      "dog_name": "Buddy",
      CONF_MODULES: {
        "gps": True,
        "unknown_module": True,  # Should be filtered
      },
    },
  ]

  modules = _extract_enabled_modules(dogs_config)  # noqa: E111

  assert "gps" in modules  # noqa: E111
  assert "unknown_module" not in modules  # noqa: E111
