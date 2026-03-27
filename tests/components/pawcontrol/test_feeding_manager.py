"""Coverage tests for feeding manager helpers and configuration parsing."""

from datetime import time

import pytest

from custom_components.pawcontrol.feeding_manager import (
    FeedingConfig,
    FeedingManager,
    FeedingScheduleType,
)


def test_parse_time_supports_hhmm_and_hhmmss(hass) -> None:
    """Time parsing should support HH:MM, HH:MM:SS, and native ``time`` objects."""
    manager = FeedingManager(hass)

    assert manager._parse_time("07:45") == time(7, 45)
    assert manager._parse_time("18:30:05") == time(18, 30, 5)
    assert manager._parse_time(time(9, 15)) == time(9, 15)
    assert manager._parse_time("invalid") is None


def test_normalize_special_diet_discards_invalid_entries(hass) -> None:
    """Special diet normalization should trim strings and drop non-string values."""
    manager = FeedingManager(hass)

    assert manager._normalize_special_diet(None) == []
    assert manager._normalize_special_diet("  renal ") == ["renal"]
    assert manager._normalize_special_diet([
        " low sodium ",
        "",
        1,
        None,
        "grain-free",
    ]) == [
        "low sodium",
        "grain-free",
    ]


@pytest.mark.asyncio
async def test_create_feeding_config_parses_meal_schedules(hass) -> None:
    """Feeding config creation should parse schedules, reminders, and snack times."""
    manager = FeedingManager(hass)

    config = await manager._create_feeding_config(
        "dog-1",
        {
            "feeding_schedule": "strict",
            "breakfast_time": "07:30",
            "dinner_time": time(18, 15),
            "snack_times": ["10:00", "bad-time", 123],
            "portion_size": "120.5",
            "enable_reminders": False,
            "reminder_minutes_before": "20",
            "special_diet": [" renal ", 123],
        },
    )

    assert config.schedule_type is FeedingScheduleType.STRICT
    assert config.special_diet == ["renal"]
    assert len(config.meal_schedules) == 3

    breakfast = config.meal_schedules[0]
    assert breakfast.scheduled_time == time(7, 30)
    assert breakfast.portion_size == 120.5
    assert breakfast.reminder_enabled is False
    assert breakfast.reminder_minutes_before == 20

    snack = config.meal_schedules[-1]
    assert snack.scheduled_time == time(10, 0)
    assert snack.portion_size == 50.0


def test_calculate_daily_calories_uses_ideal_weight_and_activity_fallback(hass) -> None:
    """Daily calories should use ideal weight and default activity on bad input."""
    manager = FeedingManager(hass)

    manager._dogs["dog-1"] = {"dog_id": "dog-1", "weight": 30.0}
    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        activity_level="unsupported",
        ideal_weight=20.0,
        weight_goal="lose",
    )

    expected = round(manager._calculate_rer(20.0, adjusted=False) * 1.6, 1)

    assert manager.calculate_daily_calories("dog-1") == expected


def test_calculate_portion_prefers_dog_metadata_meal_count(hass) -> None:
    """Portion calculation should use cached dog metadata meal counts when set."""
    manager = FeedingManager(hass)

    manager._configs["dog-1"] = FeedingConfig(
        dog_id="dog-1",
        daily_food_amount=600.0,
        meals_per_day=3,
    )
    manager._dogs["dog-1"] = {
        "dog_id": "dog-1",
        "weight": 20.0,
        "meals_per_day": 4,
    }

    assert manager.calculate_portion("dog-1") == 150.0
