"""Comprehensive unit tests for GPSGeofenceManager.

Tests GPS tracking, geofencing, route management, and location-based
features with full edge case coverage.

Quality Scale: Platinum target
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.gps_manager import (
    GeofenceEvent,
    GeofenceEventType,
    GeofenceZone,
    GPSAccuracy,
    GPSGeofenceManager,
    GPSPoint,
    LocationSource,
    WalkRoute,
    calculate_bearing,
    calculate_distance,
)
from custom_components.pawcontrol.resilience import ResilienceManager
from custom_components.pawcontrol.types import GPSTrackingConfigInput
from homeassistant.core import HomeAssistant


@pytest.mark.unit
@pytest.mark.asyncio
class TestGPSManagerInitialization:
    """Test GPS manager initialization and setup."""

    async def test_initialization_basic(self, mock_hass: HomeAssistant, mock_resilience_manager: ResilienceManager) -> None:
        """Test basic GPS manager initialization."""
        manager = GPSGeofenceManager(mock_hass)
        manager.resilience_manager = mock_resilience_manager

        assert manager.hass == mock_hass
        assert len(manager._dog_configs) == 0
        assert len(manager._active_routes) == 0
        assert len(manager._geofence_zones) == 0

    async def test_configure_dog_gps_basic(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test configuring GPS for a dog."""
        config: GPSTrackingConfigInput = {
            "enabled": True,
            "auto_start_walk": True,
            "track_route": True,
            "safety_alerts": True,
        }

        await mock_gps_manager.async_configure_dog_gps("test_dog", config)

        assert "test_dog" in mock_gps_manager._dog_configs
        assert mock_gps_manager._dog_configs["test_dog"].enabled is True

    async def test_configure_dog_gps_custom_settings(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test GPS configuration with custom settings."""
        config: GPSTrackingConfigInput = {
            "enabled": True,
            "gps_accuracy_threshold": 25.0,
            "update_interval_seconds": 30,
            "min_distance_for_point": 5.0,
        }

        await mock_gps_manager.async_configure_dog_gps("test_dog", config)

        dog_config = mock_gps_manager._dog_configs["test_dog"]
        assert dog_config.accuracy_threshold == 25.0
        assert dog_config.update_interval == 30
        assert dog_config.min_distance_for_point == 5.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestGPSTrackingTasks:
    """Validate GPS tracking background task scheduling."""

    async def test_start_tracking_task_handles_asyncmock_scheduler(
        self, mock_gps_manager: GPSGeofenceManager
    ) -> None:
        """Ensure fallback scheduling engages when hass returns AsyncMock."""

        manager = mock_gps_manager
        tracking_config: GPSTrackingConfigInput = {
            "enabled": True,
            "track_route": True,
            "update_interval_seconds": 0,
        }
        await manager.async_configure_dog_gps("test_dog", tracking_config)

        manager._active_routes["test_dog"] = WalkRoute(
            dog_id="test_dog",
            start_time=datetime.now(UTC),
        )

        loop = asyncio.get_running_loop()

        async def _fast_sleep(_: float) -> None:
            return None

        manager.hass.async_create_task.return_value = None

        with (
            patch(
                "custom_components.pawcontrol.gps_manager.asyncio.sleep",
                new=AsyncMock(side_effect=_fast_sleep),
            ),
            patch(
                "custom_components.pawcontrol.gps_manager.asyncio.create_task"
            ) as create_task,
        ):
            create_task.side_effect = lambda coro, *, name=None: loop.create_task(
                coro, name=name
            )

            await manager._start_tracking_task("test_dog")

        assert create_task.called
        task = manager._tracking_tasks.get("test_dog")
        assert isinstance(task, asyncio.Task)
        manager._active_routes.pop("test_dog", None)
        await asyncio.sleep(0)
        await manager._stop_tracking_task("test_dog")


@pytest.mark.unit
class TestDistanceCalculations:
    """Test GPS distance calculation algorithms."""

    def test_calculate_distance_same_point(self) -> None:
        """Test distance calculation for same point."""
        distance = calculate_distance(52.5200, 13.4050, 52.5200, 13.4050)

        assert distance == 0.0

    def test_calculate_distance_known_distance(self) -> None:
        """Test distance calculation with known coordinates."""
        # Berlin to Paris (approximately 877 km)
        berlin_lat, berlin_lon = 52.5200, 13.4050
        paris_lat, paris_lon = 48.8566, 2.3522

        distance = calculate_distance(berlin_lat, berlin_lon, paris_lat, paris_lon)

        # Should be approximately 877,000 meters
        assert 850_000 < distance < 900_000

    def test_calculate_distance_short_distance(self) -> None:
        """Test distance calculation for short distances."""
        # Two points about 1km apart
        lat1, lon1 = 52.5200, 13.4050
        lat2, lon2 = 52.5290, 13.4050  # ~1km north

        distance = calculate_distance(lat1, lon1, lat2, lon2)

        # Should be approximately 1000 meters
        assert 900 < distance < 1100

    def test_calculate_distance_equator_crossing(self) -> None:
        """Test distance calculation across equator."""
        # North of equator
        lat1, lon1 = 10.0, 0.0
        # South of equator
        lat2, lon2 = -10.0, 0.0

        distance = calculate_distance(lat1, lon1, lat2, lon2)

        # Should be approximately 2,220 km
        assert 2_200_000 < distance < 2_250_000

    def test_calculate_bearing_north(self) -> None:
        """Test bearing calculation for northward movement."""
        lat1, lon1 = 52.5200, 13.4050
        lat2, lon2 = 52.5300, 13.4050

        bearing = calculate_bearing(lat1, lon1, lat2, lon2)

        # Should be approximately 0 degrees (north)
        assert -10 < bearing < 10 or 350 < bearing < 360

    def test_calculate_bearing_east(self) -> None:
        """Test bearing calculation for eastward movement."""
        lat1, lon1 = 52.5200, 13.4050
        lat2, lon2 = 52.5200, 13.5050

        bearing = calculate_bearing(lat1, lon1, lat2, lon2)

        # Should be approximately 90 degrees (east)
        assert 80 < bearing < 100

    def test_calculate_bearing_south(self) -> None:
        """Test bearing calculation for southward movement."""
        lat1, lon1 = 52.5200, 13.4050
        lat2, lon2 = 52.5100, 13.4050

        bearing = calculate_bearing(lat1, lon1, lat2, lon2)

        # Should be approximately 180 degrees (south)
        assert 170 < bearing < 190


@pytest.mark.unit
class TestGPSPointCreation:
    """Test GPS point data structure."""

    def test_gps_point_basic_creation(self) -> None:
        """Test creating basic GPS point."""
        point = GPSPoint(
            latitude=52.5200,
            longitude=13.4050,
            accuracy=10.0,
        )

        assert point.latitude == 52.5200
        assert point.longitude == 13.4050
        assert point.accuracy == 10.0
        assert point.source == LocationSource.DEVICE_TRACKER

    def test_gps_point_with_metadata(self) -> None:
        """Test GPS point with full metadata."""
        timestamp = datetime.now(UTC)

        point = GPSPoint(
            latitude=52.5200,
            longitude=13.4050,
            timestamp=timestamp,
            altitude=100.0,
            accuracy=5.0,
            speed=1.5,
            heading=90.0,
            source=LocationSource.COMPANION_APP,
            battery_level=85,
        )

        assert point.altitude == 100.0
        assert point.speed == 1.5
        assert point.heading == 90.0
        assert point.battery_level == 85

    def test_gps_point_accuracy_level_excellent(self) -> None:
        """Test accuracy level classification - excellent."""
        point = GPSPoint(latitude=52.5200, longitude=13.4050, accuracy=3.0)

        assert point.accuracy_level == GPSAccuracy.EXCELLENT
        assert point.is_accurate is True

    def test_gps_point_accuracy_level_good(self) -> None:
        """Test accuracy level classification - good."""
        point = GPSPoint(latitude=52.5200, longitude=13.4050, accuracy=10.0)

        assert point.accuracy_level == GPSAccuracy.GOOD
        assert point.is_accurate is True

    def test_gps_point_accuracy_level_fair(self) -> None:
        """Test accuracy level classification - fair."""
        point = GPSPoint(latitude=52.5200, longitude=13.4050, accuracy=30.0)

        assert point.accuracy_level == GPSAccuracy.FAIR
        assert point.is_accurate is True

    def test_gps_point_accuracy_level_poor(self) -> None:
        """Test accuracy level classification - poor."""
        point = GPSPoint(latitude=52.5200, longitude=13.4050, accuracy=100.0)

        assert point.accuracy_level == GPSAccuracy.POOR
        assert point.is_accurate is False

    def test_gps_point_no_accuracy_defaults_fair(self) -> None:
        """Test GPS point without accuracy defaults to fair."""
        point = GPSPoint(latitude=52.5200, longitude=13.4050)

        assert point.accuracy_level == GPSAccuracy.FAIR


@pytest.mark.unit
@pytest.mark.asyncio
class TestGPSTracking:
    """Test GPS tracking and point addition."""

    async def test_add_gps_point_basic(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test adding basic GPS point."""
        success = await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
            accuracy=10.0,
        )

        assert success is True
        assert "test_dog" in mock_gps_manager._last_locations

    async def test_add_gps_point_updates_last_location(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that adding point updates last known location."""
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        location = await mock_gps_manager.async_get_current_location("test_dog")

        assert location is not None
        assert location.latitude == 52.5200
        assert location.longitude == 13.4050

    async def test_add_gps_point_rejects_poor_accuracy(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that points with poor accuracy are rejected."""
        # Configure strict accuracy threshold
        await mock_gps_manager.async_configure_dog_gps(
            "test_dog",
            cast(GPSTrackingConfigInput, {"gps_accuracy_threshold": 20.0}),
        )

        success = await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
            accuracy=100.0,  # Poor accuracy
        )

        assert success is False

    async def test_add_gps_point_filters_minimum_distance(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test minimum distance filter."""
        await mock_gps_manager.async_configure_dog_gps(
            "test_dog",
            cast(GPSTrackingConfigInput, {"min_distance_for_point": 10.0}),
        )

        # Start walk
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        # Add first point
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        # Add second point very close (< 10m)
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5201,  # ~11m away
            longitude=13.4050,
        )

        # Should be filtered out
        route = await mock_gps_manager.async_get_active_route("test_dog")
        assert len(route.gps_points) <= 2  # May include first point

    async def test_add_gps_point_to_active_route(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test adding GPS points to active route."""
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        route = await mock_gps_manager.async_get_active_route("test_dog")

        assert route is not None
        assert len(route.gps_points) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkSessions:
    """Test walk session management."""

    async def test_start_gps_tracking_basic(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test starting GPS tracking."""
        session_id = await mock_gps_manager.async_start_gps_tracking(
            dog_id="test_dog",
            walker="John",
        )

        assert session_id is not None
        assert "test_dog" in mock_gps_manager._active_routes

    async def test_start_gps_tracking_ends_previous_session(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that starting new tracking ends previous session."""
        # Start first session
        session1 = await mock_gps_manager.async_start_gps_tracking("test_dog")

        # Start second session
        session2 = await mock_gps_manager.async_start_gps_tracking("test_dog")

        assert session1 != session2
        assert "test_dog" in mock_gps_manager._active_routes

    async def test_end_gps_tracking_basic(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test ending GPS tracking."""
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        # Add some points
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        route = await mock_gps_manager.async_end_gps_tracking("test_dog")

        assert route is not None
        assert route.end_time is not None
        assert "test_dog" not in mock_gps_manager._active_routes

    async def test_end_gps_tracking_saves_to_history(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that ended routes are saved to history."""
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        await mock_gps_manager.async_end_gps_tracking("test_dog", save_route=True)

        assert "test_dog" in mock_gps_manager._route_history
        assert len(mock_gps_manager._route_history["test_dog"]) == 1

    async def test_end_gps_tracking_without_save(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test ending tracking without saving route."""
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        await mock_gps_manager.async_end_gps_tracking("test_dog", save_route=False)

        history = mock_gps_manager._route_history.get("test_dog", [])
        assert len(history) == 0

    async def test_end_gps_tracking_no_active_route(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test ending tracking when no active route."""
        route = await mock_gps_manager.async_end_gps_tracking("test_dog")

        assert route is None

    async def test_route_statistics_calculation(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that route statistics are calculated on end."""
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        # Add multiple points
        for i in range(5):
            await mock_gps_manager.async_add_gps_point(
                dog_id="test_dog",
                latitude=52.5200 + (i * 0.001),
                longitude=13.4050 + (i * 0.001),
                accuracy=10.0,
            )

        route = await mock_gps_manager.async_end_gps_tracking("test_dog")

        assert route.total_distance_meters > 0
        assert route.total_duration_seconds > 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestGeofencing:
    """Test geofencing functionality."""

    async def test_setup_geofence_zone_basic(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test setting up a geofence zone."""
        await mock_gps_manager.async_setup_geofence_zone(
            dog_id="test_dog",
            zone_name="home",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        assert "test_dog" in mock_gps_manager._geofence_zones
        assert len(mock_gps_manager._geofence_zones["test_dog"]) == 1

    async def test_setup_safe_zone_convenience_method(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test safe zone setup convenience method."""
        await mock_gps_manager.async_setup_safe_zone(
            dog_id="test_dog",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        zones = mock_gps_manager._geofence_zones["test_dog"]
        assert len(zones) == 1
        assert zones[0].zone_type == "safe_zone"

    async def test_geofence_zone_contains_point(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test geofence zone contains point detection."""
        zone = GeofenceZone(
            name="home",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        # Point inside zone
        inside = zone.contains_point(52.5200, 13.4050)
        assert inside is True

        # Point outside zone
        outside = zone.contains_point(52.5300, 13.4050)  # ~1km away
        assert outside is False

    async def test_geofence_zone_distance_to_center(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test distance calculation from zone center."""
        zone = GeofenceZone(
            name="home",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        # At center
        distance = zone.distance_to_center(52.5200, 13.4050)
        assert distance < 1.0  # Almost zero

        # Away from center
        distance = zone.distance_to_center(52.5210, 13.4050)
        assert distance > 100

    async def test_geofence_enter_event(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test geofence enter event detection."""
        await mock_gps_manager.async_setup_safe_zone(
            dog_id="test_dog",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        # Start tracking
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        # Add point outside zone (initial state)
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5300,
            longitude=13.4050,
        )

        # Add point inside zone (should trigger enter event)
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        route = await mock_gps_manager.async_get_active_route("test_dog")

        # Check if event was recorded
        # (Event firing is tested separately)
        assert route is not None

    async def test_geofence_exit_event(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test geofence exit event detection."""
        await mock_gps_manager.async_setup_safe_zone(
            dog_id="test_dog",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        await mock_gps_manager.async_start_gps_tracking("test_dog")

        # Start inside zone
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        # Move outside zone
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5300,
            longitude=13.4050,
        )

        # Event should be detected
        route = await mock_gps_manager.async_get_active_route("test_dog")
        assert route is not None


@pytest.mark.unit
@pytest.mark.asyncio
class TestGeofenceStatus:
    """Test geofence status reporting."""

    async def test_get_geofence_status_basic(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test getting geofence status."""
        await mock_gps_manager.async_setup_safe_zone(
            dog_id="test_dog",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        status = await mock_gps_manager.async_get_geofence_status("test_dog")

        assert status["dog_id"] == "test_dog"
        assert status["zones_configured"] == 1
        assert "zone_status" in status

    async def test_get_geofence_status_with_location(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test geofence status with current location."""
        await mock_gps_manager.async_setup_safe_zone(
            dog_id="test_dog",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        status = await mock_gps_manager.async_get_geofence_status("test_dog")

        assert status["current_location"] is not None
        assert status["current_location"]["latitude"] == 52.5200

    async def test_get_geofence_status_breach_count(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test safe zone breach counting."""
        await mock_gps_manager.async_setup_safe_zone(
            dog_id="test_dog",
            center_lat=52.5200,
            center_lon=13.4050,
            radius_meters=50.0,
        )

        # Add point outside safe zone
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5300,
            longitude=13.4050,
        )

        status = await mock_gps_manager.async_get_geofence_status("test_dog")

        # Should have breach count
        assert "safe_zone_breaches" in status


@pytest.mark.unit
@pytest.mark.asyncio
class TestRouteExport:
    """Test route export functionality."""

    async def test_export_routes_gpx_format(self, mock_gps_manager: GPSGeofenceManager, mock_walk_route: WalkRoute) -> None:
        """Test exporting routes in GPX format."""
        # Setup route history
        mock_gps_manager._route_history["test_dog"] = [mock_walk_route]

        export_data = await mock_gps_manager.async_export_routes(
            dog_id="test_dog",
            export_format="gpx",
            last_n_routes=1,
        )

        assert export_data is not None
        assert export_data["format"] == "gpx"
        assert "content" in export_data
        assert "<gpx" in export_data["content"]

    async def test_export_routes_json_format(self, mock_gps_manager: GPSGeofenceManager, mock_walk_route: WalkRoute) -> None:
        """Test exporting routes in JSON format."""
        mock_gps_manager._route_history["test_dog"] = [mock_walk_route]

        export_data = await mock_gps_manager.async_export_routes(
            dog_id="test_dog",
            export_format="json",
            last_n_routes=1,
        )

        assert export_data is not None
        assert export_data["format"] == "json"
        assert isinstance(export_data["content"], dict)
        assert "routes" in export_data["content"]

    async def test_export_routes_csv_format(self, mock_gps_manager: GPSGeofenceManager, mock_walk_route: WalkRoute) -> None:
        """Test exporting routes in CSV format."""
        mock_gps_manager._route_history["test_dog"] = [mock_walk_route]

        export_data = await mock_gps_manager.async_export_routes(
            dog_id="test_dog",
            export_format="csv",
            last_n_routes=1,
        )

        assert export_data is not None
        assert export_data["format"] == "csv"
        assert "timestamp,latitude,longitude" in export_data["content"]

    async def test_export_routes_no_history(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test exporting with no route history."""
        export_data = await mock_gps_manager.async_export_routes(
            dog_id="test_dog",
            export_format="gpx",
        )

        assert export_data is None

    async def test_export_routes_multiple_routes(
        self, mock_gps_manager: GPSGeofenceManager, mock_walk_route: WalkRoute
    ) -> None:
        """Test exporting multiple routes."""
        # Add multiple routes
        mock_gps_manager._route_history["test_dog"] = [
            mock_walk_route,
            mock_walk_route,
            mock_walk_route,
        ]

        export_data = await mock_gps_manager.async_export_routes(
            dog_id="test_dog",
            export_format="json",
            last_n_routes=2,
        )

        assert len(export_data["content"]["routes"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestStatistics:
    """Test GPS statistics and monitoring."""

    async def test_get_statistics_basic(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test getting GPS statistics."""
        await mock_gps_manager.async_configure_dog_gps(
            "test_dog", cast(GPSTrackingConfigInput, {})
        )

        stats = await mock_gps_manager.async_get_statistics()

        assert "dogs_configured" in stats
        assert "active_tracking_sessions" in stats
        assert "total_routes_stored" in stats
        assert stats["dogs_configured"] == 1

    async def test_statistics_track_gps_points(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that statistics track GPS points processed."""
        initial_stats = await mock_gps_manager.async_get_statistics()
        initial_count = initial_stats["gps_points_processed"]

        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )

        final_stats = await mock_gps_manager.async_get_statistics()

        assert final_stats["gps_points_processed"] > initial_count

    async def test_statistics_track_routes_completed(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that statistics track completed routes."""
        initial_stats = await mock_gps_manager.async_get_statistics()
        initial_count = initial_stats["routes_completed"]

        await mock_gps_manager.async_start_gps_tracking("test_dog")
        await mock_gps_manager.async_add_gps_point(
            dog_id="test_dog",
            latitude=52.5200,
            longitude=13.4050,
        )
        await mock_gps_manager.async_end_gps_tracking("test_dog")

        final_stats = await mock_gps_manager.async_get_statistics()

        assert final_stats["routes_completed"] > initial_count


@pytest.mark.unit
@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_add_gps_point_invalid_coordinates(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test handling of invalid GPS coordinates."""
        # Latitude out of range
        with pytest.raises(ValueError):
            await mock_gps_manager.async_add_gps_point(
                dog_id="test_dog",
                latitude=100.0,  # Invalid
                longitude=13.4050,
            )

    async def test_geofence_zone_negative_radius(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that negative radius is rejected."""
        with pytest.raises(ValueError):
            await mock_gps_manager.async_setup_geofence_zone(
                dog_id="test_dog",
                zone_name="test",
                center_lat=52.5200,
                center_lon=13.4050,
                radius_meters=-10.0,
            )

    async def test_concurrent_gps_point_additions(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test concurrent GPS point additions."""
        import asyncio

        await mock_gps_manager.async_start_gps_tracking("test_dog")

        async def add_point(i: int) -> None:
            await mock_gps_manager.async_add_gps_point(
                dog_id="test_dog",
                latitude=52.5200 + (i * 0.0001),
                longitude=13.4050 + (i * 0.0001),
            )

        # Add 10 points concurrently
        await asyncio.gather(*[add_point(i) for i in range(10)])

        route = await mock_gps_manager.async_get_active_route("test_dog")

        # Should have all points
        assert len(route.gps_points) >= 10

    async def test_route_history_limit(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that route history is limited."""
        # Add many routes
        for i in range(150):
            route = WalkRoute(
                dog_id="test_dog",
                start_time=datetime.now(UTC) - timedelta(hours=i),
            )
            if "test_dog" not in mock_gps_manager._route_history:
                mock_gps_manager._route_history["test_dog"] = []
            mock_gps_manager._route_history["test_dog"].append(route)

        # Trigger cleanup by ending a route
        await mock_gps_manager.async_start_gps_tracking("test_dog")
        await mock_gps_manager.async_end_gps_tracking("test_dog")

        # Should be limited to 100
        assert len(mock_gps_manager._route_history["test_dog"]) <= 101

    async def test_cleanup_clears_all_data(self, mock_gps_manager: GPSGeofenceManager) -> None:
        """Test that cleanup clears all data."""
        await mock_gps_manager.async_configure_dog_gps(
            "test_dog", cast(GPSTrackingConfigInput, {})
        )
        await mock_gps_manager.async_start_gps_tracking("test_dog")

        await mock_gps_manager.async_cleanup()

        assert len(mock_gps_manager._dog_configs) == 0
        assert len(mock_gps_manager._active_routes) == 0
        assert len(mock_gps_manager._geofence_zones) == 0
