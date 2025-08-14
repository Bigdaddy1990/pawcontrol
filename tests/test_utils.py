import math
import types

import pytest

# Passe den Importpfad ggf. an deine Dateistruktur an:
from custom_components.pawcontrol.const import EARTH_RADIUS_M
from custom_components.pawcontrol.utils import (
    calculate_distance,
    calculate_speed_kmh,
    format_coordinates,
    safe_service_call,
    validate_coordinates,
)

# --------------------------
# calculate_distance tests
# --------------------------


def test_calculate_distance_identical_points():
    assert calculate_distance(52.52, 13.405, 52.52, 13.405) == 0.0


def test_calculate_distance_small_delta_longitude_equator():
    # At the equator, 0.001° longitude ≈ R * (0.001 * π/180) meters ≈ ~111.195 m
    lat1, lon1 = 0.0, 0.0
    lat2, lon2 = 0.0, 0.001
    expected = EARTH_RADIUS_M * (0.001 * math.pi / 180.0)
    d = calculate_distance(lat1, lon1, lat2, lon2)
    assert math.isclose(d, expected, rel_tol=0, abs_tol=0.5)


def test_calculate_distance_small_delta_latitude():
    # 0.001° latitude ≈ same as longitude at equator ~111.195 m
    lat1, lon1 = 0.0, 10.0
    lat2, lon2 = 0.001, 10.0
    expected = EARTH_RADIUS_M * (0.001 * math.pi / 180.0)
    d = calculate_distance(lat1, lon1, lat2, lon2)
    assert math.isclose(d, expected, rel_tol=0, abs_tol=0.5)


def test_calculate_distance_antipodal():
    # (0,0) and (0,180) are antipodal points -> distance = π * R
    lat1, lon1 = 0.0, 0.0
    lat2, lon2 = 0.0, 180.0
    expected = math.pi * EARTH_RADIUS_M
    d = calculate_distance(lat1, lon1, lat2, lon2)
    assert math.isclose(d, expected, rel_tol=1e-12, abs_tol=1e-6)


def test_calculate_distance_near_antipodal_stability():
    # Slightly off antipodal to stress floating-point stability (a ~ 1)
    lat1, lon1 = 10.0, 20.0
    lat2, lon2 = -10.0, 200.0 - 1e-9  # ~ antipodal but not exact
    d = calculate_distance(lat1, lon1, lat2, lon2)
    # Should be close to π * R but slightly less
    assert d < math.pi * EARTH_RADIUS_M
    assert d > 0.9 * math.pi * EARTH_RADIUS_M  # sanity bound


# --------------------------
# calculate_speed_kmh tests
# --------------------------


def test_calculate_speed_kmh_normal():
    # 1000 m in 100 s => 10 m/s => 36 km/h
    assert math.isclose(calculate_speed_kmh(1000.0, 100.0), 36.0, rel_tol=1e-12)


def test_calculate_speed_kmh_zero_duration():
    assert calculate_speed_kmh(1000.0, 0.0) == 0.0


def test_calculate_speed_kmh_near_zero_duration():
    assert calculate_speed_kmh(1000.0, 1e-12) == 0.0


def test_calculate_speed_kmh_non_finite_duration():
    assert calculate_speed_kmh(1000.0, float("inf")) == 0.0
    assert calculate_speed_kmh(1000.0, float("nan")) == 0.0


def test_calculate_speed_kmh_non_finite_distance():
    assert calculate_speed_kmh(float("inf"), 10.0) == 0.0
    assert calculate_speed_kmh(float("nan"), 10.0) == 0.0


# --------------------------
# validate_coordinates tests
# --------------------------


@pytest.mark.parametrize(
    "lat,lon,valid",
    [
        (0.0, 0.0, True),
        (52.52, 13.405, True),
        (-90.0, -180.0, True),
        (90.0, 180.0, True),
        (90.0001, 0.0, False),
        (-90.0001, 0.0, False),
        (0.0, 180.0001, False),
        (0.0, -180.0001, False),
        ("52.52", "13.405", True),  # coercible
        ("abc", 0.0, False),
        (0.0, "xyz", False),
        (True, 0.0, False),  # bool must be rejected explicitly
        (0.0, False, False),  # bool must be rejected explicitly
        (float("nan"), 0.0, False),
        (0.0, float("inf"), False),
    ],
)
def test_validate_coordinates(lat, lon, valid):
    assert validate_coordinates(lat, lon) is valid


# --------------------------
# format_coordinates tests
# --------------------------


def test_format_coordinates_rounding():
    out = format_coordinates(52.520006599, 13.404954)
    assert out == "52.520007,13.404954"


def test_format_coordinates_negative():
    out = format_coordinates(-33.865143, 151.209900)
    assert out == "-33.865143,151.209900"


# --------------------------
# safe_service_call tests
# --------------------------


class _FakeServices:
    def __init__(self, should_raise: bool = False):
        self.calls = []
        self.should_raise = should_raise

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))
        if self.should_raise:
            # Mimic HA behavior by raising a HomeAssistantError-like exception
            class FauxHAError(Exception):
                pass

            raise FauxHAError("simulated failure")


class _FakeHass:
    def __init__(self, should_raise: bool = False):
        self.services = _FakeServices(should_raise=should_raise)


@pytest.mark.asyncio
async def test_safe_service_call_success():
    hass = _FakeHass(should_raise=False)
    ok = await safe_service_call(
        hass, "notify", "persistent_notification", {"message": "hi"}, blocking=True
    )
    assert ok is True
    assert len(hass.services.calls) == 1
    domain, service, data, blocking = hass.services.calls[0]
    assert domain == "notify"
    assert service == "persistent_notification"
    assert data == {"message": "hi"}
    assert blocking is True


@pytest.mark.asyncio
async def test_safe_service_call_failure_returns_false():
    hass = _FakeHass(should_raise=True)
    ok = await safe_service_call(
        hass, "light", "turn_on", {"entity_id": "light.test"}, blocking=False
    )
    assert ok is False
    # Call should still be recorded even if it raised
    assert len(hass.services.calls) == 1
