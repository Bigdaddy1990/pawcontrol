"""Unit tests for PawControl sensor helper functions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from custom_components.pawcontrol.sensor import (
    MASS_GRAMS,
    MASS_KILOGRAMS,
    PERCENTAGE,
    SENSOR_MAPPING,
    UnitOfLength,
    UnitOfTime,
    _coerce_budget_remaining,
    _is_budget_exhausted,
    _normalise_attributes,
    _suggested_precision_from_unit,
    get_activity_score_cache_ttl,
    register_sensor,
)


@dataclass(slots=True)
class _CoordinatorStub:
    """Simple coordinator test double with an ``update_interval``."""

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
    assert (
        get_activity_score_cache_ttl(
            cast(object, _CoordinatorStub(_InvalidTotalSeconds()))
        )
        == 300
    )
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
    class _RegisteredSensor:
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


@dataclass(slots=True)
class _BudgetStub:
    """Budget test double exposing a ``remaining`` attribute."""

    remaining: object


def test_suggested_precision_from_unit_known_values() -> None:
    """Known units should map to stable display precision values."""
    assert _suggested_precision_from_unit(PERCENTAGE) == 0
    assert _suggested_precision_from_unit(UnitOfTime.HOURS) == 1
    assert _suggested_precision_from_unit(UnitOfLength.KILOMETERS) == 2
    assert _suggested_precision_from_unit(MASS_KILOGRAMS) == 1
    assert _suggested_precision_from_unit(MASS_GRAMS) == 0


def test_suggested_precision_from_unit_unknown_and_none() -> None:
    """Unsupported or missing units should not force precision."""
    assert _suggested_precision_from_unit("unsupported-unit") is None
    assert _suggested_precision_from_unit(None) is None


def test_get_activity_score_cache_ttl_defaults_for_missing_invalid_values() -> None:
    """Missing or invalid intervals should use the default TTL."""
    assert get_activity_score_cache_ttl(_CoordinatorStub(None)) == 300
    assert get_activity_score_cache_ttl(_CoordinatorStub(0)) == 300
    assert get_activity_score_cache_ttl(_CoordinatorStub("bad")) == 300


def test_get_activity_score_cache_ttl_clamps_to_expected_bounds() -> None:
    """TTL should clamp to the configured minimum and maximum bounds."""
    assert get_activity_score_cache_ttl(_CoordinatorStub(timedelta(seconds=10))) == 60
    assert get_activity_score_cache_ttl(_CoordinatorStub(timedelta(seconds=120))) == 300
    assert get_activity_score_cache_ttl(_CoordinatorStub(1000)) == 600


def test_coerce_budget_remaining_handles_supported_and_unsupported_values() -> None:
    """Budget coercion should parse numbers and ignore unsupported values."""
    assert _coerce_budget_remaining(None) is None
    assert _coerce_budget_remaining(object()) is None
    assert _coerce_budget_remaining(_BudgetStub(3)) == 3
    assert _coerce_budget_remaining(_BudgetStub(4.2)) == 4
    assert _coerce_budget_remaining(_BudgetStub("7")) == 7
    assert _coerce_budget_remaining(_BudgetStub("invalid")) is None
    assert _coerce_budget_remaining(_BudgetStub([1])) is None


def test_is_budget_exhausted_reflects_remaining_budget() -> None:
    """Exhaustion should only be true when remaining capacity is non-positive."""
    assert _is_budget_exhausted(None) is False
    assert _is_budget_exhausted(_BudgetStub(2)) is False
    assert _is_budget_exhausted(_BudgetStub(0)) is True
    assert _is_budget_exhausted(_BudgetStub(-1)) is True
