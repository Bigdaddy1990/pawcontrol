"""Coverage tests for flow_validation.py — (0% → 30%+).

Covers: is_dog_config_payload_valid, normalize_dog_id, ensure_json_mapping,
        ensure_dog_modules_config, coerce_float, coerce_int
"""

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.flow_validation import (
    _validate_breed,
    _validate_dog_id,
    coerce_float,
    coerce_int,
    ensure_dog_modules_config,
    ensure_json_mapping,
    is_dog_config_payload_valid,
    normalize_dog_id,
)
from custom_components.pawcontrol.validation import InputCoercionError

# ─── is_dog_config_payload_valid ─────────────────────────────────────────────


@pytest.mark.unit
def test_is_valid_empty_dict() -> None:  # noqa: D103
    assert is_dog_config_payload_valid({}) is False


@pytest.mark.unit
def test_is_valid_minimal_required() -> None:  # noqa: D103
    result = is_dog_config_payload_valid({"dog_id": "rex", "dog_name": "Rex"})
    assert result is True


@pytest.mark.unit
def test_is_valid_missing_dog_name() -> None:  # noqa: D103
    result = is_dog_config_payload_valid({"dog_id": "rex"})
    assert result is False


@pytest.mark.unit
def test_is_valid_missing_dog_id() -> None:  # noqa: D103
    result = is_dog_config_payload_valid({"dog_name": "Rex"})
    assert result is False


# ─── normalize_dog_id (flow_validation) ──────────────────────────────────────


@pytest.mark.unit
def test_fv_normalize_dog_id_lowercase() -> None:  # noqa: D103
    result = normalize_dog_id("Rex")
    assert result == "rex"


@pytest.mark.unit
def test_fv_normalize_dog_id_strips_whitespace() -> None:  # noqa: D103
    result = normalize_dog_id("  buddy  ")
    assert result == "buddy"


@pytest.mark.unit
def test_fv_normalize_dog_id_already_clean() -> None:  # noqa: D103
    assert normalize_dog_id("rex_01") == "rex_01"


# ─── ensure_json_mapping (flow_validation) ───────────────────────────────────


@pytest.mark.unit
def test_fv_ensure_json_mapping_none() -> None:  # noqa: D103
    result = ensure_json_mapping(None)
    assert isinstance(result, dict)
    assert len(result) == 0


@pytest.mark.unit
def test_fv_ensure_json_mapping_dict() -> None:  # noqa: D103
    data = {"key": "val", "num": 42}
    result = ensure_json_mapping(data)
    assert result["key"] == "val"


# ─── ensure_dog_modules_config (flow_validation) ─────────────────────────────


@pytest.mark.unit
def test_fv_ensure_dog_modules_config_empty() -> None:  # noqa: D103
    result = ensure_dog_modules_config({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_fv_ensure_dog_modules_config_with_modules() -> None:  # noqa: D103
    result = ensure_dog_modules_config({"feeding": True, "walk": False})
    assert isinstance(result, dict)
    assert result.get("feeding") is True


# ─── coerce_float / coerce_int (flow_validation) ─────────────────────────────


@pytest.mark.unit
def test_fv_coerce_float_string() -> None:  # noqa: D103
    result = coerce_float("weight", "3.14")
    assert result == pytest.approx(3.14)


@pytest.mark.unit
def test_fv_coerce_float_int() -> None:  # noqa: D103
    result = coerce_float("weight", 42)
    assert result == pytest.approx(42.0)


@pytest.mark.unit
def test_fv_coerce_float_invalid_raises() -> None:  # noqa: D103
    with pytest.raises((InputCoercionError, Exception)):
        coerce_float("weight", "bad")


@pytest.mark.unit
def test_fv_coerce_int_valid() -> None:  # noqa: D103
    result = coerce_int("meals", "3")
    assert result == 3


@pytest.mark.unit
def test_fv_coerce_int_invalid_raises() -> None:  # noqa: D103
    with pytest.raises((InputCoercionError, Exception)):
        coerce_int("meals", "not_number")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_id", "existing_ids", "expected_id", "expected_error"),
    [
        (42, None, "", "invalid_dog_id_format"),
        ("x" * 31, None, "x" * 31, "dog_id_too_long"),
        ("buddy!", None, "buddy!", "invalid_dog_id_format"),
        ("buddy", {"buddy"}, "buddy", "dog_id_already_exists"),
    ],
)
def test_fv_validate_dog_id_edge_cases(  # noqa: D103
    raw_id: object,
    existing_ids: set[str] | None,
    expected_id: str,
    expected_error: str,
) -> None:
    dog_id, error = _validate_dog_id(raw_id, existing_ids=existing_ids)

    assert dog_id == expected_id
    assert error == expected_error


@pytest.mark.unit
def test_fv_validate_breed_normalises_and_rejects_invalid_values() -> None:  # noqa: D103
    assert _validate_breed("  border collie  ") == "border collie"

    with pytest.raises(ValidationError):
        _validate_breed(3.14)


@pytest.mark.unit
def test_fv_validate_breed_empty_and_none_return_none() -> None:  # noqa: D103
    assert _validate_breed(None) is None
    assert _validate_breed("   ") is None
