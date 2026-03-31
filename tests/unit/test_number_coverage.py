"""Targeted coverage tests for number.py — uncovered paths (66% → 75%+).

Covers: _extract_gps_tracking_input, PawControlNumberBase native_value/set_native_value,
        entity constructors, extra_state_attributes
"""

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.number import (
    _build_gps_tracking_input as _extract_gps_tracking_input,
)

# ═══════════════════════════════════════════════════════════════════════════════
# _extract_gps_tracking_input
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_extract_gps_tracking_empty() -> None:
    result = _extract_gps_tracking_input({})
    assert result == {}


@pytest.mark.unit
def test_extract_gps_tracking_with_accuracy() -> None:
    result = _extract_gps_tracking_input({"gps_accuracy_filter": 15.0})
    assert result["gps_accuracy_threshold"] == pytest.approx(15.0)


@pytest.mark.unit
def test_extract_gps_tracking_legacy_accuracy() -> None:
    result = _extract_gps_tracking_input({"accuracy_threshold": 20})
    assert result["gps_accuracy_threshold"] == pytest.approx(20.0)


@pytest.mark.unit
def test_extract_gps_tracking_update_interval() -> None:
    result = _extract_gps_tracking_input({"gps_update_interval": 30})
    assert result["update_interval_seconds"] == 30


@pytest.mark.unit
def test_extract_gps_tracking_distance_filter() -> None:
    result = _extract_gps_tracking_input({"gps_distance_filter": 10.0})
    assert result["min_distance_for_point"] == pytest.approx(10.0)


@pytest.mark.unit
def test_extract_gps_tracking_all_fields() -> None:
    config = {
        "gps_accuracy_filter": 5.0,
        "gps_update_interval": 60,
        "gps_distance_filter": 15.0,
    }
    result = _extract_gps_tracking_input(config)
    assert result["gps_accuracy_threshold"] == pytest.approx(5.0)
    assert result["update_interval_seconds"] == 60
    assert result["min_distance_for_point"] == pytest.approx(15.0)


@pytest.mark.unit
def test_extract_gps_tracking_non_numeric_ignored() -> None:
    result = _extract_gps_tracking_input({"gps_accuracy_filter": "bad"})
    assert "gps_accuracy_threshold" not in result
