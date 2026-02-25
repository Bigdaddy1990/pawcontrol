"""Unit tests for sensor module helper functions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from custom_components.pawcontrol.sensor import (
    MASS_GRAMS,
    MASS_KILOGRAMS,
    PERCENTAGE,
    UnitOfLength,
    UnitOfTime,
    _coerce_budget_remaining,
    _is_budget_exhausted,
    _suggested_precision_from_unit,
    get_activity_score_cache_ttl,
)


@dataclass(slots=True)
class _CoordinatorStub:
    """Simple coordinator test double with an ``update_interval``."""

    update_interval: object | None


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
