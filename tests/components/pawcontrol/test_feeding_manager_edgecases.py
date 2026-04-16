"""Edge-case and regression tests for feeding manager internals."""

from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.pawcontrol.feeding_manager import (
    FeedingConfig,
    FeedingEvent,
    FeedingManager,
    FeedingScheduleType,
    MealSchedule,
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


@pytest.mark.asyncio
async def test_create_feeding_config_normalizes_boundary_types_and_values(hass) -> None:
    """Config creation should survive mixed input types and preserve safe defaults."""
    manager = FeedingManager(hass)

    config = await manager._create_feeding_config(
        "dog-1",
        {
            "feeding_schedule": "strict",
            "meals_per_day": 0,
            "daily_food_amount": "350.5",
            "food_type": 99,
            "treats_enabled": "yes",
            "water_tracking": 1,
            "calorie_tracking": "no",
            "portion_calculation": "enabled",
            "medication_with_meals": "nope",
            "health_aware_portions": "on",
            "health_conditions": "not-a-list",
            "diet_validation": [1, 2, 3],
            "breakfast_time": "07:30:45",
            "lunch_time": "11:15",
            "snack_times": ("09:00", "bad", 42, None),
            "enable_reminders": "always",
            "reminder_minutes_before": "oops",
        },
    )

    assert config.meals_per_day == 0
    assert config.daily_food_amount == pytest.approx(350.5)
    assert config.food_type == "dry_food"
    assert config.treats_enabled is True
    assert config.water_tracking is False
    assert config.calorie_tracking is False
    assert config.portion_calculation_enabled is True
    assert config.medication_with_meals is False
    assert config.health_aware_portions is True
    assert config.health_conditions == []
    assert config.diet_validation is None
    assert config.schedule_type is FeedingScheduleType.STRICT
    assert [schedule.meal_type for schedule in config.meal_schedules] == [
        MealType.BREAKFAST,
        MealType.LUNCH,
        MealType.SNACK,
    ]
    assert config.meal_schedules[0].reminder_enabled is True
    assert config.meal_schedules[0].reminder_minutes_before == 15


def test_build_feeding_snapshot_handles_expired_emergency_and_bad_serialization(
    hass,
) -> None:
    """Snapshot generation recovers from invalid amounts and stale emergency states."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)

    config = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=2,
        daily_food_amount=200.0,
        schedule_type=FeedingScheduleType.STRICT,
        meal_schedules=[
            MealSchedule(
                meal_type=MealType.BREAKFAST,
                scheduled_time=(now - timedelta(hours=2)).time(),
                portion_size=100.0,
            ),
            MealSchedule(
                meal_type=MealType.DINNER,
                scheduled_time=(now + timedelta(hours=3)).time(),
                portion_size=100.0,
            ),
        ],
    )
    manager._configs["dog-1"] = config
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(hours=2), amount="bad", meal_type=MealType.BREAKFAST
        ),
        FeedingEvent(
            time=now - timedelta(minutes=90), amount=80.0, meal_type=MealType.BREAKFAST
        ),
    ]
    manager._active_emergencies["dog-1"] = {
        "active": True,
        "status": "active",
        "emergency_type": "illness",
        "portion_adjustment": 0.8,
        "duration_days": 2,
        "activated_at": (now - timedelta(days=1)).isoformat(),
        "expires_at": (now - timedelta(minutes=1)).isoformat(),
        "food_type_recommendation": "wet_food",
    }

    with (
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.now",
            return_value=now,
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.utcnow",
            return_value=now,
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.as_local",
            side_effect=lambda value: value.replace(tzinfo=UTC),
        ),
    ):
        snapshot = manager._build_feeding_snapshot("dog-1")

    assert snapshot["daily_amount_consumed"] == 80.0
    assert snapshot["health_emergency"] is False
    assert snapshot["emergency_mode"] is not None
    assert snapshot["emergency_mode"]["active"] is False
    assert snapshot["emergency_mode"]["status"] == "active"
    assert snapshot["total_feedings_today"] == 2
    assert snapshot["next_feeding_type"] == MealType.DINNER.value


@pytest.mark.asyncio
async def test_async_check_feeding_compliance_strict_schedule_recommendations(
    hass,
) -> None:
    """Compliance checks include strict-schedule and low-score recommendations."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 20, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=2,
        daily_food_amount=200.0,
        schedule_type=FeedingScheduleType.STRICT,
        meal_schedules=[
            MealSchedule(
                meal_type=MealType.BREAKFAST,
                scheduled_time=(now - timedelta(hours=10)).time(),
                portion_size=100.0,
            ),
            MealSchedule(
                meal_type=MealType.DINNER,
                scheduled_time=(now - timedelta(hours=1)).time(),
                portion_size=100.0,
            ),
        ],
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(hours=2), amount="bad", meal_type=MealType.BREAKFAST
        ),
    ]

    with patch(
        "custom_components.pawcontrol.feeding_manager.dt_util.now", return_value=now
    ):
        result = await manager.async_check_feeding_compliance(
            "dog-1",
            days_to_check=1,
        )

    assert result["status"] == "completed"
    assert result["days_with_issues"] == 1
    assert any(
        "Missed scheduled feedings" in entry
        for entry in result["compliance_issues"][0]["issues"]
    )
    assert "Consider setting up feeding reminders" in result["recommendations"]
    assert "Enable automatic reminders for scheduled meals" in result["recommendations"]
    assert "Reduce portion sizes to prevent weight gain" in result["recommendations"]


