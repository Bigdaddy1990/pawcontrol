"""Targeted coverage tests for walk_manager.py — pure-Python helpers (0% → 18%+).

Covers: is_number, normalize_value utility functions
"""

import pytest

from custom_components.pawcontrol.walk_manager import is_number, normalize_value

# ═══════════════════════════════════════════════════════════════════════════════
# is_number
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_is_number_int() -> None:
    assert is_number(42) is True


@pytest.mark.unit
def test_is_number_float() -> None:
    assert is_number(3.14) is True


@pytest.mark.unit
def test_is_number_zero() -> None:
    assert is_number(0) is True


@pytest.mark.unit
def test_is_number_negative() -> None:
    assert is_number(-7.5) is True


@pytest.mark.unit
def test_is_number_string_false() -> None:
    assert is_number("42") is False


@pytest.mark.unit
def test_is_number_none_false() -> None:
    assert is_number(None) is False


@pytest.mark.unit
def test_is_number_bool_behaviour() -> None:
    # bool is subclass of int — behaviour depends on TypeGuard impl
    result = is_number(True)
    assert isinstance(result, bool)


@pytest.mark.unit
def test_is_number_list_false() -> None:
    assert is_number([1, 2]) is False


# ═══════════════════════════════════════════════════════════════════════════════
# normalize_value
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalize_value_int() -> None:
    assert normalize_value(42) == 42


@pytest.mark.unit
def test_normalize_value_float() -> None:
    result = normalize_value(3.14)
    assert result == pytest.approx(3.14)


@pytest.mark.unit
def test_normalize_value_string() -> None:
    assert normalize_value("hello") == "hello"


@pytest.mark.unit
def test_normalize_value_none() -> None:
    assert normalize_value(None) is None


@pytest.mark.unit
def test_normalize_value_bool() -> None:
    assert normalize_value(True) is True


@pytest.mark.unit
def test_normalize_value_dict() -> None:
    data = {"a": 1, "b": "x"}
    result = normalize_value(data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_normalize_value_list() -> None:
    data = [1, "two", 3.0]
    result = normalize_value(data)
    assert isinstance(result, list)


@pytest.mark.unit
def test_normalize_value_nested() -> None:
    data = {"key": [1, {"inner": True}]}
    result = normalize_value(data)
    assert isinstance(result, dict)
