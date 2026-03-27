"""Coverage tests for feeding manager helpers and calculations."""

from unittest.mock import patch

import pytest

from custom_components.pawcontrol.feeding_manager import (
    ActivityLevel,
    FeedingConfig,
    FeedingManager,
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
