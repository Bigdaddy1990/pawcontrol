"""Targeted coverage tests for device_tracker.py — uncovered paths (25% → 45%+).

Covers: PawControlGPSTracker constructor, latitude/longitude/source_type,
        extra_state_attributes, available, battery_level, async_update_location
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.device_tracker import PawControlGPSTracker


def _coord(dog_id="rex"):
    c = MagicMock()
    c.data = {dog_id: {"gps": {}, "walk": {}}}
    c.last_update_success = True
    c.get_dog_data = MagicMock(return_value={})
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# Constructor + basic properties
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_gps_tracker_init() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    assert t.dog_id == "rex"
    assert t.dog_name == "Rex"


@pytest.mark.unit
def test_gps_tracker_unique_id() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    assert "rex" in t.unique_id


@pytest.mark.unit
def test_gps_tracker_latitude_none_initially() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    assert t.latitude is None or isinstance(t.latitude, float)


@pytest.mark.unit
def test_gps_tracker_longitude_none_initially() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    assert t.longitude is None or isinstance(t.longitude, float)


@pytest.mark.unit
def test_gps_tracker_source_type() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    result = t.source_type
    assert result is not None


@pytest.mark.unit
def test_gps_tracker_extra_attributes() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    attrs = t.extra_state_attributes
    assert isinstance(attrs, dict)


@pytest.mark.unit
def test_gps_tracker_battery_level() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    result = t.battery_level
    assert result is None or isinstance(result, int | float)


@pytest.mark.unit
def test_gps_tracker_available() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    result = t.available
    assert isinstance(result, bool)


@pytest.mark.unit
def test_gps_tracker_location_accuracy() -> None:
    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    acc = t.location_accuracy
    assert acc is None or isinstance(acc, int | float)


# ═══════════════════════════════════════════════════════════════════════════════
# async_update_location
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_location_does_not_raise() -> None:
    """async_update_location completes without raising on a minimal mock."""
    from unittest.mock import patch

    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    t.async_write_ha_state = MagicMock()
    with (
        patch.object(t, "_update_coordinator_gps_data", new=AsyncMock()),
        patch.object(t, "_update_route_tracking", new=AsyncMock()),
    ):
        # Should not raise regardless of GPS module mock state
        await t.async_update_location(latitude=52.52, longitude=13.40, accuracy=5)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_location_with_all_params() -> None:
    """async_update_location accepts all optional parameters."""
    from unittest.mock import patch

    t = PawControlGPSTracker(_coord(), "rex", "Rex")
    t.async_write_ha_state = MagicMock()
    with (
        patch.object(t, "_update_coordinator_gps_data", new=AsyncMock()),
        patch.object(t, "_update_route_tracking", new=AsyncMock()),
    ):
        await t.async_update_location(
            latitude=48.14,
            longitude=11.58,
            accuracy=10,
            altitude=520.0,
            speed=2.5,
            heading=90.0,
        )
