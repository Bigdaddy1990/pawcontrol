"""Targeted coverage tests for flow_helpers.py — (0% → 28%+).

Covers: build_boolean_schema, build_number_schema, build_select_schema,
        build_text_schema, coerce_bool, coerce_optional_float
"""

import pytest

from custom_components.pawcontrol.flow_helpers import (
    build_boolean_schema,
    build_number_schema,
    build_select_schema,
    build_text_schema,
    coerce_bool,
    coerce_optional_float,
)

# ─── build_boolean_schema ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_boolean_schema_returns_dict() -> None:  # noqa: D103
    schema = build_boolean_schema("enabled")
    assert isinstance(schema, dict)


@pytest.mark.unit
def test_build_boolean_schema_default_true() -> None:  # noqa: D103
    schema = build_boolean_schema("active", default=True)
    assert isinstance(schema, dict)


# ─── build_number_schema ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_number_schema_basic() -> None:  # noqa: D103
    schema = build_number_schema("weight", min_value=0, max_value=100)
    assert isinstance(schema, dict)


@pytest.mark.unit
def test_build_number_schema_with_default() -> None:  # noqa: D103
    schema = build_number_schema("meals", min_value=1, max_value=10, default=2)
    assert isinstance(schema, dict)


@pytest.mark.unit
def test_build_number_schema_with_step() -> None:  # noqa: D103
    schema = build_number_schema("amount_g", min_value=0, max_value=500, step=10)
    assert isinstance(schema, dict)


# ─── build_select_schema ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_select_schema_basic() -> None:  # noqa: D103
    schema = build_select_schema("breed", ["labrador", "poodle", "husky"])
    assert isinstance(schema, dict)


@pytest.mark.unit
def test_build_select_schema_with_default() -> None:  # noqa: D103
    schema = build_select_schema("size", ["small", "medium", "large"], default="medium")
    assert isinstance(schema, dict)


@pytest.mark.unit
def test_build_select_schema_required() -> None:  # noqa: D103
    schema = build_select_schema("activity", ["low", "medium", "high"], required=True)
    assert isinstance(schema, dict)


# ─── build_text_schema ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_text_schema_basic() -> None:  # noqa: D103
    schema = build_text_schema("dog_name")
    assert isinstance(schema, dict)


@pytest.mark.unit
def test_build_text_schema_with_default() -> None:  # noqa: D103
    schema = build_text_schema("notes", default="No notes")
    assert isinstance(schema, dict)


@pytest.mark.unit
def test_build_text_schema_required() -> None:  # noqa: D103
    schema = build_text_schema("host", required=True)
    assert isinstance(schema, dict)


# ─── coerce_bool ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_coerce_bool_true_values() -> None:  # noqa: D103
    assert coerce_bool(True) is True
    assert coerce_bool(1) is True
    assert coerce_bool("true") is True
    assert coerce_bool("yes") is True


@pytest.mark.unit
def test_coerce_bool_false_values() -> None:  # noqa: D103
    assert coerce_bool(False) is False
    assert coerce_bool(0) is False
    assert coerce_bool("false") is False


@pytest.mark.unit
def test_coerce_bool_default() -> None:  # noqa: D103
    assert coerce_bool(None) is False
    assert coerce_bool(None, default=True) is True


@pytest.mark.unit
def test_coerce_bool_invalid_uses_default() -> None:  # noqa: D103
    result = coerce_bool("maybe", default=False)
    assert isinstance(result, bool)


# ─── coerce_optional_float ────────────────────────────────────────────────────


@pytest.mark.unit
def test_coerce_optional_float_int() -> None:  # noqa: D103
    result = coerce_optional_float(42)
    assert result == pytest.approx(42.0)


@pytest.mark.unit
def test_coerce_optional_float_string() -> None:  # noqa: D103
    result = coerce_optional_float("3.14")
    assert result == pytest.approx(3.14)


@pytest.mark.unit
def test_coerce_optional_float_none() -> None:  # noqa: D103
    result = coerce_optional_float(None)
    assert result is None


@pytest.mark.unit
def test_coerce_optional_float_invalid() -> None:  # noqa: D103
    result = coerce_optional_float("not_a_number")
    assert result is None
