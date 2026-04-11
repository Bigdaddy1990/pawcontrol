"""Coverage tests for selected helpers in ``utils._legacy``."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest

from custom_components.pawcontrol.utils._legacy import (
    build_error_context,
    calculate_age_from_months,
    calculate_bmi_equivalent,
    chunk_list,
    clamp,
    convert_units,
    deep_merge_dicts,
    extract_numbers,
    flatten_dict,
    format_distance,
    format_duration,
    generate_entity_id,
    generate_unique_id,
    is_dict_subset,
    is_number,
    merge_configurations,
    normalise_entity_attributes,
    normalise_json_mapping,
    normalise_json_value,
    parse_weight,
    safe_divide,
    safe_get_nested,
    safe_set_nested,
    sanitize_dog_id,
    sanitize_microchip_id,
    unflatten_dict,
    validate_configuration_schema,
    validate_email,
    validate_portion_size,
    validate_time_string,
)


class _ToMappingPayload:
    def to_mapping(self) -> dict[str, object]:
        return {"api_token": "secret", "count": 2}


class _ToDictPayload:
    def to_dict(self) -> dict[str, object]:
        return {"name": "Luna", "weight": 12.5}


def test_build_error_context_prefers_error_message_over_reason() -> None:
    """The context message should mirror the error string when provided."""
    error = ValueError("invalid profile")

    context = build_error_context("timeout", error)

    assert context.error is error
    assert context.reason == "timeout"
    assert context.message == "invalid profile"
    assert context.classification


def test_build_error_context_uses_reason_when_error_missing() -> None:
    """The reason should be used as message when no exception exists."""
    context = build_error_context("auth_failed", None)

    assert context.reason == "auth_failed"
    assert context.error is None
    assert context.message == "auth_failed"
    assert context.classification


def test_deep_merge_dicts_returns_merged_copy_without_mutating_input() -> None:
    """Nested mappings should merge recursively on a copied output mapping."""
    base = {
        "dog": {"name": "Luna", "age": 5},
        "active": True,
    }
    updates = {
        "dog": {"age": 6, "breed": "Collie"},
        "last_feed": "2026-03-27T07:30:00+00:00",
    }

    merged = deep_merge_dicts(base, updates)

    assert merged == {
        "dog": {"name": "Luna", "age": 6, "breed": "Collie"},
        "active": True,
        "last_feed": "2026-03-27T07:30:00+00:00",
    }
    assert base == {
        "dog": {"name": "Luna", "age": 5},
        "active": True,
    }


def test_is_number_accepts_real_numbers_but_rejects_booleans() -> None:
    """`is_number` should keep bool values out of numeric flows."""
    assert is_number(1)
    assert is_number(3.14)
    assert not is_number(True)
    assert not is_number("3.14")


def test_sanitize_dog_id_handles_prefix_and_hash_fallback() -> None:
    """Dog IDs should normalize, prepend prefix, and hash empty results."""
    assert sanitize_dog_id("Nova 007") == "nova_007"
    assert sanitize_dog_id("007") == "dog_007"

    hashed = sanitize_dog_id("***")

    assert hashed.startswith("dog_")
    assert len(hashed) == 12


def test_normalise_json_value_supports_temporal_values_and_collections() -> None:
    """Temporal and collection values should map to JSON-friendly payloads."""
    payload = {
        "stamp": datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
        "day": date(2026, 3, 27),
        "clock": time(8, 30, 0),
        "duration": timedelta(minutes=5),
        "items": {1, 2},
    }

    normalised = normalise_json_value(payload)

    assert normalised["stamp"] == "2026-03-27T12:00:00+00:00"
    assert normalised["day"] == "2026-03-27"
    assert normalised["clock"] == "08:30:00"
    assert normalised["duration"] == "0:05:00"
    assert sorted(normalised["items"]) == [1, 2]


def test_normalise_json_value_handles_dataclass_and_recursion() -> None:
    """Dataclasses should be converted and recursive references should be nulled."""

    @dataclass
    class DogProfile:
        name: str
        age: int

    recursive: dict[str, object] = {"self": None}
    recursive["self"] = recursive
    payload = {"profile": DogProfile("Nova", 4), "recursive": recursive}

    normalised = normalise_json_value(payload)

    assert normalised["profile"] == {"name": "Nova", "age": 4}
    assert normalised["recursive"] == {"self": None}


def test_normalise_json_value_supports_to_mapping_to_dict_and_object_dict() -> None:
    """Normalization should support common object payload-export hooks."""

    class _ObjectPayload:
        def __init__(self) -> None:
            self.value = "ok"

    mapped = normalise_json_value(_ToMappingPayload())
    serialised = normalise_json_value(_ToDictPayload())
    object_payload = normalise_json_value(_ObjectPayload())

    assert mapped == {"api_token": "secret", "count": 2}
    assert serialised == {"name": "Luna", "weight": 12.5}
    assert object_payload == {"value": "ok"}


def test_normalise_mapping_and_entity_attributes_default_to_empty_dict() -> None:
    """Mapping helpers should return empty dicts for missing payloads."""
    assert normalise_json_mapping(None) == {}
    assert normalise_entity_attributes(None) == {}


def test_safe_nested_helpers_get_and_set_values() -> None:
    """Nested helpers should both read and create dotted JSON paths."""
    payload: dict[str, object] = {"dog": {"name": "Luna"}}
    assert safe_get_nested(payload, "dog.name") == "Luna"
    assert safe_get_nested(payload, "dog.weight", default=12.5) == 12.5

    updated = safe_set_nested(payload, "dog.stats.weight", 14.2)

    assert updated["dog"]["stats"]["weight"] == 14.2


def test_validate_time_and_weight_helpers_cover_common_formats() -> None:
    """Validation/parsing helpers should handle valid and invalid input."""
    assert validate_time_string("09:45") == time(9, 45)
    assert validate_time_string("09:45:59") == time(9, 45, 59)
    assert validate_time_string("not-a-time") is None

    assert parse_weight("12kg") == 12.0
    assert parse_weight("22 lb") == 22 * 0.453592
    assert parse_weight(-5) is None
    assert parse_weight("n/a") is None


def test_validate_time_string_rejects_out_of_range_values() -> None:
    """Invalid clock values should be rejected by the parser."""
    assert validate_time_string("25:10") is None
    assert validate_time_string("09:61:00") is None


def test_format_helpers_and_math_helpers() -> None:
    """Formatting and numeric helpers should return stable representations."""
    assert format_duration(59) == "59s"
    assert format_duration(125) == "2m 5s"
    assert format_duration(7200) == "2h"

    assert format_distance(450) == "450 m"
    assert format_distance(3200) == "3.2 km"
    assert format_distance(1609.344, "imperial") == "1.0 mi"

    assert safe_divide(10, 2) == 5
    assert safe_divide(1, 0, default=-1) == -1
    assert safe_divide("10", 2, default=0.0) == 0.0


def test_chunk_and_microchip_helpers() -> None:
    """Chunking and microchip sanitisation should handle edge cases."""
    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert sanitize_microchip_id("ab-12 34!") == "AB1234"
    assert sanitize_microchip_id("***") is None


def test_validate_email_age_and_entity_id_helpers() -> None:
    """Email, age conversion, and entity-id creation should be deterministic."""
    assert validate_email("dog.guardian@example.com")
    assert not validate_email("invalid")
    assert calculate_age_from_months(14) == {
        "years": 1,
        "months": 2,
        "total_months": 14,
    }
    assert (
        generate_entity_id("sensor", "Luna #7", "Daily Feed!")
        == "sensor.luna_7_daily_feed_"
    )


def test_calculate_age_from_months_rejects_bool_and_negative_values() -> None:
    """Age helper should reject invalid argument types and ranges."""
    with pytest.raises(TypeError):
        calculate_age_from_months(True)
    with pytest.raises(ValueError):
        calculate_age_from_months(-1)


def test_bmi_and_portion_validation_cover_boundaries() -> None:
    """BMI and portion checks should expose warning/error branches."""
    assert calculate_bmi_equivalent(4.0, "small") == 15.0
    assert calculate_bmi_equivalent(15.0, "small") == 30.0
    assert calculate_bmi_equivalent(10.0, "small") == pytest.approx(22.045, abs=0.001)
    assert calculate_bmi_equivalent(10.0, "unknown") is None

    invalid_portion = validate_portion_size(float("nan"), 100)
    assert not invalid_portion["valid"]
    assert "finite number" in invalid_portion["warnings"][0]

    oversized = validate_portion_size(80, 100, meals_per_day=4)
    assert not oversized["valid"]
    assert oversized["percentage_of_daily"] == 80.0
    assert "Portion exceeds 70% of daily requirement" in oversized["warnings"]

    small_with_invalid_meal_count = validate_portion_size(2, 100, meals_per_day=0)
    assert small_with_invalid_meal_count["valid"]
    assert (
        "Meals per day is not positive" in small_with_invalid_meal_count["warnings"][0]
    )
    assert "very small" in small_with_invalid_meal_count["warnings"][-1]


def test_validate_portion_size_rejects_non_numeric_and_invalid_daily_amount() -> None:
    """Validation should fail with actionable messages for invalid inputs."""
    not_numeric = validate_portion_size("invalid", 120)  # type: ignore[arg-type]
    bad_daily = validate_portion_size(20, 0)

    assert not not_numeric["valid"]
    assert "Portion must be a real number" in not_numeric["warnings"]
    assert not bad_daily["valid"]
    assert "must be positive" in bad_daily["warnings"][0]


def test_collection_and_configuration_helpers_cover_edge_cases() -> None:
    """Flattening, set comparisons, and schema/config helpers should be stable."""
    flattened = flatten_dict({"dog": {"name": "Nova", "stats": {"walks": 2}}})
    assert flattened == {"dog.name": "Nova", "dog.stats.walks": 2}
    assert unflatten_dict(flattened) == {"dog": {"name": "Nova", "stats": {"walks": 2}}}

    assert is_dict_subset({"a": 1}, {"a": 1, "b": 2})
    assert not is_dict_subset({"a": 2}, {"a": 1, "b": 2})
    assert not is_dict_subset({"a": 1}, None)  # type: ignore[arg-type]

    merged = merge_configurations(
        {"dog": {"name": "Luna"}, "token": "base"},
        {"dog": {"weight": 12}, "token": "ignored"},
        protected_keys={"token"},
    )
    assert merged == {"dog": {"name": "Luna", "weight": 12}, "token": "base"}

    schema = validate_configuration_schema(
        {"required": 1, "extra": 2},
        required_keys={"required", "missing"},
        optional_keys={"optional"},
    )
    assert not schema["valid"]
    assert schema["missing_keys"] == ["missing"]
    assert schema["unknown_keys"] == ["extra"]


def test_numeric_and_conversion_helpers() -> None:
    """Numeric utility helpers should cover success and failure branches."""
    assert clamp(5, 0, 3) == 3
    assert clamp(-1, 0, 3) == 0
    assert extract_numbers("w1 -2.5 and 3") == [1.0, -2.5, 3.0]
    assert generate_unique_id(" Dog ", "Feed#1", "") == "dog_feed_1"
    assert generate_unique_id("", "###") == "unknown"
    assert convert_units(1, "kg", "lb") == pytest.approx(2.20462)
    assert convert_units(1, "KM", " km ") == 1
    with pytest.raises(ValueError):
        convert_units(1, "kg", "c")
    with pytest.raises(ValueError):
        chunk_list([1, 2], 0)
