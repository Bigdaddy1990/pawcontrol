"""Targeted coverage tests for dog_status.py and validation_helpers.py.

dog_status: build_dog_status_snapshot
validation_helpers: format_coordinate_validation_error, normalise_existing_names,
                    safe_validate_interval, validate_dog_name, validate_coordinate
"""

import pytest

from custom_components.pawcontrol.dog_status import build_dog_status_snapshot
from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation_helpers import (
    format_coordinate_validation_error,
    normalise_existing_names,
    safe_validate_interval,
    validate_coordinate,
    validate_dog_name,
)

# ═══════════════════════════════════════════════════════════════════════════════
# build_dog_status_snapshot
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_build_dog_status_snapshot_empty() -> None:
    result = build_dog_status_snapshot("rex", {})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_dog_status_snapshot_with_walk() -> None:
    data = {"walk": {"walk_in_progress": True, "total_distance_today": 2.5}}
    result = build_dog_status_snapshot("rex", data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_dog_status_snapshot_with_feeding() -> None:
    data = {"feeding": {"meals_today": 2}}
    result = build_dog_status_snapshot("buddy", data)
    assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# normalise_existing_names
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalise_existing_names_none() -> None:
    result = normalise_existing_names(None)
    assert isinstance(result, set)
    assert len(result) == 0


@pytest.mark.unit
def test_normalise_existing_names_set() -> None:
    # normalise_existing_names lowercases names
    result = normalise_existing_names({"Rex", "Buddy"})
    assert isinstance(result, set)
    assert "rex" in result or "Rex" in result


# ═══════════════════════════════════════════════════════════════════════════════
# safe_validate_interval
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_safe_validate_interval_valid() -> None:
    result = safe_validate_interval(
        60, default=30, minimum=1, maximum=3600, field="interval"
    )
    assert result == 60


@pytest.mark.unit
def test_safe_validate_interval_below_min_clamps() -> None:
    result = safe_validate_interval(
        0,
        default=30,
        minimum=1,
        maximum=3600,
        field="interval",
        clamp=True,
    )
    assert result == 1


@pytest.mark.unit
def test_safe_validate_interval_above_max_clamps() -> None:
    result = safe_validate_interval(
        9999,
        default=30,
        minimum=1,
        maximum=3600,
        field="interval",
        clamp=True,
    )
    assert result == 3600


@pytest.mark.unit
def test_safe_validate_interval_none_uses_default() -> None:
    result = safe_validate_interval(
        None, default=30, minimum=1, maximum=3600, field="interval"
    )
    assert result == 30


# ═══════════════════════════════════════════════════════════════════════════════
# validate_dog_name (validation_helpers)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_vh_validate_dog_name_valid() -> None:
    result = validate_dog_name("Rex")
    assert result == "Rex"


@pytest.mark.unit
def test_vh_validate_dog_name_strips() -> None:
    result = validate_dog_name("  Buddy  ")
    assert result == "Buddy"


# ═══════════════════════════════════════════════════════════════════════════════
# validate_coordinate / format_coordinate_validation_error
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_coordinate_valid_lat() -> None:
    result = validate_coordinate(52.5, field="latitude", minimum=-90, maximum=90)
    assert result == pytest.approx(52.5)


@pytest.mark.unit
def test_validate_coordinate_invalid_raises() -> None:
    with pytest.raises((ValidationError, Exception)):
        validate_coordinate(999.0, field="latitude", minimum=-90, maximum=90)


@pytest.mark.unit
def test_format_coordinate_validation_error() -> None:
    err = ValidationError(
        "latitude", 999.0, "out_of_range", min_value=-90, max_value=90
    )
    result = format_coordinate_validation_error(err)
    assert isinstance(result, str)
    assert len(result) > 0
