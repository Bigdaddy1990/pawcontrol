"""Coverage tests for GPS manager math and config normalization helpers."""

import math

from custom_components.pawcontrol.gps_manager import (
    _build_tracking_config,
    calculate_bearing,
    calculate_distance,
)


def test_build_tracking_config_uses_defaults_for_invalid_types() -> None:
    """Non-supported types should fall back to the documented defaults."""
    config = _build_tracking_config({
        "enabled": "yes",
        "auto_start_walk": None,
        "track_route": True,
        "safety_alerts": 1,
        "geofence_notifications": False,
        "auto_detect_home": "",
        "gps_accuracy_threshold": "50",
        "update_interval_seconds": True,
        "min_distance_for_point": object(),
        "route_smoothing": 0,
    })

    assert config.enabled is True
    assert config.auto_start_walk is True
    assert config.track_route is True
    assert config.safety_alerts is True
    assert config.geofence_notifications is False
    assert config.auto_detect_home is True
    assert config.accuracy_threshold == 50.0
    assert config.update_interval == 60
    assert config.min_distance_for_point == 10.0
    assert config.route_smoothing is True


def test_build_tracking_config_converts_numeric_values() -> None:
    """Numeric values should be normalized without boolean coercion leaks."""
    config = _build_tracking_config({
        "enabled": False,
        "auto_start_walk": False,
        "track_route": False,
        "safety_alerts": False,
        "geofence_notifications": True,
        "auto_detect_home": False,
        "gps_accuracy_threshold": 12,
        "update_interval_seconds": 25.8,
        "min_distance_for_point": 4,
        "route_smoothing": False,
    })

    assert config.enabled is False
    assert config.auto_start_walk is False
    assert config.track_route is False
    assert config.safety_alerts is False
    assert config.geofence_notifications is True
    assert config.auto_detect_home is False
    assert config.accuracy_threshold == 12.0
    assert config.update_interval == 25
    assert config.min_distance_for_point == 4.0
    assert config.route_smoothing is False


def test_calculate_distance_returns_zero_for_identical_points() -> None:
    """Distance should be zero for identical GPS coordinates."""
    assert calculate_distance(52.52, 13.405, 52.52, 13.405) == 0.0


def test_calculate_distance_returns_expected_range_for_one_degree_latitude() -> None:
    """Haversine distance should be close to 111.2km for one latitude degree."""
    distance_m = calculate_distance(0.0, 0.0, 1.0, 0.0)

    assert math.isclose(distance_m, 111_195.0, rel_tol=0.005)


def test_calculate_bearing_normalizes_to_compass_range() -> None:
    """Bearing helper should return normalized values in [0, 360)."""
    north = calculate_bearing(0.0, 0.0, 1.0, 0.0)
    east = calculate_bearing(0.0, 0.0, 0.0, 1.0)
    west = calculate_bearing(0.0, 0.0, 0.0, -1.0)

    assert 0.0 <= north < 360.0
    assert 0.0 <= east < 360.0
    assert 0.0 <= west < 360.0
    assert math.isclose(north, 0.0, abs_tol=1e-6)
    assert math.isclose(east, 90.0, abs_tol=1e-6)
    assert math.isclose(west, 270.0, abs_tol=1e-6)
