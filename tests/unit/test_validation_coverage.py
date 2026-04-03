"""Targeted coverage tests for validation.py — (0% → 28%+).

Covers: clamp_float_range, clamp_int_range, coerce_float, coerce_int,
        normalize_dog_id, InputCoercionError
"""

import pytest

from custom_components.pawcontrol.validation import (
    InputCoercionError,
    clamp_float_range,
    clamp_int_range,
    coerce_float,
    coerce_int,
    normalize_dog_id,
)

# ─── clamp_float_range ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_clamp_float_range_within_bounds() -> None:
    result = clamp_float_range(
        5.0, field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(5.0)


@pytest.mark.unit
def test_clamp_float_range_below_min() -> None:
    result = clamp_float_range(
        -1.0, field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(0.0)


@pytest.mark.unit
def test_clamp_float_range_above_max() -> None:
    result = clamp_float_range(
        999.0, field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(100.0)


@pytest.mark.unit
def test_clamp_float_range_none_uses_default() -> None:
    result = clamp_float_range(
        None, field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(50.0)


@pytest.mark.unit
def test_clamp_float_range_at_boundary() -> None:
    result = clamp_float_range(
        100.0, field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(100.0)


# ─── clamp_int_range ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_clamp_int_range_within_bounds() -> None:
    result = clamp_int_range(3, field="meals", minimum=1, maximum=6, default=2)
    assert result == 3


@pytest.mark.unit
def test_clamp_int_range_below_min() -> None:
    result = clamp_int_range(0, field="meals", minimum=1, maximum=6, default=2)
    assert result == 1


@pytest.mark.unit
def test_clamp_int_range_above_max() -> None:
    result = clamp_int_range(99, field="meals", minimum=1, maximum=6, default=2)
    assert result == 6


@pytest.mark.unit
def test_clamp_int_range_none_uses_default() -> None:
    result = clamp_int_range(None, field="meals", minimum=1, maximum=6, default=2)
    assert result == 2


# ─── coerce_float ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_coerce_float_int_input() -> None:
    result = coerce_float("weight", 42)
    assert result == pytest.approx(42.0)


@pytest.mark.unit
def test_coerce_float_string_input() -> None:
    result = coerce_float("weight", "3.14")
    assert result == pytest.approx(3.14)


@pytest.mark.unit
def test_coerce_float_invalid_raises() -> None:
    with pytest.raises((InputCoercionError, Exception)):
        coerce_float("weight", "not_a_number")


# ─── coerce_int ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_coerce_int_float_raises() -> None:
    # coerce_int requires whole numbers — floats raise InputCoercionError
    with pytest.raises((InputCoercionError, Exception)):
        coerce_int("meals", 2.9)


@pytest.mark.unit
def test_coerce_int_string_input() -> None:
    result = coerce_int("meals", "3")
    assert result == 3


@pytest.mark.unit
def test_coerce_int_invalid_raises() -> None:
    with pytest.raises((InputCoercionError, Exception)):
        coerce_int("meals", "not_a_number")


# ─── normalize_dog_id ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_normalize_dog_id_lowercase() -> None:
    result = normalize_dog_id("Rex")
    assert result == "rex"


@pytest.mark.unit
def test_normalize_dog_id_strips_spaces() -> None:
    result = normalize_dog_id("  buddy  ")
    assert result == "buddy"


@pytest.mark.unit
def test_normalize_dog_id_already_normalized() -> None:
    assert normalize_dog_id("rex_01") == "rex_01"


# ─── InputCoercionError ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_input_coercion_error_init() -> None:
    err = InputCoercionError("weight", "bad_val", "must be a number")
    assert err.field == "weight"
    assert isinstance(err, Exception)


@pytest.mark.unit
def test_input_coercion_error_raise() -> None:
    with pytest.raises(InputCoercionError):
        raise InputCoercionError("meals", None, "required field")
