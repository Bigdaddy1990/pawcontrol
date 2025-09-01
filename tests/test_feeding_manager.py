"""Tests for the lightweight FeedingManager."""

from __future__ import annotations

import pytest

import sys
from importlib import util
from pathlib import Path
from datetime import datetime, timedelta

SPEC = util.spec_from_file_location(
    "feeding_manager",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pawcontrol"
    / "feeding_manager.py",
)
assert SPEC and SPEC.loader
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
async def test_feeding_manager_excludes_previous_days() -> None:
    """Feedings from other days are excluded from today's totals."""

    manager = FeedingManager()
    yesterday = datetime.utcnow() - timedelta(days=1)
    await manager.async_add_feeding("dog", 1.0, meal_type="breakfast", time=yesterday)
    await manager.async_add_feeding("dog", 1.0, meal_type="dinner")

    data = await manager.async_get_feeding_data("dog")

    assert "breakfast" not in data["feedings_today"]
    assert data["feedings_today"]["dinner"] == 1
    assert data["total_feedings_today"] == 1
