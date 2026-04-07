"""Coverage tests for feeding manager helpers and calculations."""

from datetime import UTC, datetime, time, timedelta
from unittest.mock import patch

import pytest

from custom_components.pawcontrol.feeding_manager import (
    ActivityLevel,
    FeedingConfig,
    FeedingEvent,
    FeedingManager,
    FeedingScheduleType,
    HealthCalculator,
    MealSchedule,
    MealType,
    _normalise_health_override,
)


def test_normalise_health_override_filters_and_coerces_values() -> None:
    """Health override normalizer should coerce scalar values and drop invalid ones."""
    payload = {
        "weight": "22.5",
        "ideal_weight": 20,
        "age_months": "36",
        "health_conditions": ["arthritis", 7, "allergy"],
    }

    assert _normalise_health_override(payload) == {
        "weight": 22.5,
        "ideal_weight": 20.0,
        "age_months": 36,
        "health_conditions": ["arthritis", "allergy"],
    }


def test_normalise_health_override_returns_none_for_empty_payload() -> None:
    """Empty or unsupported override payload should produce ``None``."""
    assert _normalise_health_override(None) is None
    assert _normalise_health_override({"health_conditions": "single-condition"}) is None


def test_parse_time_supports_time_strings_and_rejects_invalid(hass) -> None:
    """Time parser should accept valid formats and reject invalid values."""
    manager = FeedingManager(hass)

    assert str(manager._parse_time("08:30")) == "08:30:00"
    assert str(manager._parse_time("08:30:45")) == "08:30:45"
    assert manager._parse_time("bad-value") is None


def test_normalize_special_diet_handles_multiple_input_shapes(hass) -> None:
    """Special diet normalization should trim strings and ignore non-string entries."""
    manager = FeedingManager(hass)

    assert manager._normalize_special_diet("  renal  ") == ["renal"]
    assert manager._normalize_special_diet([" diabetic ", 12, ""]) == ["diabetic"]
    assert manager._normalize_special_diet(12) == []
    assert manager._normalize_special_diet(None) == []


def test_calculate_daily_calories_uses_weight_goal_and_activity_fallback(hass) -> None:
    """Calorie calculation should respect weight-goal and activity fallback paths."""
    manager = FeedingManager(hass)
    manager._dogs["buddy"] = {
        "dog_id": "buddy",
        "weight": 18.0,
        "age_months": 48,
        "activity_level": "unsupported",
    }
    manager._configs["buddy"] = FeedingConfig(
        dog_id="buddy",
        ideal_weight=16.0,
        weight_goal="lose",
        activity_level="unsupported",
    )

    with patch.object(manager, "_calculate_rer", return_value=100.0) as calculate_rer:
        calories = manager.calculate_daily_calories("buddy")

    calculate_rer.assert_called_once_with(16.0, adjusted=False)
    assert calories == pytest.approx(160.0)


@pytest.mark.parametrize(
    ("weight_goal", "expected_weight", "adjusted_flag"),
    [("gain", 14.0, True), ("maintain", 12.0, True)],
)
def test_calculate_daily_calories_weight_goal_paths(
    hass,
    weight_goal: str,
    expected_weight: float,
    adjusted_flag: bool,
) -> None:
    """Calorie calculation should choose the expected base weight for each goal."""
    manager = FeedingManager(hass)
    manager._dogs["max"] = {
        "dog_id": "max",
        "weight": 12.0,
        "activity_level": ActivityLevel.HIGH.value,
    }
    manager._configs["max"] = FeedingConfig(
        dog_id="max",
        ideal_weight=14.0,
        weight_goal=weight_goal,
    )

    with patch.object(manager, "_calculate_rer", return_value=100.0) as calculate_rer:
        calories = manager.calculate_daily_calories("max")

    calculate_rer.assert_called_once_with(expected_weight, adjusted=adjusted_flag)
    assert calories == pytest.approx(200.0)


def test_calculate_portion_size_falls_back_when_health_aware_errors() -> None:
    """Portion calculation should fall back to meal multipliers after failures."""
    config = FeedingConfig(
        dog_id="buddy",
        daily_food_amount=600.0,
        meals_per_day=3,
        portion_tolerance=0,
        health_aware_portions=True,
        meal_schedules=[
            MealSchedule(
                meal_type=MealType.BREAKFAST,
                scheduled_time=time(8, 0),
                portion_size=0.0,
            ),
            MealSchedule(
                meal_type=MealType.LUNCH,
                scheduled_time=time(12, 0),
                portion_size=0.0,
            ),
            MealSchedule(
                meal_type=MealType.DINNER,
                scheduled_time=time(18, 0),
                portion_size=0.0,
            ),
        ],
    )

    with patch.object(
        config,
        "_calculate_health_aware_portion",
        side_effect=RuntimeError("upstream-error"),
    ):
        portion = config.calculate_portion_size(MealType.BREAKFAST)

    assert portion == pytest.approx(220.0)


