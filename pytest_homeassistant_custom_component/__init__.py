"""Lightweight test stub for ``pytest-homeassistant-custom-component``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from homeassistant.core import ConfigEntry, ConfigEntryState, HomeAssistant

__all__ = ["MockConfigEntry", "enable_custom_integrations"]


class MockConfigEntry(ConfigEntry):
    """Simplified config entry used in PawControl tests."""

    def __init__(
        self,
        *,
        domain: str,
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        title: str | None = None,
        unique_id: str | None = None,
    ) -> None:
        super().__init__(domain=domain, data=data, options=options, title=title)
        if unique_id is not None:
            self.unique_id = unique_id
        self.source = "user"
        self.state = ConfigEntryState.NOT_LOADED
        self._listeners: list[Any] = []

    def add_to_hass(self, hass: HomeAssistant) -> None:  # type: ignore[override]
        super().add_to_hass(hass)
        self.state = ConfigEntryState.NOT_LOADED

    async def async_setup(self, hass: HomeAssistant) -> bool:
        self.state = ConfigEntryState.LOADED
        return True

    async def async_unload(self, hass: HomeAssistant) -> bool:
        self.state = ConfigEntryState.NOT_LOADED
        return True

    def add_update_listener(self, listener: Any) -> None:
        self._listeners.append(listener)


@pytest.fixture
def enable_custom_integrations() -> Iterable[None]:
    """Compatibility fixture to match the upstream helper library."""

    yield
