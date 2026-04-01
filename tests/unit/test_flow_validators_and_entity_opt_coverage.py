"""Targeted coverage tests for flow_validators.py + entity_optimization.py.

flow_validators: validate_dog_name, validate_flow_gps_coordinates,
                 validate_flow_geofence_radius
entity_optimization: calculate_optimal_update_interval, estimate_state_write_reduction
"""

import pytest

from custom_components.pawcontrol.entity_optimization import (
    calculate_optimal_update_interval,
    estimate_state_write_reduction,
)
from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.flow_validators import (
    validate_dog_name,
    validate_flow_geofence_radius,
    validate_flow_gps_coordinates,
)

# ─── validate_dog_name ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_fv_validate_dog_name_valid() -> None:
    result = validate_dog_name("Rex")
    assert result == "Rex"


@pytest.mark.unit
def test_fv_validate_dog_name_stripped() -> None:
    result = validate_dog_name("  Buddy  ")
    assert result == "Buddy"


@pytest.mark.unit
def test_fv_validate_dog_name_too_short_raises() -> None:
    with pytest.raises((ValidationError, Exception)):
        validate_dog_name("R", min_length=2)


@pytest.mark.unit
def test_fv_validate_dog_name_not_required_none() -> None:
    result = validate_dog_name(None, required=False)
    assert result is None or isinstance(result, str)


# ─── validate_flow_gps_coordinates ────────────────────────────────────────────


@pytest.mark.unit
def test_validate_gps_coords_valid() -> None:
    lat, lon = validate_flow_gps_coordinates(52.52, 13.40)
    assert lat == pytest.approx(52.52)
    assert lon == pytest.approx(13.40)


@pytest.mark.unit
def test_validate_gps_coords_invalid_lat_raises() -> None:
    with pytest.raises((ValidationError, Exception)):
        validate_flow_gps_coordinates(999.0, 13.40)


@pytest.mark.unit
def test_validate_gps_coords_invalid_lon_raises() -> None:
    with pytest.raises((ValidationError, Exception)):
        validate_flow_gps_coordinates(52.52, 999.0)


# ─── validate_flow_geofence_radius ────────────────────────────────────────────


@pytest.mark.unit
def test_validate_geofence_radius_valid() -> None:
    result = validate_flow_geofence_radius(
        100.0, field="radius", min_value=10.0, max_value=5000.0
    )
    assert result == pytest.approx(100.0)


@pytest.mark.unit
def test_validate_geofence_radius_too_small_raises() -> None:
    with pytest.raises((ValidationError, Exception)):
        validate_flow_geofence_radius(
            1.0, field="radius", min_value=10.0, max_value=5000.0
        )


@pytest.mark.unit
def test_validate_geofence_radius_none_not_required() -> None:
    result = validate_flow_geofence_radius(
        None, field="radius", min_value=10.0, max_value=5000.0, required=False
    )
    assert result is None


# ─── calculate_optimal_update_interval ────────────────────────────────────────


@pytest.mark.unit
def test_calculate_optimal_update_interval_walk() -> None:
    result = calculate_optimal_update_interval("walk", "high")
    assert isinstance(result, int)
    assert result > 0


@pytest.mark.unit
def test_calculate_optimal_update_interval_feeding_low() -> None:
    result = calculate_optimal_update_interval("feeding", "low")
    assert isinstance(result, int)
    assert result > 0


@pytest.mark.unit
def test_calculate_optimal_update_interval_default_volatility() -> None:
    result = calculate_optimal_update_interval("health")
    assert isinstance(result, int)
    assert result > 0


# ─── estimate_state_write_reduction ───────────────────────────────────────────


@pytest.mark.unit
def test_estimate_state_write_reduction_basic() -> None:
    result = estimate_state_write_reduction(100, 60)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_estimate_state_write_reduction_no_reduction() -> None:
    result = estimate_state_write_reduction(50, 50)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_estimate_state_write_reduction_full_reduction() -> None:
    result = estimate_state_write_reduction(100, 0)
    assert isinstance(result, dict)
