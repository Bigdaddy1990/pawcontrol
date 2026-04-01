"""Coverage tests for flow_validation.py — (0% → 30%+).

Covers: is_dog_config_payload_valid, normalize_dog_id, ensure_json_mapping,
        ensure_dog_modules_config, coerce_float, coerce_int
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.flow_validation import (
    coerce_float,
    coerce_int,
    ensure_dog_modules_config,
    ensure_json_mapping,
    is_dog_config_payload_valid,
    normalize_dog_id,
    validate_dog_config_payload,
)
from custom_components.pawcontrol.validation import InputCoercionError

# ─── is_dog_config_payload_valid ─────────────────────────────────────────────


@pytest.mark.unit
def test_is_valid_empty_dict() -> None:
    assert is_dog_config_payload_valid({}) is False


@pytest.mark.unit
def test_is_valid_minimal_required() -> None:
    result = is_dog_config_payload_valid({"dog_id": "rex", "dog_name": "Rex"})
    assert result is True


@pytest.mark.unit
def test_is_valid_missing_dog_name() -> None:
    result = is_dog_config_payload_valid({"dog_id": "rex"})
    assert result is False


@pytest.mark.unit
def test_is_valid_missing_dog_id() -> None:
    result = is_dog_config_payload_valid({"dog_name": "Rex"})
    assert result is False


# ─── normalize_dog_id (flow_validation) ──────────────────────────────────────


@pytest.mark.unit
def test_fv_normalize_dog_id_lowercase() -> None:
    result = normalize_dog_id("Rex")
    assert result == "rex"


@pytest.mark.unit
def test_fv_normalize_dog_id_strips_whitespace() -> None:
    result = normalize_dog_id("  buddy  ")
    assert result == "buddy"


@pytest.mark.unit
def test_fv_normalize_dog_id_already_clean() -> None:
    assert normalize_dog_id("rex_01") == "rex_01"


# ─── ensure_json_mapping (flow_validation) ───────────────────────────────────


@pytest.mark.unit
def test_fv_ensure_json_mapping_none() -> None:
    result = ensure_json_mapping(None)
    assert isinstance(result, dict)
    assert len(result) == 0


@pytest.mark.unit
def test_fv_ensure_json_mapping_dict() -> None:
    data = {"key": "val", "num": 42}
    result = ensure_json_mapping(data)
    assert result["key"] == "val"


# ─── ensure_dog_modules_config (flow_validation) ─────────────────────────────


@pytest.mark.unit
def test_fv_ensure_dog_modules_config_empty() -> None:
    result = ensure_dog_modules_config({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_fv_ensure_dog_modules_config_with_modules() -> None:
    result = ensure_dog_modules_config({"feeding": True, "walk": False})
    assert isinstance(result, dict)
    assert result.get("feeding") is True


# ─── coerce_float / coerce_int (flow_validation) ─────────────────────────────


@pytest.mark.unit
def test_fv_coerce_float_string() -> None:
    result = coerce_float("weight", "3.14")
    assert result == pytest.approx(3.14)


@pytest.mark.unit
def test_fv_coerce_float_int() -> None:
    result = coerce_float("weight", 42)
    assert result == pytest.approx(42.0)


@pytest.mark.unit
def test_fv_coerce_float_invalid_raises() -> None:
    with pytest.raises((InputCoercionError, Exception)):
        coerce_float("weight", "bad")


@pytest.mark.unit
def test_fv_coerce_int_valid() -> None:
    result = coerce_int("meals", "3")
    assert result == 3


@pytest.mark.unit
def test_fv_coerce_int_invalid_raises() -> None:
    with pytest.raises((InputCoercionError, Exception)):
        coerce_int("meals", "not_number")
