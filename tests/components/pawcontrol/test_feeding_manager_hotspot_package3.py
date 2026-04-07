"""Hotspot package 3: feeding manager state/compliance regression coverage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.feeding_manager import (
    FeedingConfig,
    FeedingEvent,
    FeedingManager,
    FeedingScheduleType,
    MealType,
)


@pytest.mark.asyncio
async def test_batch_add_feedings_rejects_missing_dog_id_payload(hass) -> None:
    """Regression: malformed batch payloads must fail fast with a key error."""
    manager = FeedingManager(hass)

    with pytest.raises(KeyError, match="dog_id"):
        await manager.async_batch_add_feedings([
            {
                "amount": 120.0,
                "meal_type": "breakfast",
                "time": datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
            }
        ])


@pytest.mark.asyncio
async def test_batch_add_feedings_dispatches_contiguous_events_in_order(hass) -> None:
    """Batch dispatch should preserve order and forward per-entry arguments."""
    manager = FeedingManager(hass)
    manager.async_add_feeding = AsyncMock(side_effect=["first", "second"])

    result = await manager.async_batch_add_feedings([
        {
            "dog_id": "dog-1",
            "amount": 90.0,
            "meal_type": "breakfast",
            "scheduled": True,
        },
        {
            "dog_id": "dog-2",
            "amount": 110.0,
            "timestamp": datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
            "notes": "manual correction",
        },
    ])

    assert result == ["first", "second"]
    assert manager.async_add_feeding.await_count == 2
    first_call = manager.async_add_feeding.await_args_list[0]
    second_call = manager.async_add_feeding.await_args_list[1]
    assert first_call.args == ("dog-1",)
    assert first_call.kwargs["meal_type"] == "breakfast"
    assert second_call.args == ("dog-2",)
    assert second_call.kwargs["notes"] == "manual correction"


@pytest.mark.asyncio
async def test_start_diet_transition_no_change_keeps_config_unmodified(hass) -> None:
    """State transition flow should return ``no_change`` when food type is unchanged."""
    manager = FeedingManager(hass)
    config = FeedingConfig(dog_id="dog-1", food_type="dry_food")
    manager._configs["dog-1"] = config

    result = await manager.async_start_diet_transition("dog-1", "dry_food")

    assert result["status"] == "no_change"
    assert result["transition_schedule"] == []
    assert config.transition_data is None
    assert "diet_transition" not in config.health_conditions


@pytest.mark.asyncio
async def test_check_feeding_compliance_time_window_ignores_old_and_skipped_events(
    hass,
) -> None:
    """Compliance window must only include recent non-skipped feeding events."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=1,
        daily_food_amount=100.0,
        schedule_type=FeedingScheduleType.FLEXIBLE,
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(days=2),
            amount=80.0,
            meal_type=MealType.BREAKFAST,
        ),
        FeedingEvent(
            time=now - timedelta(hours=2),
            amount=999.0,
            meal_type=MealType.BREAKFAST,
            skipped=True,
        ),
        FeedingEvent(
            time=now - timedelta(hours=1),
            amount=100.0,
            meal_type=MealType.BREAKFAST,
        ),
    ]

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            "custom_components.pawcontrol.feeding_manager.dt_util.now", lambda: now
        )
        result = await manager.async_check_feeding_compliance("dog-1", days_to_check=1)

    assert result["status"] == "completed"
    assert result["days_analyzed"] == 1
    assert result["compliance_rate"] == 100.0
    assert result["days_with_issues"] == 0
