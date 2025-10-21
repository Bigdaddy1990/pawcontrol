"""Shared data accessor helpers for the PawControl coordinator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeGuard, cast, overload

from .types import (
    CoordinatorDataPayload,
    CoordinatorDogData,
    CoordinatorModuleState,
    CoordinatorRuntimeManagers,
    CoordinatorTypedModuleName,
)

_TYPED_MODULES: frozenset[CoordinatorTypedModuleName] = frozenset(
    {"feeding", "garden", "geofencing", "gps", "health", "walk", "weather"}
)

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .coordinator_support import DogConfigRegistry
    from .types import DogConfigData


class CoordinatorDataAccessMixin:
    """Provide read helpers for coordinator managed state."""

    registry: DogConfigRegistry
    _data: CoordinatorDataPayload
    runtime_managers: CoordinatorRuntimeManagers

    def get_dog_config(self, dog_id: str) -> DogConfigData | None:
        """Return the configuration payload for a dog."""

        return self.registry.get(dog_id)

    def get_dog_ids(self) -> list[str]:
        """Return all configured dog identifiers."""

        return self.registry.ids()

    def get_configured_dog_ids(self) -> list[str]:
        """Return helper alias for existing dog identifiers."""

        return self.get_dog_ids()

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        """Return the cached runtime payload for a dog."""

        return self._data.get(dog_id)

    @overload
    def get_module_data(
        self, dog_id: str, module: CoordinatorTypedModuleName
    ) -> CoordinatorModuleState:
        """Return coordinator data for a typed module."""

    @overload
    def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any]:
        """Return cached data for a specific module."""

    def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any]:
        """Return cached data for a specific module."""

        if not isinstance(module, str):
            return {}

        dog_data = self._data.get(dog_id)
        if not dog_data:
            return (
                cast(CoordinatorModuleState, {"status": "unknown"})
                if CoordinatorDataAccessMixin._is_typed_module(module)
                else {}
            )

        module_data = dog_data.get(module)
        if CoordinatorDataAccessMixin._is_typed_module(module):
            if isinstance(module_data, Mapping):
                return cast(CoordinatorModuleState, module_data)
            return cast(CoordinatorModuleState, {"status": "unknown"})

        if isinstance(module_data, Mapping):
            return module_data

        return {}

    @staticmethod
    def _is_typed_module(module: str) -> TypeGuard[CoordinatorTypedModuleName]:
        """Return True if ``module`` stores structured coordinator state."""

        return module in _TYPED_MODULES

    def get_configured_dog_name(self, dog_id: str) -> str | None:
        """Return the configured display name for a dog."""

        return self.registry.get_name(dog_id)

    def get_dog_info(self, dog_id: str) -> Mapping[str, Any]:
        """Return the latest dog info payload, falling back to config."""

        dog_data = self.get_dog_data(dog_id)
        if dog_data is not None:
            dog_info = dog_data.get("dog_info")
            if isinstance(dog_info, Mapping):
                return dog_info

        config = self.registry.get(dog_id)
        if config is not None:
            return config
        return {}
