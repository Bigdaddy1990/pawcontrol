"""Shared data accessor helpers for the PawControl coordinator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, TypeGuard, cast, overload

from .types import (
  CoordinatorDataPayload,
  CoordinatorDogData,
  CoordinatorModuleLookupResult,
  CoordinatorModuleState,
  CoordinatorRuntimeManagers,
  CoordinatorTypedModuleName,
  CoordinatorUntypedModuleState,
  DogConfigData,
)

_TYPED_MODULES: frozenset[CoordinatorTypedModuleName] = frozenset(
  {"feeding", "garden", "geofencing", "gps", "health", "walk", "weather"},
)

if TYPE_CHECKING:  # pragma: no cover - import for typing only
  from .coordinator_support import DogConfigRegistry  # noqa: E111


class CoordinatorDataAccessMixin:
  """Provide read helpers for coordinator managed state."""  # noqa: E111

  registry: DogConfigRegistry  # noqa: E111
  _data: CoordinatorDataPayload  # noqa: E111
  runtime_managers: CoordinatorRuntimeManagers  # noqa: E111

  def get_dog_config(self, dog_id: str) -> DogConfigData | None:  # noqa: E111
    """Return the configuration payload for a dog."""

    return self.registry.get(dog_id)

  def get_dog_ids(self) -> list[str]:  # noqa: E111
    """Return all configured dog identifiers."""

    return self.registry.ids()

  def get_configured_dog_ids(self) -> list[str]:  # noqa: E111
    """Return helper alias for existing dog identifiers."""

    return self.get_dog_ids()

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:  # noqa: E111
    """Return the cached runtime payload for a dog."""

    return self._data.get(dog_id)

  @overload  # noqa: E111
  def get_module_data(  # noqa: E111
    self,
    dog_id: str,
    module: Literal[
      "feeding",
      "garden",
      "geofencing",
      "gps",
      "health",
      "walk",
      "weather",
    ],
  ) -> CoordinatorModuleState:
    """Return coordinator data for a typed module."""

  @overload  # noqa: E111
  def get_module_data(  # noqa: E111
    self,
    dog_id: str,
    module: str,
  ) -> CoordinatorModuleLookupResult:
    """Return cached data for a module without strict typing."""

  def get_module_data(  # noqa: E111
    self,
    dog_id: str,
    module: str,
  ) -> CoordinatorModuleLookupResult:
    """Return cached data for a specific module."""

    if not isinstance(module, str):
      return cast(CoordinatorUntypedModuleState, {})  # noqa: E111

    dog_data = self._data.get(dog_id)
    if not dog_data:
      return (  # noqa: E111
        cast(CoordinatorModuleState, {"status": "unknown"})
        if CoordinatorDataAccessMixin._is_typed_module(module)
        else cast(CoordinatorUntypedModuleState, {})
      )

    module_data = dog_data.get(module)
    if CoordinatorDataAccessMixin._is_typed_module(module):
      if isinstance(module_data, Mapping):  # noqa: E111
        return cast(CoordinatorModuleState, module_data)
      return cast(CoordinatorModuleState, {"status": "unknown"})  # noqa: E111

    if isinstance(module_data, Mapping):
      return cast(CoordinatorUntypedModuleState, module_data)  # noqa: E111

    return cast(CoordinatorUntypedModuleState, {})

  @staticmethod  # noqa: E111
  def _is_typed_module(module: str) -> TypeGuard[CoordinatorTypedModuleName]:  # noqa: E111
    """Return True if ``module`` stores structured coordinator state."""

    return module in _TYPED_MODULES

  def get_configured_dog_name(self, dog_id: str) -> str | None:  # noqa: E111
    """Return the configured display name for a dog."""

    return self.registry.get_name(dog_id)

  def get_dog_info(self, dog_id: str) -> DogConfigData:  # noqa: E111
    """Return the latest dog info payload, falling back to config."""

    dog_data = self.get_dog_data(dog_id)
    if dog_data is not None:
      dog_info = dog_data.get("dog_info")  # noqa: E111
      if isinstance(dog_info, Mapping):  # noqa: E111
        return cast(DogConfigData, dog_info)

    config = self.registry.get(dog_id)
    if config is not None:
      return config  # noqa: E111
    return cast(DogConfigData, {})