def test_calculate_portion_size_uses_fallback_weight_when_all_schedules_disabled() -> (
    None
):
    """Portion calculation should avoid divide-by-zero when schedules are disabled."""
    config = FeedingConfig(
        dog_id="milo",
        daily_food_amount=500.0,
        meals_per_day=2,
        health_aware_portions=False,
        portion_tolerance=0,
        meal_schedules=[
            MealSchedule(
                meal_type=MealType.BREAKFAST,
                scheduled_time=time(8, 0),
                portion_size=0.0,
                enabled=False,
            )
        ],
    )

    assert config.calculate_portion_size(MealType.DINNER) == pytest.approx(250.0)


def test_feeding_event_to_dict_serializes_optional_fields() -> None:
    """Feeding events should serialize optional metadata predictably."""
    event = FeedingEvent(
        time=datetime(2026, 4, 4, 8, 30, tzinfo=UTC),
        amount=125,
        meal_type=MealType.BREAKFAST,
        scheduled=True,
        with_medication=True,
        medication_name="Omega-3",
        medication_dose="1 capsule",
        medication_time="08:15",
    )

    payload = event.to_dict()

    assert payload["time"] == "2026-04-04T08:30:00+00:00"
    assert payload["amount"] == 125.0
    assert payload["meal_type"] == "breakfast"
    assert payload["scheduled"] is True
    assert payload["with_medication"] is True
    assert payload["medication_name"] == "Omega-3"


def test_meal_schedule_next_and_reminder_times_respect_weekday_filters() -> None:
    """Schedule helpers should handle disabled/filtered and reminder branches."""
    now = datetime(2026, 4, 4, 10, 0, tzinfo=UTC)  # Saturday
    monday = 0

    schedule = MealSchedule(
        meal_type=MealType.DINNER,
        scheduled_time=time(9, 30),
        portion_size=200.0,
        days_of_week=[monday],
        reminder_minutes_before=30,
    )

    with patch(
        "custom_components.pawcontrol.feeding_manager.dt_util.now", return_value=now
    ):
        assert schedule.is_due_today() is False
        next_time = schedule.get_next_feeding_time()
        reminder_time = schedule.get_reminder_time()

    assert next_time == datetime(2026, 4, 6, 9, 30, tzinfo=UTC)
    assert reminder_time == datetime(2026, 4, 6, 9, 0, tzinfo=UTC)

    disabled = MealSchedule(
        meal_type=MealType.BREAKFAST,
        scheduled_time=time(8, 0),
        portion_size=150.0,
        enabled=False,
        days_of_week=[],
        reminder_enabled=False,
    )
    with patch(
        "custom_components.pawcontrol.feeding_manager.dt_util.now", return_value=now
    ):
        assert disabled.is_due_today() is False
        assert disabled.get_next_feeding_time() == datetime(
            2026,
            4,
            5,
            8,
            0,
            tzinfo=UTC,
        )
        assert disabled.get_reminder_time() is None


def test_feeding_config_calculate_portion_size_fallback_and_distribution() -> None:
    """Portion helper should fallback correctly and normalize meal distribution."""
    config = FeedingConfig(
        dog_id="buddy",
        meals_per_day=2,
        daily_food_amount=600.0,
        health_aware_portions=False,
        meal_schedules=[
            MealSchedule(
                meal_type=MealType.BREAKFAST,
                scheduled_time=time(8, 0),
                portion_size=0.0,
            ),
            MealSchedule(
                meal_type=MealType.LUNCH,
                scheduled_time=time(12, 0),
                portion_size=0.0,
            ),
            MealSchedule(
                meal_type=MealType.DINNER,
                scheduled_time=time(18, 0),
                portion_size=0.0,
            ),
        ],
    )

    with patch.object(
        config,
        "_calculate_health_aware_portion",
        side_effect=RuntimeError("boom"),
    ):
        portion = config.calculate_portion_size(MealType.BREAKFAST)

    assert portion == pytest.approx(242.0)


