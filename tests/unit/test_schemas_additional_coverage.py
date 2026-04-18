"""Additional coverage tests for schema validation helpers."""

from custom_components.pawcontrol.schemas import (
    _validate_schema_property,
    validate_json_schema_payload,
)


def test_validate_json_schema_payload_skips_unknown_keys_when_allowed() -> None:
    """Unknown properties are ignored when additionalProperties is enabled."""
    schema = {
        "type": "object",
        "additionalProperties": True,
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }

    violations = validate_json_schema_payload({"name": "paw", "extra": 1}, schema)

    assert violations == []


def test_validate_schema_property_reports_type_before_other_constraints() -> None:
    """Type mismatches should short-circuit enum and range checks."""
    violations = _validate_schema_property(
        "size",
        "3",
        {
            "type": "integer",
            "enum": [1, 2, 3],
            "minimum": 1,
            "maximum": 10,
            "multipleOf": 2,
        },
    )

    assert len(violations) == 1
    assert violations[0].constraint == "type"


def test_validate_schema_property_reports_max_length_violation() -> None:
    """String fields should report maxLength violations."""
    violations = _validate_schema_property(
        "topic",
        "pawcontrol-too-long",
        {"type": "string", "maxLength": 8},
    )

    assert len(violations) == 1
    assert violations[0].constraint == "maxLength"


def test_validate_schema_property_unknown_type_reports_type_violation() -> None:
    """Unknown JSON schema types should be treated as mismatches."""
    violations = _validate_schema_property(
        "field",
        "value",
        {"type": "unexpected"},
    )

    assert len(violations) == 1
    assert violations[0].constraint == "type"
