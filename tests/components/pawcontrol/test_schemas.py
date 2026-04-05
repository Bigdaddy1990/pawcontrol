"""Tests for JSON schema payload validation helpers."""

from custom_components.pawcontrol.const import CONF_GPS_SOURCE
from custom_components.pawcontrol.schemas import (
    GPS_OPTIONS_JSON_SCHEMA,
    SchemaViolation,
    validate_json_schema_payload,
)


def test_validate_json_schema_payload_rejects_non_mapping_payload() -> None:
    """A non-dict payload should return a payload type violation."""
    violations = validate_json_schema_payload(
        ["not", "a", "dict"], GPS_OPTIONS_JSON_SCHEMA
    )

    assert violations == [
        SchemaViolation(field="payload", value=["not", "a", "dict"], constraint="type")
    ]


def test_validate_json_schema_payload_reports_required_and_additional() -> None:
    """The validator should report missing required and unexpected fields."""
    schema = {
        "type": "object",
        "required": [CONF_GPS_SOURCE],
        "additionalProperties": False,
        "properties": {CONF_GPS_SOURCE: {"type": "string"}},
    }

    violations = validate_json_schema_payload({"unexpected": 1}, schema)

    assert (
        SchemaViolation(field=CONF_GPS_SOURCE, value=None, constraint="required")
        in violations
    )
    assert (
        SchemaViolation(field="unexpected", value=1, constraint="additional")
        in violations
    )


def test_validate_json_schema_payload_checks_enum_and_string_bounds() -> None:
    """Enum, minLength, and maxLength constraints should be enforced."""
    schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "enum": ["manual", "webhook"]},
            "topic": {"type": "string", "minLength": 2, "maxLength": 4},
        },
    }

    violations = validate_json_schema_payload(
        {"source": "bluetooth", "topic": "x"},
        schema,
    )

    assert (
        SchemaViolation(field="source", value="bluetooth", constraint="enum")
        in violations
    )
    assert (
        SchemaViolation(field="topic", value="x", constraint="minLength") in violations
    )

    too_long = validate_json_schema_payload(
        {"source": "manual", "topic": "topic"}, schema
    )
    assert too_long == [
        SchemaViolation(field="topic", value="topic", constraint="maxLength"),
    ]


def test_validate_json_schema_payload_checks_number_and_multiple_of() -> None:
    """Minimum, maximum, and multipleOf constraints should be enforced."""
    schema = {
        "type": "object",
        "properties": {
            "interval": {
                "type": "integer",
                "minimum": 5,
                "maximum": 12,
                "multipleOf": 2,
            },
            "accuracy": {"type": "number", "minimum": 0.5, "maximum": 5},
            "nullable": {"type": ["null", "integer"]},
        },
    }

    violations = validate_json_schema_payload(
        {
            "interval": 7,
            "accuracy": 6.5,
            "nullable": None,
        },
        schema,
    )

    assert (
        SchemaViolation(field="interval", value=7, constraint="multipleOf")
        in violations
    )
    assert (
        SchemaViolation(field="accuracy", value=6.5, constraint="maximum") in violations
    )

    below_minimum = validate_json_schema_payload(
        {"interval": 3, "accuracy": 0.1}, schema
    )
    assert (
        SchemaViolation(field="interval", value=3, constraint="minimum")
        in below_minimum
    )
    assert (
        SchemaViolation(field="accuracy", value=0.1, constraint="minimum")
        in below_minimum
    )


def test_validate_json_schema_payload_treats_bool_as_non_numeric() -> None:
    """Boolean values must not satisfy integer/number validators."""
    schema = {
        "type": "object",
        "properties": {
            "interval": {"type": "integer"},
            "accuracy": {"type": "number"},
        },
    }

    violations = validate_json_schema_payload(
        {"interval": True, "accuracy": False}, schema
    )

    assert violations == [
        SchemaViolation(field="interval", value=True, constraint="type"),
        SchemaViolation(field="accuracy", value=False, constraint="type"),
    ]


def test_validate_json_schema_payload_handles_boolean_and_unknown_types() -> None:
    """Boolean types should pass and unknown schema types should fail."""
    schema = {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean"},
            "unsupported": {"type": "object"},
        },
    }

    violations = validate_json_schema_payload(
        {"enabled": True, "unsupported": {}},
        schema,
    )

    assert violations == [
        SchemaViolation(field="unsupported", value={}, constraint="type"),
    ]
