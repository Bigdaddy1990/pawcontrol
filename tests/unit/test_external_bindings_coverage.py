"""Targeted coverage tests for external_bindings.py — uncovered paths (84% → 93%+).

Covers: _domain_store, _haversine_m, _extract_coords
"""

import math
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.external_bindings import (
    _domain_store,
    _extract_coords,
    _haversine_m,
)

# ═══════════════════════════════════════════════════════════════════════════════
# _haversine_m
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_haversine_same_point() -> None:
    assert _haversine_m(52.0, 13.0, 52.0, 13.0) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.unit
def test_haversine_berlin_to_munich() -> None:
    # ~504 km between Berlin and Munich
    dist = _haversine_m(52.5200, 13.4050, 48.1351, 11.5820)
    assert 500_000 < dist < 510_000


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_coords
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_extract_coords_valid() -> None:
    state = MagicMock()
    state.attributes = {"latitude": 52.5, "longitude": 13.4, "gps_accuracy": 10}
    lat, lon, acc, alt = _extract_coords(state)
    assert lat == pytest.approx(52.5)
    assert lon == pytest.approx(13.4)
    assert acc == pytest.approx(10.0)
    assert alt is None


@pytest.mark.unit
def test_extract_coords_no_attrs() -> None:
    state = MagicMock()
    state.attributes = None
    lat, lon, acc, alt = _extract_coords(state)
    assert lat is None and lon is None


@pytest.mark.unit
def test_extract_coords_missing_lat_lon() -> None:
    state = MagicMock()
    state.attributes = {"altitude": 100}
    lat, lon, acc, alt = _extract_coords(state)
    assert lat is None and lon is None


@pytest.mark.unit
def test_extract_coords_with_altitude() -> None:
    state = MagicMock()
    state.attributes = {"latitude": 48.1, "longitude": 11.6, "altitude": 520.0}
    lat, lon, acc, alt = _extract_coords(state)
    assert alt == pytest.approx(520.0)


# ═══════════════════════════════════════════════════════════════════════════════
# _domain_store
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_domain_store_creates_dict(mock_hass) -> None:
    mock_hass.data = {}
    store = _domain_store(mock_hass)
    assert isinstance(store, dict)
    assert DOMAIN in mock_hass.data


@pytest.mark.unit
def test_domain_store_resets_if_not_dict(mock_hass) -> None:
    mock_hass.data = {DOMAIN: "invalid"}
    store = _domain_store(mock_hass)
    assert isinstance(store, dict)