@pytest.mark.asyncio
async def test_async_check_feeding_compliance_zero_expected_feedings_defaults_to_100(
    hass,
) -> None:
    """Compliance clamps to 100 when no meals are expected in the analyzed window."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=0,
        daily_food_amount=0.0,
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(hours=1), amount=10.0, meal_type=MealType.SNACK
        ),
    ]

    with patch(
        "custom_components.pawcontrol.feeding_manager.dt_util.now", return_value=now
    ):
        result = await manager.async_check_feeding_compliance("dog-1", days_to_check=1)

    assert result["status"] == "completed"
    assert result["compliance_rate"] == 100.0
    assert result["compliance_score"] == 100


@pytest.mark.asyncio
async def test_async_activate_emergency_feeding_mode_restores_state_without_leaks(
    hass,
) -> None:
    """Emergency restore task should resolve and clean up task tracking."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    config = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=2,
        daily_food_amount=300.0,
        food_type="dry_food",
        schedule_type=FeedingScheduleType.STRICT,
    )
    manager._configs["dog-1"] = config

    captured: dict[str, object] = {}

    class _CancelledTask:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    previous_task = _CancelledTask()
    manager._emergency_restore_tasks["dog-1"] = previous_task

    class _TrackedTask:
        def cancel(self) -> None:
            return None

    def _fake_create_task(coro: object) -> _TrackedTask:
        captured["coro"] = coro
        return _TrackedTask()

    with (
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.now",
            return_value=now,
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.utcnow",
            return_value=now + timedelta(days=1),
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.asyncio.sleep",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.asyncio.create_task",
            side_effect=_fake_create_task,
        ),
    ):
        result = await manager.async_activate_emergency_feeding_mode(
            "dog-1",
            emergency_type="digestive_upset",
            duration_days=1,
            portion_adjustment=0.8,
        )
        await cast(Coroutine[Any, Any, None], captured["coro"])

    assert previous_task.cancelled is True
    assert result["status"] == "activated"
    assert manager._active_emergencies["dog-1"]["active"] is False
    assert manager._active_emergencies["dog-1"]["status"] == "active"
    assert "dog-1" not in manager._emergency_restore_tasks
    assert config.daily_food_amount == 300.0
    assert config.food_type == "dry_food"


@pytest.mark.asyncio
async def test_async_activate_emergency_feeding_mode_restore_error_is_swallowed(
    hass,
) -> None:
    """Restoration errors are logged and do not leak from background tasks."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(dog_id="dog-1")
    captured: dict[str, object] = {}

    class _TrackedTask:
        def cancel(self) -> None:
            return None

    def _fake_create_task(coro: object) -> _TrackedTask:
        captured["coro"] = coro
        return _TrackedTask()

    with (
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.now",
            return_value=now,
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.utcnow",
            return_value=now + timedelta(days=1),
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.asyncio.sleep",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.asyncio.create_task",
            side_effect=_fake_create_task,
        ),
        patch.object(
            manager,
            "_apply_emergency_restoration",
            side_effect=RuntimeError("restore failed"),
        ),
    ):
        await manager.async_activate_emergency_feeding_mode(
            "dog-1",
            emergency_type="illness",
            duration_days=1,
        )
        await cast(Coroutine[Any, Any, None], captured["coro"])

    assert manager._active_emergencies["dog-1"]["active"] is False
    assert "dog-1" not in manager._emergency_restore_tasks
