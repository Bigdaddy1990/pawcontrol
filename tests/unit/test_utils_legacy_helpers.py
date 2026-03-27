"""Coverage tests for selected helpers in ``utils._legacy``."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from custom_components.pawcontrol.utils._legacy import (
    build_error_context,
    chunk_list,
    deep_merge_dicts,
    format_distance,
    format_duration,
    is_number,
    normalise_entity_attributes,
    normalise_json_mapping,
    normalise_json_value,
    parse_weight,
    safe_divide,
    safe_get_nested,
    safe_set_nested,
    sanitize_dog_id,
    sanitize_microchip_id,
    validate_time_string,
)


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
