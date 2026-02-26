"""Tests for the PawControl JSON schema validation module.

Covers validate_json_schema_payload, SchemaViolation, the GPS/geofence/options
schemas, and all internal type-check helpers in schemas.py.
"""

import pytest

from custom_components.pawcontrol.schemas import (
    GEOFENCE_OPTIONS_JSON_SCHEMA,
    GPS_DOG_CONFIG_JSON_SCHEMA,
    GPS_OPTIONS_JSON_SCHEMA,
    SchemaViolation,
    _is_integer,
    _is_number,
    _matches_type,
    _validate_schema_property,
    validate_json_schema_payload,
)

# ---------------------------------------------------------------------------
# SchemaViolation dataclass
# ---------------------------------------------------------------------------


class TestSchemaViolation:
    """Tests for the SchemaViolation dataclass."""

    def test_fields_are_stored(self) -> None:
        """Constructor args are available as attributes."""
        v = SchemaViolation(field="name", value="x", constraint="minLength")
        assert v.field == "name"
        assert v.value == "x"
        assert v.constraint == "minLength"

    def test_is_frozen(self) -> None:
        """SchemaViolation instances must be immutable."""
        v = SchemaViolation(field="f", value=None, constraint="required")
        with pytest.raises(Exception):  # noqa: B017
            v.field = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _is_number / _is_integer
# ---------------------------------------------------------------------------


