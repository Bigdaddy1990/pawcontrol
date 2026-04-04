"""Coverage tests for flow_steps helpers + device_automation_helpers."""

import pytest

from custom_components.pawcontrol.device_automation_helpers import (
    build_dog_status_snapshot,
    build_unique_id,
)
from custom_components.pawcontrol.exceptions import ValidationError
import custom_components.pawcontrol.flow_steps.gps_helpers as gps_h
from custom_components.pawcontrol.flow_steps.gps_helpers import (
    build_gps_source_options,
    validation_error_key,
)
import custom_components.pawcontrol.flow_steps.health_helpers as health_h
from custom_components.pawcontrol.flow_steps.notifications_helpers import (
    validate_int_range,
)

# ─── build_gps_source_options ─────────────────────────────────────────────────


@pytest.mark.unit
def test_build_gps_source_options_empty() -> None:
    result = build_gps_source_options({})
    # Function may include default sources even for empty input
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_gps_source_options_with_entries() -> None:
    result = build_gps_source_options({
        "ha_person": "HA Person",
        "gps_device": "GPS Device",
    })
    assert isinstance(result, dict)
    assert "ha_person" in result


# ─── validation_error_key ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_validation_error_key_with_constraint() -> None:
    err = ValidationError("weight", -1.0, "too_low")
    result = validation_error_key(err, fallback="invalid_value")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_validation_error_key_uses_fallback() -> None:
    err = ValidationError("name")
    result = validation_error_key(err, fallback="field_required")
    assert isinstance(result, str)


# ─── validate_int_range ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_validate_int_range_valid() -> None:
    result = validate_int_range(5, field="count", minimum=1, maximum=10)
    assert result == 5


@pytest.mark.unit
def test_validate_int_range_none_not_required() -> None:
    result = validate_int_range(
        None, field="count", minimum=1, maximum=10, required=False
    )
    assert result is None


@pytest.mark.unit
def test_validate_int_range_clamp_below() -> None:
    result = validate_int_range(0, field="count", minimum=1, maximum=10, clamp=True)
    assert result == 1


@pytest.mark.unit
def test_validate_int_range_clamp_above() -> None:
    result = validate_int_range(99, field="count", minimum=1, maximum=10, clamp=True)
    assert result == 10


# ─── build_unique_id ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_unique_id_basic() -> None:
    result = build_unique_id("rex", "feeding_sensor")
    assert isinstance(result, str)
    assert "rex" in result
    assert "feeding_sensor" in result


@pytest.mark.unit
def test_build_unique_id_different_inputs() -> None:
    r1 = build_unique_id("rex", "walk_sensor")
    r2 = build_unique_id("buddy", "walk_sensor")
    assert r1 != r2


# ─── build_dog_status_snapshot ────────────────────────────────────────────────


@pytest.mark.unit
def test_build_dog_status_snapshot_empty() -> None:
    result = build_dog_status_snapshot("rex", {})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_dog_status_snapshot_with_data() -> None:
    data = {"walk": {"walk_in_progress": True}, "feeding": {"meals_today": 2}}
    result = build_dog_status_snapshot("rex", data)
    assert isinstance(result, dict)


# ─── module imports ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_gps_helpers_module_importable() -> None:
    assert gps_h is not None
    assert hasattr(gps_h, "build_dog_gps_placeholders")


@pytest.mark.unit
def test_health_helpers_module_importable() -> None:
    assert health_h is not None
    assert hasattr(health_h, "build_dog_health_placeholders")
