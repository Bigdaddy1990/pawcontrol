"""Targeted coverage tests for garden_manager.py — pure helpers (0% → 16%+).

Covers: normalize_value (garden_manager re-export)
"""

import pytest

from custom_components.pawcontrol.garden_manager import normalize_value

# ═══════════════════════════════════════════════════════════════════════════════
# normalize_value (same semantics as walk_manager.normalize_value)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalize_value_int_passthrough() -> None:  # noqa: D103
    assert normalize_value(42) == 42


@pytest.mark.unit
def test_normalize_value_float_passthrough() -> None:  # noqa: D103
    assert normalize_value(3.14) == pytest.approx(3.14)


@pytest.mark.unit
def test_normalize_value_string_passthrough() -> None:  # noqa: D103
    assert normalize_value("hello") == "hello"


@pytest.mark.unit
def test_normalize_value_none_passthrough() -> None:  # noqa: D103
    assert normalize_value(None) is None


@pytest.mark.unit
def test_normalize_value_bool_passthrough() -> None:  # noqa: D103
    assert normalize_value(True) is True


@pytest.mark.unit
def test_normalize_value_dict() -> None:  # noqa: D103
    data = {"duration_minutes": 15, "poop_detected": True}
    result = normalize_value(data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_normalize_value_list() -> None:  # noqa: D103
    data = [1, "two", None]
    result = normalize_value(data)
    assert isinstance(result, list)


@pytest.mark.unit
def test_normalize_value_nested_dict() -> None:  # noqa: D103
    data = {"sessions": [{"start": "10:00", "duration": 20}]}
    result = normalize_value(data)
    assert isinstance(result, dict)