class TestTypeHelpers:
    """Tests for _is_number and _is_integer helpers."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            (1, True),
            (1.5, True),
            (0, True),
            (-3.14, True),
            (True, False),  # booleans are excluded
            (False, False),
            ("1", False),
            (None, False),
        ],
    )
    def test_is_number(self, value: object, expected: bool) -> None:
        """Booleans must be excluded from numeric checks."""
        assert _is_number(value) is expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            (5, True),
            (0, True),
            (-1, True),
            (3.14, False),
            (True, False),
            (False, False),
            ("5", False),
            (None, False),
        ],
    )
    def test_is_integer(self, value: object, expected: bool) -> None:
        """Only plain int values (not bool) should match."""
        assert _is_integer(value) is expected


# ---------------------------------------------------------------------------
# _matches_type
# ---------------------------------------------------------------------------


class TestMatchesType:
    """Tests for _matches_type helper."""

    def test_string_matches_string(self) -> None:
        assert _matches_type("hello", "string") is True

    def test_integer_matches_integer(self) -> None:
        assert _matches_type(5, "integer") is True

    def test_float_does_not_match_integer(self) -> None:
        assert _matches_type(5.5, "integer") is False

    def test_float_matches_number(self) -> None:
        assert _matches_type(5.5, "number") is True

    def test_integer_matches_number(self) -> None:
        assert _matches_type(5, "number") is True

    def test_bool_does_not_match_number(self) -> None:
        assert _matches_type(True, "number") is False

    def test_bool_matches_boolean(self) -> None:
        assert _matches_type(True, "boolean") is True

    def test_none_matches_null(self) -> None:
        assert _matches_type(None, "null") is True

    def test_value_does_not_match_null(self) -> None:
        assert _matches_type(0, "null") is False

    def test_list_of_types_accepts_first_match(self) -> None:
        assert _matches_type(None, ["string", "null"]) is True

    def test_list_of_types_accepts_second_match(self) -> None:
        assert _matches_type("x", ["string", "null"]) is True

    def test_list_of_types_rejects_no_match(self) -> None:
        assert _matches_type(5, ["string", "null"]) is False

    def test_unknown_type_string_returns_false(self) -> None:
        assert _matches_type("anything", "object") is False


# ---------------------------------------------------------------------------
# _validate_schema_property
# ---------------------------------------------------------------------------


class TestValidateSchemaProperty:
    """Tests for _validate_schema_property helper."""

    def test_valid_string_passes(self) -> None:
        violations = _validate_schema_property("k", "hello", {"type": "string"})
        assert violations == []

    def test_wrong_type_returns_violation(self) -> None:
        violations = _validate_schema_property("k", 5, {"type": "string"})
        assert len(violations) == 1
        assert violations[0].constraint == "type"

    def test_enum_accepts_valid_value(self) -> None:
        violations = _validate_schema_property(
            "k", "a", {"type": "string", "enum": ["a", "b"]}
        )
        assert violations == []

    def test_enum_rejects_invalid_value(self) -> None:
        violations = _validate_schema_property(
            "k", "z", {"type": "string", "enum": ["a", "b"]}
        )
        assert any(v.constraint == "enum" for v in violations)

    def test_minlength_passes(self) -> None:
        violations = _validate_schema_property(
            "k", "ab", {"type": "string", "minLength": 2}
        )
        assert violations == []

    def test_minlength_fails(self) -> None:
        violations = _validate_schema_property(
            "k", "a", {"type": "string", "minLength": 2}
        )
        assert any(v.constraint == "minLength" for v in violations)

    def test_maxlength_passes(self) -> None:
        violations = _validate_schema_property(
            "k", "ab", {"type": "string", "maxLength": 5}
        )
        assert violations == []

    def test_maxlength_fails(self) -> None:
        violations = _validate_schema_property(
            "k", "abcdef", {"type": "string", "maxLength": 3}
        )
        assert any(v.constraint == "maxLength" for v in violations)

    def test_minimum_passes(self) -> None:
        violations = _validate_schema_property(
            "k", 10, {"type": "integer", "minimum": 5}
        )
        assert violations == []

    def test_minimum_fails(self) -> None:
        violations = _validate_schema_property(
            "k", 3, {"type": "integer", "minimum": 5}
        )
        assert any(v.constraint == "minimum" for v in violations)

    def test_maximum_passes(self) -> None:
        violations = _validate_schema_property(
            "k", 5, {"type": "integer", "maximum": 10}
        )
        assert violations == []

    def test_maximum_fails(self) -> None:
        violations = _validate_schema_property(
            "k", 15, {"type": "integer", "maximum": 10}
        )
        assert any(v.constraint == "maximum" for v in violations)

    def test_multiple_of_passes(self) -> None:
        violations = _validate_schema_property(
            "k", 4, {"type": "integer", "multipleOf": 2}
        )
        assert violations == []

    def test_multiple_of_fails(self) -> None:
        violations = _validate_schema_property(
            "k", 3, {"type": "integer", "multipleOf": 2}
        )
        assert any(v.constraint == "multipleOf" for v in violations)


# ---------------------------------------------------------------------------
# validate_json_schema_payload
# ---------------------------------------------------------------------------


class TestValidateJsonSchemaPayload:
    """Tests for the top-level validate_json_schema_payload function."""

    def test_non_dict_returns_type_violation(self) -> None:
        violations = validate_json_schema_payload(
            "not-a-dict", GPS_DOG_CONFIG_JSON_SCHEMA
        )
        assert len(violations) == 1
        assert violations[0].field == "payload"
        assert violations[0].constraint == "type"

    def test_missing_required_field(self) -> None:
        violations = validate_json_schema_payload({}, GPS_DOG_CONFIG_JSON_SCHEMA)
        fields = [v.field for v in violations]
        assert "gps_source" in fields

    def test_valid_minimal_gps_dog_config(self) -> None:
        payload = {"gps_source": "device_tracker"}
        violations = validate_json_schema_payload(payload, GPS_DOG_CONFIG_JSON_SCHEMA)
        assert violations == []

    def test_additional_property_rejected_when_disallowed(self) -> None:
        payload = {"gps_source": "device_tracker", "extra_field": "value"}
        violations = validate_json_schema_payload(payload, GPS_DOG_CONFIG_JSON_SCHEMA)
        assert any(v.constraint == "additional" for v in violations)

    def test_gps_update_interval_too_low(self) -> None:
        payload = {"gps_source": "device_tracker", "gps_update_interval": 1}
        violations = validate_json_schema_payload(payload, GPS_DOG_CONFIG_JSON_SCHEMA)
        assert any(
            v.field == "gps_update_interval" and v.constraint == "minimum"
            for v in violations
        )

    def test_gps_update_interval_valid(self) -> None:
        payload = {"gps_source": "device_tracker", "gps_update_interval": 30}
        violations = validate_json_schema_payload(payload, GPS_DOG_CONFIG_JSON_SCHEMA)
        assert all(v.field != "gps_update_interval" for v in violations)

    def test_gps_options_schema_valid_empty(self) -> None:
        """Empty dict is valid since no fields are required in GPS options."""
        violations = validate_json_schema_payload({}, GPS_OPTIONS_JSON_SCHEMA)
        assert violations == []

    def test_gps_options_invalid_gps_source_enum(self) -> None:
        payload = {"gps_source": "invalid_source"}
        violations = validate_json_schema_payload(payload, GPS_OPTIONS_JSON_SCHEMA)
        assert any(v.constraint == "enum" for v in violations)

    def test_gps_options_valid_gps_source_enum(self) -> None:
        payload = {"gps_source": "device_tracker"}
        violations = validate_json_schema_payload(payload, GPS_OPTIONS_JSON_SCHEMA)
        assert violations == []

    def test_geofence_options_valid_enabled(self) -> None:
        payload = {"enabled": True, "use_home": False}
        violations = validate_json_schema_payload(payload, GEOFENCE_OPTIONS_JSON_SCHEMA)
        assert violations == []

    def test_geofence_lat_out_of_range(self) -> None:
        payload = {"lat": -200.0}
        violations = validate_json_schema_payload(payload, GEOFENCE_OPTIONS_JSON_SCHEMA)
        assert any(v.field == "lat" for v in violations)

    def test_geofence_radius_below_minimum(self) -> None:
        payload = {"radius": 1}
        violations = validate_json_schema_payload(payload, GEOFENCE_OPTIONS_JSON_SCHEMA)
        assert any(
            v.field == "radius" and v.constraint == "minimum" for v in violations
        )

    def test_geofence_radius_above_maximum(self) -> None:
        payload = {"radius": 999999}
        violations = validate_json_schema_payload(payload, GEOFENCE_OPTIONS_JSON_SCHEMA)
        assert any(
            v.field == "radius" and v.constraint == "maximum" for v in violations
        )

    def test_geofence_null_lat_accepted(self) -> None:
        """Null latitude should be accepted (type: [number, null])."""
        payload = {"lat": None}
        violations = validate_json_schema_payload(payload, GEOFENCE_OPTIONS_JSON_SCHEMA)
        assert all(v.field != "lat" for v in violations)

    def test_mqtt_topic_too_long(self) -> None:
        payload = {"mqtt_topic": "x" * 257}
        violations = validate_json_schema_payload(payload, GPS_OPTIONS_JSON_SCHEMA)
        assert any(
            v.field == "mqtt_topic" and v.constraint == "maxLength" for v in violations
        )

    def test_push_payload_max_bytes_valid(self) -> None:
        payload = {"push_payload_max_bytes": 65536}
        violations = validate_json_schema_payload(payload, GPS_OPTIONS_JSON_SCHEMA)
        assert violations == []

    def test_push_payload_max_bytes_too_low(self) -> None:
        payload = {"push_payload_max_bytes": 100}
        violations = validate_json_schema_payload(payload, GPS_OPTIONS_JSON_SCHEMA)
        assert any(v.field == "push_payload_max_bytes" for v in violations)
