"""Additional coverage tests for schema validation edge branches."""

from custom_components.pawcontrol.schemas import validate_json_schema_payload


def test_schema_validator_collects_string_length_violations() -> None:
    """String validators should report both min/max length violations."""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 3, "maxLength": 5},
        },
    }

    too_short = validate_json_schema_payload({"name": "ab"}, schema)
    too_long = validate_json_schema_payload({"name": "abcdef"}, schema)

    assert [(v.field, v.constraint) for v in too_short] == [("name", "minLength")]
    assert [(v.field, v.constraint) for v in too_long] == [("name", "maxLength")]


def test_schema_validator_checks_numeric_maximum_and_multiple_of() -> None:
    """Numeric constraints should apply maximum and multipleOf checks."""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "interval": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "multipleOf": 3,
            },
        },
    }

    too_high = validate_json_schema_payload({"interval": 11}, schema)
    wrong_multiple = validate_json_schema_payload({"interval": 8}, schema)

    assert [(v.field, v.constraint) for v in too_high] == [
        ("interval", "maximum"),
        ("interval", "multipleOf"),
    ]
    assert [(v.field, v.constraint) for v in wrong_multiple] == [
        ("interval", "multipleOf")
    ]


def test_schema_validator_type_violation_short_circuits_enum_checks() -> None:
    """Type mismatch should be reported before enum validation."""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"source": {"type": "string", "enum": ["mqtt", "webhook"]}},
    }

    violations = validate_json_schema_payload({"source": 42}, schema)

    assert [(v.field, v.constraint) for v in violations] == [("source", "type")]


def test_schema_validator_allows_unknown_fields_when_additional_allowed() -> None:
    """Schemas with additionalProperties enabled should ignore extra keys."""
    schema = {
        "type": "object",
        "additionalProperties": True,
        "required": ["required_field"],
        "properties": {"required_field": {"type": "boolean"}},
    }

    violations = validate_json_schema_payload(
        {"required_field": True, "extra": "value"},
        schema,
    )

    assert violations == []
