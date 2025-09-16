"""Tests for PawControl service handlers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.pawcontrol import services as services_module
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.services import (
    SERVICE_END_WALK,
    SERVICE_START_WALK,
)
from custom_components.pawcontrol.walk_manager import WeatherCondition
from homeassistant.core import HomeAssistant, ServiceCall


@pytest.fixture
def coordinator_mock() -> SimpleNamespace:
    """Return a coordinator-like object with async mocks."""

    return SimpleNamespace(
        walk_manager=AsyncMock(),
        async_request_refresh=AsyncMock(),
        feeding_manager=None,
        data_manager=None,
    )


async def _register_services(
    hass: HomeAssistant,
    coordinator: SimpleNamespace,
) -> dict[tuple[str, str], Callable[[ServiceCall], Awaitable[None]]]:
    """Register PawControl services and return the handlers."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinator"] = coordinator

    registered: dict[tuple[str, str], Callable[[ServiceCall], Awaitable[None]]] = {}

    def register(
        self,
        domain: str,
        service: str,
        handler: Callable[[ServiceCall], Awaitable[None]],
        schema: object | None = None,
    ) -> None:
        registered[(domain, service)] = handler

    with patch.object(
        type(hass.services), "async_register", side_effect=register, autospec=True
    ):
        await services_module.async_setup_services(hass)

    return registered


@pytest.mark.asyncio
async def test_start_walk_service_passes_metadata(
    hass: HomeAssistant,
    coordinator_mock: SimpleNamespace,
) -> None:
    """Verify the walk start service forwards optional metadata correctly."""

    handlers = await _register_services(hass, coordinator_mock)
    handler = handlers[(DOMAIN, SERVICE_START_WALK)]

    coordinator_mock.walk_manager.async_start_walk.return_value = "session-1"

    await handler(
        ServiceCall(
            hass,
            DOMAIN,
            SERVICE_START_WALK,
            {
                "dog_id": "doggo",
                "walker": "Alex",
                "weather": "cloudy",
                "leash_used": False,
            },
        )
    )

    await_args = coordinator_mock.walk_manager.async_start_walk.await_args
    assert await_args.kwargs["dog_id"] == "doggo"
    assert await_args.kwargs["walk_type"] == "manual"
    assert await_args.kwargs["walker"] == "Alex"
    assert await_args.kwargs["leash_used"] is False
    assert await_args.kwargs["weather"] == WeatherCondition.CLOUDY


@pytest.mark.asyncio
async def test_end_walk_service_updates_stats(
    hass: HomeAssistant,
    coordinator_mock: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensure the end walk service stores metadata and logs summary."""

    handlers = await _register_services(hass, coordinator_mock)
    handler = handlers[(DOMAIN, SERVICE_END_WALK)]

    coordinator_mock.walk_manager.async_end_walk.return_value = {
        "distance": 1500.0,
        "duration": 900.0,
    }

    caplog.set_level(logging.INFO, logger="custom_components.pawcontrol.services")

    await handler(
        ServiceCall(
            hass,
            DOMAIN,
            SERVICE_END_WALK,
            {
                "dog_id": "doggo",
                "notes": "Great walk",
                "dog_weight_kg": 18.5,
            },
        )
    )

    await_args = coordinator_mock.walk_manager.async_end_walk.await_args
    assert await_args.kwargs["dog_id"] == "doggo"
    assert await_args.kwargs["notes"] == "Great walk"
    assert await_args.kwargs["dog_weight_kg"] == 18.5
    coordinator_mock.async_request_refresh.assert_awaited_once()

    assert any(
        "Ended walk for doggo" in message for message in caplog.messages
    ), "Expected summary log message was not emitted"
