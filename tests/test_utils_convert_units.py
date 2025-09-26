"""Tests for :mod:`custom_components.pawcontrol.utils.convert_units`."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.utils import convert_units


@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        (1.0, "kg", "lb", pytest.approx(2.20462)),
        (32.0, "f", "c", pytest.approx(0)),
        (5280.0, "ft", "mi", pytest.approx(1.0)),
    ],
)
def test_convert_units_known_conversion(
    value: float, from_unit: str, to_unit: str, expected: float
) -> None:
    """The helper converts between supported unit pairs."""

    assert convert_units(value, from_unit, to_unit) == expected


def test_convert_units_same_unit_returns_original_value() -> None:
    """No conversion is performed when the requested units match."""

    assert convert_units(10.0, "kg", "KG") == 10.0


def test_convert_units_unsupported_pair_raises_value_error() -> None:
    """Unsupported unit pairs produce a helpful :class:`ValueError`."""

    with pytest.raises(ValueError) as excinfo:
        convert_units(1.0, "lightyear", "m")

    message = str(excinfo.value)
    assert "lightyear" in message
    assert "available" in message
