"""Coverage tests for feeding manager helpers and calculations."""

from datetime import UTC, datetime, time
from unittest.mock import patch

import pytest

from custom_components.pawcontrol.feeding_manager import (
    ActivityLevel,
    FeedingEvent,
    FeedingConfig,
    FeedingManager,
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

    with patch("custom_components.pawcontrol.feeding_manager.dt_util.now", return_value=now):
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
    with patch("custom_components.pawcontrol.feeding_manager.dt_util.now", return_value=now):
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
                meal_type=MealType.DINNER,
                scheduled_time=time(18, 0),
                portion_size=0.0,
            ),
        ],
    )

    assert config.calculate_portion_size() == pytest.approx(300.0)
    assert config.calculate_portion_size(MealType.BREAKFAST) == pytest.approx(345.7)


def test_feeding_config_uses_health_portion_when_available() -> None:
    """Health-aware portion should be returned when calculator gives a value."""
    config = FeedingConfig(dog_id="buddy", meals_per_day=3, daily_food_amount=450.0)

    with patch.object(config, "_calculate_health_aware_portion", return_value=222.2):
        assert config.calculate_portion_size(MealType.DINNER) == pytest.approx(222.2)

    with patch.object(config, "_calculate_health_aware_portion", side_effect=RuntimeError):
        assert config.calculate_portion_size(MealType.DINNER) == pytest.approx(165.0)


def test_diet_validation_summary_defaults_without_validation_data() -> None:
    """Diet validation summary should emit a no-data baseline."""
    config = FeedingConfig(dog_id="buddy", special_diet=["renal"])

    summary = config._get_diet_validation_summary()

    assert summary["has_adjustments"] is False
    assert summary["adjustment_info"] == "No validation data"
    assert summary["total_diets"] == 1
    assert summary["compatibility_level"] == "excellent"
