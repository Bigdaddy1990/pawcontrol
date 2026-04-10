"""Focused coverage tests for feeding compliance and emergency activation."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol.feeding_manager import (
    FeedingConfig,
    FeedingEvent,
    FeedingManager,
    MealType,
)


@pytest.mark.asyncio
async def test_async_check_feeding_compliance_success_path(hass) -> None:
    """Compliance API should return a completed payload for valid recent history."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=1,
        daily_food_amount=100.0,
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(hours=2),
            amount=100.0,
            meal_type=MealType.BREAKFAST,
            scheduled=True,
        ),
    ]

    result = await manager.async_check_feeding_compliance("dog-1", days_to_check=1)

    assert result["status"] == "completed"
    assert result["days_analyzed"] == 1


@pytest.mark.asyncio
async def test_async_check_feeding_compliance_invalid_input_raises(hass) -> None:
    """Missing dog config should surface as ValueError."""
    manager = FeedingManager(hass)

    with pytest.raises(ValueError, match="No feeding configuration found for dog"):
        await manager.async_check_feeding_compliance("missing-dog")


@pytest.mark.asyncio
async def test_async_check_feeding_compliance_fallback_no_history(hass) -> None:
    """No history should return a no_data fallback payload."""
    manager = FeedingManager(hass)
    manager._configs["dog-1"] = FeedingConfig(dog_id="dog-1")

    result = await manager.async_check_feeding_compliance("dog-1")

    assert result["status"] == "no_data"


@pytest.mark.asyncio
async def test_async_activate_emergency_feeding_mode_success_path(hass) -> None:
    """Emergency feeding mode should mutate config and return activation metadata."""
    manager = FeedingManager(hass)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        daily_food_amount=400.0,
        meals_per_day=2,
        food_type="dry_food",
    )

    result = await manager.async_activate_emergency_feeding_mode(
        "dog-1",
        emergency_type="digestive_upset",
        duration_days=2,
        portion_adjustment=0.8,
    )

    assert result["status"] == "activated"
    assert result["new_daily_amount"] == pytest.approx(320.0)
    assert manager._configs["dog-1"].food_type == "wet_food"
    restore_task = manager._emergency_restore_tasks.pop("dog-1", None)
    if restore_task is not None:
        restore_task.cancel()


@pytest.mark.asyncio
async def test_async_activate_emergency_feeding_mode_invalid_input_raises(hass) -> None:
    """Unsupported emergency types should raise ValueError."""
    manager = FeedingManager(hass)
    manager._configs["dog-1"] = FeedingConfig(dog_id="dog-1")

    with pytest.raises(ValueError, match="Emergency type must be one of"):
        await manager.async_activate_emergency_feeding_mode(
            "dog-1",
            emergency_type="unsupported",
        )


@pytest.mark.asyncio
async def test_async_activate_emergency_feeding_mode_fallback_missing_config(
    hass,
) -> None:
    """Missing config should fail fast with a clear ValueError."""
    manager = FeedingManager(hass)

    with pytest.raises(ValueError, match="No feeding configuration found for dog"):
        await manager.async_activate_emergency_feeding_mode(
            "missing-dog",
            emergency_type="illness",
        )
