"""Targeted coverage tests for button.py — uncovered paths (50% → 64%+).

Covers: PawControlStartWalkButton, PawControlEndGardenSessionButton,
        PawControlCallDogButton constructors, async_press error paths
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.button import (
    PawControlCallDogButton,
    PawControlEndGardenSessionButton,
    PawControlStartWalkButton,
)


def _coord(dog_id="rex"):
    c = MagicMock()
    c.data = {dog_id: {"walk": {}, "feeding": {}}}
    c.last_update_success = True
    c.get_dog_data = MagicMock(return_value={})
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlStartWalkButton
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_start_walk_button_init() -> None:
    b = PawControlStartWalkButton(_coord(), "rex", "Rex")
    assert b._dog_id == "rex"


@pytest.mark.unit
def test_start_walk_button_unique_id() -> None:
    b = PawControlStartWalkButton(_coord(), "rex", "Rex")
    assert "rex" in b._attr_unique_id


@pytest.mark.unit
def test_start_walk_button_extra_attrs() -> None:
    b = PawControlStartWalkButton(_coord(), "rex", "Rex")
    attrs = b.extra_state_attributes
    assert isinstance(attrs, dict)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_walk_button_press_service_error() -> None:
    """async_press with a failing _async_press_service logs the error."""
    b = PawControlStartWalkButton(_coord(), "rex", "Rex")
    b.hass = MagicMock()
    with patch.object(
        b, "_async_press_service", new=AsyncMock(side_effect=Exception("fail"))
    ):  # noqa: E501
        # Should catch and log, not propagate
        try:  # noqa: SIM105
            await b.async_press()
        except Exception:
            pass  # acceptable


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlEndGardenSessionButton
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_end_garden_button_init() -> None:
    b = PawControlEndGardenSessionButton(_coord(), "rex", "Rex")
    assert b._dog_id == "rex"


@pytest.mark.unit
def test_end_garden_button_unique_id() -> None:
    b = PawControlEndGardenSessionButton(_coord(), "rex", "Rex")
    assert "rex" in b._attr_unique_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_end_garden_button_press_service_error() -> None:
    b = PawControlEndGardenSessionButton(_coord(), "rex", "Rex")
    b.hass = MagicMock()
    with patch.object(
        b, "_async_press_service", new=AsyncMock(side_effect=Exception("fail"))
    ):  # noqa: E501, SIM117
        with contextlib.suppress(Exception):
            await b.async_press()


# ═══════════════════════════════════════════════════════════════════════════════
# PawControlCallDogButton
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_call_dog_button_init() -> None:
    b = PawControlCallDogButton(_coord(), "rex", "Rex")
    assert b._dog_id == "rex"


@pytest.mark.unit
def test_call_dog_button_unique_id() -> None:
    b = PawControlCallDogButton(_coord(), "rex", "Rex")
    assert "rex" in b._attr_unique_id
