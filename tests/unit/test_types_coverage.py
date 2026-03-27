"""Additional coverage for utility helpers in ``custom_components.pawcontrol.types``."""

from __future__ import annotations

import math

import pytest

from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.types import (
    calculate_daily_calories,
    create_entity_id,
    is_dog_config_valid,
    is_feeding_data_valid,
    is_gps_location_valid,
    is_health_data_valid,
    is_notification_data_valid,
    validate_dog_weight_for_size,
)


def test_create_entity_id_normalises_to_home_assistant_style() -> None:
    """Entity IDs should be lower-cased and composed in a stable order."""
    assert create_entity_id("Buddy_One", "Sensor", "Feeding") == (
        "pawcontrol_buddy_one_feeding_sensor"
    )


def test_validate_dog_weight_for_size_honors_ranges_and_unknown_sizes() -> None:
    """Known sizes enforce min/max boundaries; unknown values are tolerated."""
    assert validate_dog_weight_for_size(6.0, "toy")
    assert not validate_dog_weight_for_size(6.1, "toy")
    assert validate_dog_weight_for_size(42.0, "custom_size")


def test_calculate_daily_calories_applies_age_adjustments() -> None:
    """Puppy and senior multipliers should diverge from the adult baseline."""
    weight = 10.0
    base = 70 * math.pow(weight, 0.75)

    assert calculate_daily_calories(weight, "normal", age=5) == int(base * 1.6)
    assert calculate_daily_calories(weight, "normal", age=0) == int(base * 1.6 * 2.0)
    assert calculate_daily_calories(weight, "normal", age=8) == int(base * 1.6 * 0.9)


def test_is_dog_config_valid_returns_false_for_non_mapping() -> None:
    """Non-mapping payloads should be rejected immediately."""
    assert not is_dog_config_valid(["invalid"])


def test_is_dog_config_valid_delegates_to_flow_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # noqa: E501
    """Flow validator failures should convert to ``False`` and success to ``True``."""
    from custom_components.pawcontrol import flow_validation

    def _raise_validation(*_: object, **__: object) -> None:
        raise FlowValidationError(field_errors={"dog_name": "invalid"})

    monkeypatch.setattr(
        flow_validation, "validate_dog_config_payload", _raise_validation
    )  # noqa: E501
    assert not is_dog_config_valid({"dog_id": "buddy", "dog_name": "Buddy"})

    monkeypatch.setattr(
        flow_validation,
        "validate_dog_config_payload",
        lambda *_args, **_kwargs: None,
    )
    assert is_dog_config_valid({"dog_id": "buddy", "dog_name": "Buddy"})


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"latitude": 52.5, "longitude": 13.4, "accuracy": 3.2, "battery_level": 80},
            True,
        ),  # noqa: E501
        ({"latitude": -91, "longitude": 13.4}, False),
        ({"latitude": 52.5, "longitude": 181}, False),
        ({"latitude": 52.5, "longitude": 13.4, "accuracy": -0.1}, False),
        ({"latitude": 52.5, "longitude": 13.4, "battery_level": 101}, False),
    ],
)
def test_is_gps_location_valid(payload: object, expected: bool) -> None:
    """GPS payload validation should enforce coordinate and sensor bounds."""
    assert is_gps_location_valid(payload) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"meal_type": "breakfast", "portion_size": 200, "food_type": "dry_food"},
            True,
        ),  # noqa: E501
        ({"meal_type": "invalid", "portion_size": 200}, False),
        ({"meal_type": "breakfast", "portion_size": -1}, False),
        ({"meal_type": "breakfast", "portion_size": 100, "calories": -3}, False),
    ],
)
def test_is_feeding_data_valid(payload: object, expected: bool) -> None:
    """Feeding payload validation should enforce meal and nutrition constraints."""
    assert is_feeding_data_valid(payload) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "mood": "happy",
                "activity_level": "normal",
                "health_status": "good",
                "weight": 20.0,
            },
            True,
        ),  # noqa: E501
        ({"mood": "confused"}, False),
        ({"activity_level": "extreme"}, False),
        ({"health_status": "critical"}, False),
        ({"temperature": 34.9}, False),
        ({"weight": 0}, False),
    ],
)
def test_is_health_data_valid(payload: object, expected: bool) -> None:
    """Health payload validation should reject out-of-range and unknown values."""
    assert is_health_data_valid(payload) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "title": "Walk Time",
                "message": "Buddy needs a walk",
                "priority": "high",
                "channel": "mobile",
            },
            True,
        ),  # noqa: E501
        ({"title": "", "message": "missing title"}, False),
        ({"title": "Title", "message": "   "}, False),
        ({"title": "Title", "message": "Body", "priority": "critical"}, False),
        ({"title": "Title", "message": "Body", "channel": "pager"}, False),
    ],
)
def test_is_notification_data_valid(payload: object, expected: bool) -> None:
    """Notification payloads require non-empty content and known enums."""
    assert is_notification_data_valid(payload) is expected