def test_calculate_portion_size_without_meal_type_returns_base() -> None:
    """Basic fallback should return equal split when meal type is omitted."""
    config = FeedingConfig(
        dog_id="nala",
        daily_food_amount=500.0,
        meals_per_day=2,
        health_aware_portions=False,
    )

    assert config.calculate_portion_size() == pytest.approx(250.0)


def test_get_diet_validation_summary_tracks_adjustments_and_urgency() -> None:
    """Diet summary should expose conflicts, warnings, and compatibility score."""
    config = FeedingConfig(
        dog_id="luna",
        special_diet=["renal", "diabetic", "allergy", "sensitive"],
        health_aware_portions=False,
        portion_tolerance=0,
        diet_validation={
            "valid": False,
            "conflicts": [
                {"type": "protein_conflict", "diets": ["renal"], "message": "conflict"}
            ],
            "warnings": [
                {"type": "fiber_warning", "diets": ["diabetic"], "message": "warn"}
            ],
            "recommended_vet_consultation": False,
            "total_diets": 4,
        },
    )

    with patch.object(
        HealthCalculator,
        "calculate_diet_validation_adjustment",
        return_value=0.85,
    ):
        summary = config._get_diet_validation_summary()

    assert summary["has_adjustments"] is True
    assert summary["consultation_urgency"] == "high"
    assert summary["compatibility_level"] == "acceptable"
    assert summary["percentage_adjustment"] == pytest.approx(-15.0)
    assert summary["vet_consultation_recommended"] is True
    assert config.calculate_portion_size() == pytest.approx(250.0)
    assert config.calculate_portion_size(MealType.BREAKFAST) == pytest.approx(275.0)


def test_feeding_config_uses_health_portion_when_available() -> None:
    """Health-aware portion should be returned when calculator gives a value."""
    config = FeedingConfig(dog_id="buddy", meals_per_day=3, daily_food_amount=450.0)

    with patch.object(config, "_calculate_health_aware_portion", return_value=222.2):
        assert config.calculate_portion_size(MealType.DINNER) == pytest.approx(222.2)

    with patch.object(
        config, "_calculate_health_aware_portion", side_effect=RuntimeError
    ):
        assert config.calculate_portion_size(MealType.DINNER) == pytest.approx(165.0)


def test_diet_validation_summary_defaults_without_validation_data() -> None:
    """Diet validation summary should emit a no-data baseline."""
    config = FeedingConfig(dog_id="buddy", special_diet=["renal"])

    summary = config._get_diet_validation_summary()

    assert summary["has_adjustments"] is False
    assert summary["adjustment_info"] == "No validation data"
    assert summary["total_diets"] == 1
    assert summary["compatibility_level"] == "excellent"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_data", "expected"),
    [
        (
            {},
            {
                "meals_per_day": 2,
                "daily_food_amount": 500.0,
                "food_type": "dry_food",
                "schedule_type": FeedingScheduleType.FLEXIBLE,
                "portion_tolerance": 10,
                "health_aware_portions": True,
                "meal_count": 0,
            },
        ),
        (
            {
                "meals_per_day": "4",
                "daily_food_amount": "999.9",
                "food_type": "wet_food",
                "feeding_schedule": "strict",
                "portion_tolerance": "25",
                "health_aware_portions": False,
                "special_diet": [" renal ", "", 5],
                "breakfast_time": "07:30",
                "snack_times": ["10:00", None, "bad"],
            },
            {
                "meals_per_day": 4,
                "daily_food_amount": 999.9,
                "food_type": "wet_food",
                "schedule_type": FeedingScheduleType.STRICT,
                "portion_tolerance": 25,
                "health_aware_portions": False,
                "meal_count": 2,
            },
        ),
    ],
)
async def test_create_feeding_config_applies_defaults_and_coercion(
    hass,
    config_data: dict[str, object],
    expected: dict[str, object],
) -> None:
    """Config creation should coerce input payloads into domain-safe values."""
    manager = FeedingManager(hass)

    config = await manager._create_feeding_config("dog-1", config_data)

    assert config.meals_per_day == expected["meals_per_day"]
    assert config.daily_food_amount == pytest.approx(expected["daily_food_amount"])
    assert config.food_type == expected["food_type"]
    assert config.schedule_type == expected["schedule_type"]
    assert config.portion_tolerance == expected["portion_tolerance"]
    assert config.health_aware_portions == expected["health_aware_portions"]
    assert len(config.meal_schedules) == expected["meal_count"]


