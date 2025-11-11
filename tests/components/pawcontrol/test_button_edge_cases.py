"""Regression tests covering PawControl button edge cases."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.button import (
    PawControlEndWalkButton,
    PawControlStartWalkButton,
)
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    MODULE_WALK,
    SERVICE_END_WALK,
    SERVICE_START_WALK,
)
from custom_components.pawcontrol.exceptions import (
    WalkAlreadyInProgressError,
    WalkNotInProgressError,
)
from custom_components.pawcontrol.types import WALK_IN_PROGRESS_FIELD
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util


def _build_mock_coordinator(flag: Any) -> Mock:
    """Return a coordinator stub exposing walk payload data."""

    coordinator = Mock()
    coordinator.available = True
    coordinator.config_entry = Mock()
    coordinator.config_entry.entry_id = "test-entry"

    walk_payload = {
        WALK_IN_PROGRESS_FIELD: flag,
        "current_walk_id": "walk-1234",
        "current_walk_start": dt_util.utcnow().isoformat(),
        "last_walk": (dt_util.utcnow() - timedelta(hours=2)).isoformat(),
    }

    dog_data = {
        MODULE_WALK: walk_payload,
        "dog_info": {"dog_id": "test_dog", "dog_name": "Test Dog"},
    }

    coordinator.data = {"test_dog": dog_data}
    coordinator.get_dog_data = Mock(side_effect=lambda dog_id: coordinator.data[dog_id])
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_request_selective_refresh = AsyncMock()

    return coordinator


@pytest.mark.parametrize(
    ("flag", "start_available", "end_available"),
    [
        (False, True, False),
        (True, False, True),
        ("false", True, False),
        ("TRUE", False, True),
        ("0", True, False),
        ("1", False, True),
        (None, True, False),
    ],
)
def test_walk_button_availability(flag: Any, start_available: bool, end_available: bool) -> None:
    """Walk buttons normalise module flags before reporting availability."""

    coordinator = _build_mock_coordinator(flag)

    start_button = PawControlStartWalkButton(coordinator, "test_dog", "Test Dog")
    end_button = PawControlEndWalkButton(coordinator, "test_dog", "Test Dog")

    assert start_button.available is start_available
    assert end_button.available is end_available


@pytest.mark.parametrize("raw_flag", ["false", "0", None])
async def test_start_walk_allows_falsey_strings(
    hass: HomeAssistant, raw_flag: Any
) -> None:
    """The start button should treat false-like flags as no active walk."""

    coordinator = _build_mock_coordinator(raw_flag)
    start_button = PawControlStartWalkButton(coordinator, "test_dog", "Test Dog")
    start_button.hass = hass

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
        await start_button.async_press()

    mock_call.assert_awaited_once_with(
        "pawcontrol",
        SERVICE_START_WALK,
        {ATTR_DOG_ID: "test_dog", "label": "Manual walk"},
        blocking=False,
    )


@pytest.mark.parametrize("raw_flag", ["true", "TRUE", "yes", 1])
async def test_start_walk_blocks_truthy_strings(
    hass: HomeAssistant, raw_flag: Any
) -> None:
    """The start button should reject walk starts while a walk is active."""

    coordinator = _build_mock_coordinator(raw_flag)
    start_button = PawControlStartWalkButton(coordinator, "test_dog", "Test Dog")
    start_button.hass = hass

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call, pytest.raises(
        HomeAssistantError
    ) as captured:
        await start_button.async_press()

    mock_call.assert_not_called()
    assert isinstance(captured.value.__cause__, WalkAlreadyInProgressError)


@pytest.mark.parametrize("raw_flag", [False, "false", "0", None])
async def test_end_walk_blocks_falsey_strings(
    hass: HomeAssistant, raw_flag: Any
) -> None:
    """Ending a walk with false-like flags should raise a typed error."""

    coordinator = _build_mock_coordinator(raw_flag)
    end_button = PawControlEndWalkButton(coordinator, "test_dog", "Test Dog")
    end_button.hass = hass

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call, pytest.raises(
        HomeAssistantError
    ) as captured:
        await end_button.async_press()

    mock_call.assert_not_called()
    assert isinstance(captured.value.__cause__, WalkNotInProgressError)


@pytest.mark.parametrize("raw_flag", [True, "true", "1", "active"])
async def test_end_walk_allows_truthy_strings(
    hass: HomeAssistant, raw_flag: Any
) -> None:
    """Ending a walk should respect normalised truthy flags."""

    coordinator = _build_mock_coordinator(raw_flag)
    end_button = PawControlEndWalkButton(coordinator, "test_dog", "Test Dog")
    end_button.hass = hass

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
        await end_button.async_press()

    mock_call.assert_awaited_once_with(
        "pawcontrol",
        SERVICE_END_WALK,
        {ATTR_DOG_ID: "test_dog"},
        blocking=False,
    )


async def test_end_walk_reports_unknown_walk_identifier(hass: HomeAssistant) -> None:
    """Ensure unknown identifiers fall back to the Home Assistant default."""

    coordinator = _build_mock_coordinator(True)
    coordinator.data["test_dog"][MODULE_WALK]["current_walk_id"] = 1234

    end_button = PawControlEndWalkButton(coordinator, "test_dog", "Test Dog")
    end_button.hass = hass

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
        await end_button.async_press()

    mock_call.assert_awaited_once_with(
        "pawcontrol", SERVICE_END_WALK, {ATTR_DOG_ID: "test_dog"}, blocking=False
    )
    assert end_button.extra_state_attributes["button_type"] == "end_walk"


async def test_start_walk_raises_with_unknown_flag(hass: HomeAssistant) -> None:
    """Unknown flag values should default to safe behaviour while logging details."""

    coordinator = _build_mock_coordinator({"unexpected": "value"})
    start_button = PawControlStartWalkButton(coordinator, "test_dog", "Test Dog")
    start_button.hass = hass

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
        await start_button.async_press()

    mock_call.assert_awaited_once_with(
        "pawcontrol",
        SERVICE_START_WALK,
        {ATTR_DOG_ID: "test_dog", "label": "Manual walk"},
        blocking=False,
    )


async def test_start_walk_reports_unknown_walk_id(hass: HomeAssistant) -> None:
    """Ensure non-string identifiers fall back to ``STATE_UNKNOWN`` in errors."""

    coordinator = _build_mock_coordinator(True)
    coordinator.data["test_dog"][MODULE_WALK]["current_walk_id"] = 12
    coordinator.data["test_dog"][MODULE_WALK]["current_walk_start"] = dt_util.utcnow()

    start_button = PawControlStartWalkButton(coordinator, "test_dog", "Test Dog")
    start_button.hass = hass

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call, pytest.raises(
        HomeAssistantError
    ) as captured:
        await start_button.async_press()

    mock_call.assert_not_called()
    cause = captured.value.__cause__
    assert isinstance(cause, WalkAlreadyInProgressError)
    assert cause.walk_id == STATE_UNKNOWN
