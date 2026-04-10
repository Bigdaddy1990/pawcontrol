"""Shared fixtures for PawControl component test modules."""

from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.config_entries import ConfigEntryState
import pytest


@pytest.fixture
def service_runtime_factory(mock_hass: SimpleNamespace):
    """Create reusable runtime/coordinator doubles for service-layer tests."""

    def _factory(
        *,
        entry_id: str = "entry-1",
        runtime_managers: SimpleNamespace | None = None,
        dog_ids: set[str] | None = None,
        dog_config: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        config_entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id=entry_id)
        coordinator = SimpleNamespace(
            hass=mock_hass,
            config_entry=config_entry,
            runtime_managers=runtime_managers or SimpleNamespace(),
            get_dog_config=Mock(return_value=dog_config),
            get_configured_dog_ids=Mock(return_value=dog_ids or set()),
            get_configured_dog_name=Mock(
                return_value=(dog_config or {}).get("name", "Buddy")
            ),
        )
        runtime_data = SimpleNamespace(performance_stats={}, coordinator=coordinator)
        return runtime_data

    return _factory
