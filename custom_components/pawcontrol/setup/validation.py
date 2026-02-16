"""Configuration validation for PawControl setup.

Extracted from __init__.py to improve testability and maintainability.
Handles validation of dogs configuration, modules, and profiles.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
from typing import TYPE_CHECKING

from ..const import CONF_DOGS, CONF_MODULES
from ..entity_factory import ENTITY_PROFILES
from ..exceptions import ConfigurationError
from ..types import DogConfigData, ensure_dog_config_data

if TYPE_CHECKING:
  from ..types import PawControlConfigEntry  # noqa: E111

_LOGGER = logging.getLogger(__name__)


async def async_validate_entry_config(
  entry: PawControlConfigEntry,
) -> tuple[list[DogConfigData], str, frozenset[str]]:
  """Validate and normalize config entry data.

  Args:
      entry: Config entry to validate

  Returns:
      Tuple of (dogs_config, profile, enabled_modules)

  Raises:
      ConfigurationError: If validation fails

  Example:
      >>> dogs, profile, modules = await async_validate_entry_config(entry)
      >>> len(dogs)
      2
      >>> profile
      'standard'
  """  # noqa: E111
  # Validate dogs configuration  # noqa: E114
  dogs_config = await _async_validate_dogs_config(entry)  # noqa: E111

  # Validate and normalize profile  # noqa: E114
  profile = _validate_profile(entry)  # noqa: E111

  # Extract enabled modules  # noqa: E114
  enabled_modules = _extract_enabled_modules(dogs_config)  # noqa: E111

  _LOGGER.debug(  # noqa: E111
    "Config validation complete: %d dogs, profile='%s', %d modules enabled",
    len(dogs_config),
    profile,
    len(enabled_modules),
  )

  return dogs_config, profile, enabled_modules  # noqa: E111


async def _async_validate_dogs_config(
  entry: PawControlConfigEntry,
) -> list[DogConfigData]:
  """Validate dogs configuration from entry data.

  Args:
      entry: Config entry containing dogs data

  Returns:
      List of validated dog configurations

  Raises:
      ConfigurationError: If dogs configuration is invalid
  """  # noqa: E111
  dogs_config_raw = entry.data.get(CONF_DOGS, [])  # noqa: E111
  if dogs_config_raw is None:  # noqa: E111
    dogs_config_raw = []

  dogs_config: list[DogConfigData] = []  # noqa: E111

  if not isinstance(dogs_config_raw, list):  # noqa: E111
    raise ConfigurationError(
      "dogs_configuration",
      type(dogs_config_raw).__name__,
      "Dogs configuration must be a list",
    )

  for i, dog in enumerate(dogs_config_raw):  # noqa: E111
    if not isinstance(dog, Mapping):
      raise ConfigurationError(  # noqa: E111
        f"dog_config_{i}",
        dog,
        "Dog configuration entries must be mappings",
      )

    normalised = ensure_dog_config_data(dog)
    if normalised is None:
      raise ConfigurationError(  # noqa: E111
        f"dog_config_{i}",
        dog,
        (
          "Invalid dog configuration: each entry must include "
          "non-empty dog_id and dog_name"
        ),
      )
    dogs_config.append(normalised)

  if not dogs_config:  # noqa: E111
    _LOGGER.debug(
      "No dogs configured for entry %s; continuing without dog-specific entities",
      entry.entry_id,
    )

  return dogs_config  # noqa: E111


def _validate_profile(entry: PawControlConfigEntry) -> str:
  """Validate and normalize entity profile.

  Args:
      entry: Config entry containing profile option

  Returns:
      Validated profile name (defaults to 'standard')
  """  # noqa: E111
  profile_raw = entry.options.get("entity_profile", "standard")  # noqa: E111
  if profile_raw is None:  # noqa: E111
    profile_raw = "standard"

  profile = profile_raw if isinstance(profile_raw, str) else str(profile_raw)  # noqa: E111

  if profile not in ENTITY_PROFILES:  # noqa: E111
    _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
    profile = "standard"

  return profile  # noqa: E111


def _extract_enabled_modules(dogs_config: Sequence[DogConfigData]) -> frozenset[str]:
  """Extract enabled modules from dogs configuration.

  Args:
      dogs_config: List of dog configurations

  Returns:
      Set of enabled module names
  """  # noqa: E111
  from ..const import ALL_MODULES  # noqa: E111

  enabled_modules: set[str] = set()  # noqa: E111
  unknown_modules: set[str] = set()  # noqa: E111

  for dog in dogs_config:  # noqa: E111
    modules_config = dog.get(CONF_MODULES)
    if modules_config is None:
      continue  # noqa: E111

    if not isinstance(modules_config, Mapping):
      _LOGGER.warning(  # noqa: E111
        "Ignoring modules for dog %s because configuration is not a mapping",
        dog.get("dog_id", "<unknown>"),
      )
      continue  # noqa: E111

    for module_name, enabled in modules_config.items():
      if not enabled:  # noqa: E111
        continue

      if module_name not in ALL_MODULES:  # noqa: E111
        unknown_modules.add(module_name)
        continue

      enabled_modules.add(module_name)  # noqa: E111

  if unknown_modules:  # noqa: E111
    _LOGGER.warning(
      "Ignoring unknown PawControl modules: %s",
      ", ".join(sorted(unknown_modules)),
    )

  return frozenset(enabled_modules)  # noqa: E111
