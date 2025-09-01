"""Tests for the lightweight FeedingManager."""

from __future__ import annotations

import pytest

import sys
from importlib import util
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch


SPEC = util.spec_from_file_location(
    "feeding_manager",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pawcontrol"
    / "feeding_manager.py",
)
from importlib import util
from pathlib import Path

feeding_manager = util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feeding_manager
SPEC.loader.exec_module(feeding_manager)
FeedingManager = feeding_manager.FeedingManager


@pytest.mark.asyncio
async def test_feeding_manager_returns_consistent_feedings_today() -> None:
    """Ensure feedings_today is always a dict with integer counts."""

    manager = FeedingManager()
    await manager.async_add_feeding("dog", 1.0, meal_type="breakfast")
    await manager.async_add_feeding("dog", 1.0, meal_type="dinner")

    data = await manager.async_get_feeding_data("dog")

    assert isinstance(data["feedings_today"], dict)
    assert data["feedings_today"]["breakfast"] == 1
    assert data["feedings_today"]["dinner"] == 1
    assert data["total_feedings_today"] == 2


@pytest.mark.asyncio
async def test_feeding_manager_empty_history() -> None:
    """Verify empty histories return empty mappings and zero totals."""

    manager = FeedingManager()
    data = await manager.async_get_feeding_data("dog")

    assert data["feedings_today"] == {}
    assert data["total_feedings_today"] == 0


@pytest.mark.asyncio
async def test_feeding_manager_unknown_meal_type() -> None:
    """Feeding with None meal_type is categorized as 'unknown'."""

    manager = FeedingManager()
    await manager.async_add_feeding("dog", 1.0, meal_type=None)

    data = await manager.async_get_feeding_data("dog")

    assert data["feedings_today"]["unknown"] == 1
    assert data["total_feedings_today"] == 1


@pytest.mark.asyncio
async def test_feeding_manager_ignores_feedings_from_previous_days() -> None:
    """Feedings from earlier days should not appear in today's counts."""

    fixed_now = datetime(2023, 1, 1, 12, 0, 0)
    yesterday = fixed_now - timedelta(days=1)

    with patch("feeding_manager.datetime") as mock_datetime:
        mock_datetime.utcnow.return_value = fixed_now

        manager = FeedingManager()

        # Feeding yesterday should be ignored
        await manager.async_add_feeding(
            "dog", 1.0, meal_type="breakfast", time=yesterday
        )
        # Feeding today should be counted (uses patched utcnow)
        await manager.async_add_feeding("dog", 1.0, meal_type="dinner")

        data = await manager.async_get_feeding_data("dog")

    assert data["feedings_today"] == {"dinner": 1}
    assert data["total_feedings_today"] == 1
