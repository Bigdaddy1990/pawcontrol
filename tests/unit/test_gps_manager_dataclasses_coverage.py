"""Additional coverage for gps_manager dataclass helper branches."""

from datetime import timedelta

import pytest

from custom_components.pawcontrol.gps_manager import (
    GPSAccuracy,
    GPSPoint,
    GeofenceEvent,
    GeofenceEventType,
    GeofenceZone,
    LocationSource,
    RouteSegment,
    WalkRoute,
)


@pytest.mark.parametrize(
    ("accuracy", "expected_level", "expected_is_accurate"),
    [
        (None, GPSAccuracy.FAIR, True),
        (4.99, GPSAccuracy.EXCELLENT, True),
        (5.0, GPSAccuracy.GOOD, True),
        (14.99, GPSAccuracy.GOOD, True),
        (15.0, GPSAccuracy.FAIR, True),
        (49.99, GPSAccuracy.FAIR, True),
        (50.0, GPSAccuracy.POOR, False),
    ],
)
def test_gps_point_accuracy_properties_cover_thresholds(
    accuracy: float | None,
    expected_level: GPSAccuracy,
    expected_is_accurate: bool,
) -> None:
    """Accuracy helper properties should classify threshold boundaries correctly."""
    point = GPSPoint(latitude=52.52, longitude=13.405, accuracy=accuracy)

    assert point.accuracy_level is expected_level
    assert point.is_accurate is expected_is_accurate


def test_geofence_zone_contains_point_and_distance_helpers() -> None:
    """Geofence zones should include center point and exclude far-away locations."""
    zone = GeofenceZone(
        name="home",
        center_lat=52.52,
        center_lon=13.405,
        radius_meters=100.0,
    )

    assert zone.contains_point(52.52, 13.405) is True
    assert zone.contains_point(52.53, 13.415) is False
    assert zone.distance_to_center(52.52, 13.405) == 0.0


@pytest.mark.parametrize(
    ("event_type", "zone_type", "duration", "expected"),
    [
        (GeofenceEventType.BREACH, "safe_zone", timedelta(minutes=31), "high"),
        (GeofenceEventType.BREACH, "safe_zone", timedelta(minutes=10), "medium"),
        (GeofenceEventType.BREACH, "safe_zone", None, "medium"),
        (GeofenceEventType.EXITED, "safe_zone", None, "medium"),
        (GeofenceEventType.EXITED, "danger_zone", None, "low"),
        (GeofenceEventType.ENTERED, "safe_zone", None, "low"),
    ],
)
def test_geofence_event_severity_branches(
    event_type: GeofenceEventType,
    zone_type: str,
    duration: timedelta | None,
    expected: str,
) -> None:
    """Severity should reflect breach duration and safe-zone exit behavior."""
    zone = GeofenceZone(
        name="zone",
        center_lat=52.52,
        center_lon=13.405,
        radius_meters=150.0,
        zone_type=zone_type,
    )
    point = GPSPoint(
        latitude=52.52,
        longitude=13.405,
        source=LocationSource.MANUAL_INPUT,
    )
    event = GeofenceEvent(
        dog_id="dog-1",
        zone=zone,
        event_type=event_type,
        location=point,
        distance_from_center=200.0,
        duration_outside=duration,
    )

    assert event.severity == expected


def test_route_segment_and_walk_route_property_helpers() -> None:
    """Route dataclasses should expose consistent derived convenience values."""
    start = GPSPoint(latitude=52.52, longitude=13.405)
    end = GPSPoint(latitude=52.53, longitude=13.415)
    segment = RouteSegment(
        start_point=start,
        end_point=end,
        distance_meters=1200.0,
        duration_seconds=300.0,
    )
    active_route = WalkRoute(
        dog_id="dog-1",
        start_time=start.timestamp,
        total_distance_meters=1200.0,
        total_duration_seconds=300.0,
        avg_speed_mps=2.0,
    )
    completed_route = WalkRoute(
        dog_id="dog-1",
        start_time=start.timestamp,
        end_time=end.timestamp,
    )

    assert segment.duration_minutes == pytest.approx(5.0)
    assert segment.distance_km == pytest.approx(1.2)
    assert active_route.is_active is True
    assert completed_route.is_active is False
    assert active_route.duration_minutes == pytest.approx(5.0)
    assert active_route.distance_km == pytest.approx(1.2)
    assert active_route.avg_speed_kmh == pytest.approx(7.2)
    assert completed_route.avg_speed_kmh is None