@pytest.mark.asyncio
async def test_create_feeding_config_rejects_invalid_schedule(hass) -> None:
    """Invalid schedule enum values should surface as ValueError."""
    manager = FeedingManager(hass)

    with pytest.raises(ValueError):
        await manager._create_feeding_config(
            "dog-1",
            {"feeding_schedule": "invalid_schedule"},
        )


@pytest.mark.asyncio
async def test_create_feeding_config_ignores_invalid_meal_time_inputs(hass) -> None:
    """Ignore invalid meal times instead of crashing config creation."""
    manager = FeedingManager(hass)

    config = await manager._create_feeding_config(
        "dog-1",
        {
            "feeding_schedule": "strict",
            "breakfast_time": "07:30",
            "lunch_time": "invalid-time",
            "dinner_time": object(),
        },
    )

    assert len(config.meal_schedules) == 1
    assert config.meal_schedules[0].meal_type is MealType.BREAKFAST


def test_build_feeding_snapshot_reports_missed_meals_and_progress(hass) -> None:
    """Snapshot builder should expose concrete adherence and consumption metrics."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=2,
        daily_food_amount=200.0,
        schedule_type=FeedingScheduleType.STRICT,
        portion_tolerance=10,
        health_aware_portions=False,
        meal_schedules=[
            MealSchedule(
                meal_type=MealType.BREAKFAST,
                scheduled_time=time(8, 0),
                portion_size=100.0,
            ),
            MealSchedule(
                meal_type=MealType.LUNCH,
                scheduled_time=time(11, 0),
                portion_size=100.0,
            ),
        ],
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(days=1),
            amount=120.0,
            meal_type=MealType.DINNER,
        ),
        FeedingEvent(
            time=now - timedelta(hours=4), amount=100.0, meal_type=MealType.BREAKFAST
        ),
        FeedingEvent(
            time=now - timedelta(hours=1),
            amount=40.0,
            meal_type=MealType.LUNCH,
            skipped=True,
        ),
    ]

    with (
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.now",
            return_value=now,
        ),
        patch(
            "custom_components.pawcontrol.feeding_manager.dt_util.as_local",
            side_effect=lambda value: value.replace(tzinfo=UTC),
        ),
    ):
        snapshot = manager._build_feeding_snapshot("dog-1")

    assert snapshot["daily_amount_consumed"] == pytest.approx(100.0)
    assert snapshot["daily_amount_percentage"] == 50
    assert snapshot["schedule_adherence"] == 50
    assert snapshot["total_feedings_today"] == 1
    assert snapshot["missed_feedings"][0]["meal_type"] == MealType.LUNCH.value
    assert snapshot["next_feeding_type"] == MealType.BREAKFAST.value


def test_build_feeding_snapshot_falls_back_to_empty_payload_without_history(
    hass,
) -> None:
    """Snapshot builder should return empty defaults when no history exists."""
    manager = FeedingManager(hass)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        daily_food_amount=250.0,
        meals_per_day=2,
    )

    snapshot = manager._build_feeding_snapshot("dog-1")

    assert snapshot["daily_amount_consumed"] == 0.0
    assert snapshot["total_feedings_today"] == 0
    assert snapshot["schedule_adherence"] == 100


@pytest.mark.asyncio
async def test_async_check_feeding_compliance_returns_domain_issues(hass) -> None:
    """Compliance check should report underfeeding and missing meals concretely."""
    manager = FeedingManager(hass)
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        meals_per_day=2,
        daily_food_amount=200.0,
        portion_tolerance=10,
        health_aware_portions=False,
    )
    manager._feedings["dog-1"] = [
        FeedingEvent(
            time=now - timedelta(hours=2), amount=100.0, meal_type=MealType.BREAKFAST
        ),
        FeedingEvent(
            time=now - timedelta(days=5),
            amount=200.0,
            meal_type=MealType.DINNER,
            skipped=True,
        ),
    ]

    with patch(
        "custom_components.pawcontrol.feeding_manager.dt_util.now", return_value=now
    ):
        result = await manager.async_check_feeding_compliance("dog-1", days_to_check=2)

    assert result["status"] == "completed"
    assert result["compliance_score"] == 50
    assert result["days_analyzed"] == 1
    assert result["missed_meals"] == [
        {"date": "2026-04-07", "expected": 2, "actual": 1}
    ]
    assert (
        "Underfed by 50.0% (100g vs 200g)" in result["compliance_issues"][0]["issues"]
    )
