"""Unit tests for PawControl sensor helper functions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from custom_components.pawcontrol.sensor import (
    SENSOR_MAPPING,
    _normalise_attributes,
    _suggested_precision_from_unit,
    get_activity_score_cache_ttl,
    register_sensor,
)


@dataclass(slots=True)
class _CoordinatorStub:
    """Minimal coordinator stub exposing update interval values."""

    update_interval: object | None


class _InvalidTotalSeconds:
    """Object whose ``total_seconds`` coercion fails."""

    def total_seconds(self) -> float:
        """Raise ``ValueError`` to exercise defensive handling."""
        raise ValueError("bad total seconds")


class _TypeErrorTotalSeconds:
    """Object whose ``total_seconds`` raises ``TypeError``."""

    def total_seconds(self) -> float:
        """Raise ``TypeError`` to exercise defensive handling."""
        raise TypeError("invalid type")


def test_suggested_precision_returns_expected_values() -> None:
    """Known units should return stable precision defaults."""
    assert _suggested_precision_from_unit("%") == 0
    assert _suggested_precision_from_unit("min") == 0
    assert _suggested_precision_from_unit("h") == 1
    assert _suggested_precision_from_unit("m") == 1
    assert _suggested_precision_from_unit("km") == 2


def test_suggested_precision_handles_none_and_unknown_units() -> None:
    """Unknown units should not force a precision."""
    assert _suggested_precision_from_unit(None) is None
    assert _suggested_precision_from_unit("unknown") is None


def test_activity_score_cache_ttl_defaults_when_missing_or_invalid() -> None:
    """Missing, invalid, and non-positive intervals should use default TTL."""
    assert get_activity_score_cache_ttl(cast(object, _CoordinatorStub(None))) == 300
    assert get_activity_score_cache_ttl(
        cast(object, _CoordinatorStub(_InvalidTotalSeconds()))
    ) == 300
    assert (
        get_activity_score_cache_ttl(
            cast(object, _CoordinatorStub(_TypeErrorTotalSeconds()))
        )
        == 300
    )
    assert get_activity_score_cache_ttl(cast(object, _CoordinatorStub(0))) == 300
    assert get_activity_score_cache_ttl(cast(object, _CoordinatorStub(-4))) == 300


def test_activity_score_cache_ttl_scales_with_update_interval() -> None:
    """Cache TTL should scale and clamp to documented limits."""
    assert (
        get_activity_score_cache_ttl(
            cast(object, _CoordinatorStub(timedelta(seconds=10)))
        )
        == 60
    )
    assert (
        get_activity_score_cache_ttl(
            cast(object, _CoordinatorStub(timedelta(seconds=120)))
        )
        == 300
    )
    assert get_activity_score_cache_ttl(cast(object, _CoordinatorStub(360.0))) == 600


def test_register_sensor_adds_class_to_mapping() -> None:
    """Decorator should register sensor classes in ``SENSOR_MAPPING``."""
    mapping_key = "unit_test_sensor"

    @register_sensor(mapping_key)
    class _RegisteredSensor:  # noqa: D401 - tiny inline test class
        """Inline class used to validate decorator wiring."""

    try:
        assert SENSOR_MAPPING[mapping_key] is _RegisteredSensor
    finally:
        SENSOR_MAPPING.pop(mapping_key, None)


def test_normalise_attributes_serialises_complex_values() -> None:
    """Attributes should be converted to JSON-safe payloads."""
    payload = {
        "timestamp": datetime(2026, 1, 2, 3, 4, 5),
        "duration": timedelta(minutes=5),
        "values": {"a", "b"},
        "opaque": object(),
    }

    normalised = _normalise_attributes(payload)

    assert normalised["timestamp"] == "2026-01-02T03:04:05"
    assert normalised["duration"] == "0:05:00"
    assert sorted(cast(list[str], normalised["values"])) == ["a", "b"]
    assert str(normalised["opaque"]).startswith("<object object at")
