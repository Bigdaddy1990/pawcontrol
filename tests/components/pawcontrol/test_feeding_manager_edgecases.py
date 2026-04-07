"""Edge-case and regression tests for feeding manager internals."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol.feeding_manager import (
    FeedingConfig,
    FeedingEvent,
    FeedingManager,
    FeedingScheduleType,
    MealType,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_data", "expected"),
    [
        (
            {
                "meals_per_day": "bad",
                "daily_food_amount": "bad",
                "portion_tolerance": "bad",
                "dog_weight": "bad",
                "ideal_weight": "bad",
                "age_months": "bad",
                "body_condition_score": "bad",
            },
            {
                "meals_per_day": 2,
                "daily_food_amount": 500.0,
                "portion_tolerance": 10,
                "dog_weight": None,
                "ideal_weight": None,
                "age_months": 0,
                "body_condition_score": 0,
            },
        ),
        (
            {
                "meals_per_day": "5",
                "daily_food_amount": "750.5",
                "portion_tolerance": "15",
                "dog_weight": "13.4",
                "ideal_weight": "11.9",
                "age_months": "24",
                "body_condition_score": "6",
            },
            {
                "meals_per_day": 5,
                "daily_food_amount": 750.5,
                "portion_tolerance": 15,
                "dog_weight": 13.4,
                "ideal_weight": 11.9,
                "age_months": 24,
                "body_condition_score": 6,
            },
        ),
    ],
)
async def test_create_feeding_config_handles_invalid_numeric_strings_regression(
    hass,
    config_data: dict[str, object],
    expected: dict[str, object],
) -> None:
    """Regression: invalid numeric strings should safely fall back to defaults."""
    manager = FeedingManager(hass)

    config = await manager._create_feeding_config("dog-1", config_data)

    assert config.meals_per_day == expected["meals_per_day"]
    assert config.daily_food_amount == expected["daily_food_amount"]
    assert config.portion_tolerance == expected["portion_tolerance"]
    assert config.dog_weight == expected["dog_weight"]
    assert config.ideal_weight == expected["ideal_weight"]
    assert config.age_months == expected["age_months"]
    assert config.body_condition_score == expected["body_condition_score"]


@pytest.mark.parametrize(
    ("event_amount", "expected_amount"),
    [
        ("50.0", 50.0),
        ("bad", 0.0),
        (None, 0.0),
    ],
)
def test_build_feeding_snapshot_skips_invalid_amounts_regression(
    hass,
    event_amount: object,
    expected_amount: float,
) -> None:
    """Regression: malformed feeding amounts should not crash snapshot creation."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=2,
        daily_food_amount=200.0,
        schedule_type=FeedingScheduleType.FLEXIBLE,
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(hours=1),
            amount=event_amount,
            meal_type=MealType.BREAKFAST,
        ),
    ]

    snapshot = manager._build_feeding_snapshot("dog-1")

    assert snapshot["daily_amount_consumed"] == expected_amount


@pytest.mark.asyncio
@pytest.mark.parametrize("event_amount", ["bad", None, 80.0])
async def test_async_check_feeding_compliance_handles_amount_type_errors(
    hass,
    event_amount: object,
) -> None:
    """Compliance checks should be resilient to malformed feeding amounts."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=1,
        daily_food_amount=100.0,
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(hours=1),
            amount=event_amount,
            meal_type=MealType.BREAKFAST,
        ),
    ]

    result = await manager.async_check_feeding_compliance("dog-1", days_to_check=1)

    assert result["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("duration_days", [0, -1])
async def test_activate_emergency_feeding_mode_rejects_non_positive_duration(
    hass,
    duration_days: int,
) -> None:
    """Emergency mode must reject invalid duration boundaries."""
    manager = FeedingManager(hass)
    manager._configs["dog-1"] = FeedingConfig(dog_id="dog-1")

    with pytest.raises(ValueError, match="Duration must be at least 1 day"):
        await manager.async_activate_emergency_feeding_mode(
            "dog-1",
            emergency_type="illness",
            duration_days=duration_days,
        )
