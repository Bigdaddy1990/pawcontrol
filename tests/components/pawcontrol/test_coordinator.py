"""Tests for the PawControl data coordinator update interval logic."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_EXTERNAL_INTEGRATIONS,
    CONF_GPS_UPDATE_INTERVAL,
    DOMAIN,
    MAX_IDLE_POLL_INTERVAL,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _create_entry(
    hass: HomeAssistant,
    *,
    dogs: Iterable[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    """Create a mock config entry with the provided dogs and options."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: list(dogs) if dogs is not None else []},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


async def test_update_interval_without_dogs_uses_minimal(hass: HomeAssistant) -> None:
    """Ensure the coordinator falls back to the minimal interval when no dogs exist."""

    entry = _create_entry(hass)
    coordinator = PawControlCoordinator(hass, entry, async_get_clientsession(hass))

    assert coordinator.update_interval.total_seconds() == UPDATE_INTERVALS["minimal"]


async def test_update_interval_balanced_for_medium_complexity(
    hass: HomeAssistant,
) -> None:
    """Verify medium complexity dog setups pick the balanced refresh cadence."""

    dogs = [
        {
            CONF_DOG_ID: "dog_1",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_HEALTH: True,
                MODULE_WALK: True,
            },
        },
        {
            CONF_DOG_ID: "dog_2",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_HEALTH: True,
                MODULE_NOTIFICATIONS: True,
            },
        },
        {
            CONF_DOG_ID: "dog_3",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_NOTIFICATIONS: True,
            },
        },
    ]

    entry = _create_entry(hass, dogs=dogs)
    coordinator = PawControlCoordinator(hass, entry, async_get_clientsession(hass))

    assert coordinator.update_interval.total_seconds() == UPDATE_INTERVALS["balanced"]


async def test_update_interval_real_time_for_high_complexity(
    hass: HomeAssistant,
) -> None:
    """Ensure very complex setups keep the fastest refresh interval."""

    dogs = [
        {
            CONF_DOG_ID: f"dog_{index}",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_NOTIFICATIONS: True,
            },
        }
        for index in range(1, 5)
    ]

    entry = _create_entry(hass, dogs=dogs)
    coordinator = PawControlCoordinator(hass, entry, async_get_clientsession(hass))

    assert coordinator.update_interval.total_seconds() == UPDATE_INTERVALS["real_time"]


async def test_update_interval_honors_gps_option(hass: HomeAssistant) -> None:
    """The GPS update interval option should override the automatic calculation."""

    entry = _create_entry(
        hass,
        dogs=[{CONF_DOG_ID: "gps_dog", "modules": {MODULE_GPS: True}}],
        options={CONF_GPS_UPDATE_INTERVAL: 45},
    )
    coordinator = PawControlCoordinator(hass, entry, async_get_clientsession(hass))

    assert coordinator.update_interval.total_seconds() == 45


async def test_update_interval_capped_for_idle_configs(hass: HomeAssistant) -> None:
    """Ensure idle configurations respect the platinum 15 minute ceiling."""

    entry = _create_entry(
        hass,
        dogs=[{CONF_DOG_ID: "gps_dog", "modules": {MODULE_GPS: True}}],
        options={CONF_GPS_UPDATE_INTERVAL: 3600},
    )

    coordinator = PawControlCoordinator(hass, entry, async_get_clientsession(hass))

    assert coordinator.update_interval.total_seconds() == MAX_IDLE_POLL_INTERVAL


async def test_coordinator_external_api_option(hass: HomeAssistant) -> None:
    """External integrations option should toggle coordinator API usage."""

    enabled_entry = _create_entry(
        hass,
        options={CONF_EXTERNAL_INTEGRATIONS: True},
    )
    coordinator_enabled = PawControlCoordinator(
        hass, enabled_entry, async_get_clientsession(hass)
    )

    assert coordinator_enabled.use_external_api is True

    disabled_entry = _create_entry(hass)
    coordinator_disabled = PawControlCoordinator(
        hass, disabled_entry, async_get_clientsession(hass)
    )

    assert coordinator_disabled.use_external_api is False


async def test_async_update_data_propagates_update_failed(
    hass: HomeAssistant,
) -> None:
    """Coordinator should surface UpdateFailed errors when runtime fetches fail."""

    dogs = [
        {
            CONF_DOG_ID: "failure_dog",
            "modules": {MODULE_FEEDING: True},
        }
    ]

    entry = _create_entry(hass, dogs=dogs)
    coordinator = PawControlCoordinator(hass, entry, async_get_clientsession(hass))

    await coordinator.async_prepare_entry()

    with (
        patch.object(
            coordinator._runtime,
            "execute_cycle",
            AsyncMock(side_effect=UpdateFailed("boom")),
        ) as mock_execute,
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    mock_execute.assert_awaited_once()
