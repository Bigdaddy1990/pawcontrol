"""Shared data accessor helpers for the PawControl coordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .coordinator_support import DogConfigRegistry


class CoordinatorDataAccessMixin:
    """Provide read helpers for coordinator managed state."""

    registry: "DogConfigRegistry"
    _data: dict[str, dict[str, Any]]

    def get_dog_config(self, dog_id: str) -> Any:
        """Return the configuration payload for a dog."""

        return self.registry.get(dog_id)

    def get_dog_ids(self) -> list[str]:
        """Return all configured dog identifiers."""

        return self.registry.ids()

    def get_configured_dog_ids(self) -> list[str]:
        """Return helper alias for existing dog identifiers."""

        return self.get_dog_ids()

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        """Return the cached runtime payload for a dog."""

        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        """Return cached data for a specific module."""

        return self._data.get(dog_id, {}).get(module, {})

    def get_configured_dog_name(self, dog_id: str) -> str | None:
        """Return the configured display name for a dog."""

        return self.registry.get_name(dog_id)

    def get_dog_info(self, dog_id: str) -> dict[str, Any]:
        """Return the latest dog info payload, falling back to config."""

        dog_data = self.get_dog_data(dog_id)
        if dog_data and isinstance(dog_data.get("dog_info"), dict):
            return dog_data["dog_info"]
        return self.registry.get(dog_id) or {}

